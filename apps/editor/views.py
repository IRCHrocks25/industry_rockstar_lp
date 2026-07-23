import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from apps.annotation import service as annotation_service
from apps.annotation.schema import EDITABLE_FIELD_TYPES
from apps.forms.models import Form
from apps.importer.tasks import enqueue_import
from apps.library import parser as template_parser
from apps.library.models import SiteTemplate, TemplatePage
from apps.library.provision import provision_site
from apps.library.tasks import enqueue_template_annotation
from apps.pages.models import ImportJob, ImportSource, Page
from apps.pages.render import render_version
from apps.publishing.service import NothingToPublish, publish_page
from apps.sites.models import Site

from .forms import PageImportForm, SiteForm, TemplateCreateForm


@login_required
def sites_list(request):
    return render(
        request,
        "editor/sites_list.html",
        {"sites": Site.objects.all(), "base_domain": settings.BASE_DOMAIN},
    )


@login_required
def site_create(request):
    form = SiteForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        site = form.save()
        template = form.cleaned_data.get("template")
        if template:
            homepage = provision_site(site, template, user=request.user)
            messages.success(
                request,
                f"“{site.name}” was created from “{template.name}” — make it yours, then publish.",
            )
            if homepage:
                return redirect("page_edit", page_id=homepage.id)
        elif form.cleaned_data["start"] == SiteForm.START_PASTE:
            raw_html, source_type = form.pasted_html()
            page = Page.objects.create(site=site, name="Landing page", path="")
            source = ImportSource.objects.create(
                page=page, raw_html=raw_html, source_type=source_type, created_by=request.user
            )
            job = ImportJob.objects.create(page=page, source=source)
            enqueue_import(job)
            messages.success(request, f"“{site.name}” created — making your page editable now.")
            return redirect("import_status", page_id=page.id, job_id=job.id)
        else:
            messages.success(request, f"“{site.name}” is live at {site.subdomain}.{settings.BASE_DOMAIN}.")
        return redirect("sites_list")
    return render(
        request,
        "editor/site_form.html",
        {
            "form": form,
            "base_domain": settings.BASE_DOMAIN,
            "templates": SiteTemplate.gallery().prefetch_related("pages"),
        },
    )


@login_required
def templates_list(request):
    templates = SiteTemplate.objects.prefetch_related("pages")
    annotating = any(
        p.status == TemplatePage.Status.ANNOTATING for t in templates for p in t.pages.all()
    )
    return render(
        request,
        "editor/templates_list.html",
        {"templates": templates, "annotating": annotating},
    )


@login_required
def template_create(request):
    form = TemplateCreateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        template = form.save()
        pages = [("Landing page", "", form.cleaned_data["landing_html"])]
        if form.cleaned_data["thanks_html"]:
            pages.append(("Thank you", "thank-you", form.cleaned_data["thanks_html"]))
        needs_ai = False
        for sort, (name, path, html) in enumerate(pages):
            page = TemplatePage(
                template=template, name=name, path=path, sort=sort, html_source=html
            )
            if not template_parser.has_annotations(html):
                page.status = TemplatePage.Status.ANNOTATING
                needs_ai = True
            page.save()
            if page.status == TemplatePage.Status.ANNOTATING:
                enqueue_template_annotation(page)
        if needs_ai:
            messages.success(
                request,
                f"“{template.name}” added — the AI is finding the editable parts; it'll appear "
                "in the gallery in a minute.",
            )
        else:
            messages.success(request, f"“{template.name}” added to the gallery.")
        return redirect("templates_list")
    return render(request, "editor/template_form.html", {"form": form})


@login_required
@require_POST
def template_delete(request, template_id):
    template = get_object_or_404(SiteTemplate, id=template_id)
    name = template.name
    template.delete()  # sites made from it keep their own copies
    messages.success(request, f"Removed “{name}” from the gallery.")
    return redirect("templates_list")


@login_required
@xframe_options_sameorigin
def template_preview(request, template_id):
    """The template's homepage as stored — defaults ARE the markup's content,
    so no render pass is needed. Feeds the gallery thumbnails + preview tab."""
    template = get_object_or_404(SiteTemplate, id=template_id)
    page = template.homepage
    if page is None:
        return HttpResponse("<!doctype html><p>This template has no pages yet.</p>")
    return HttpResponse(page.template_html)


@login_required
def site_detail(request, site_id):
    site = get_object_or_404(Site, id=site_id)
    return render(
        request,
        "editor/site_detail.html",
        {"site": site, "pages": site.pages.all(), "base_domain": settings.BASE_DOMAIN},
    )


@login_required
def page_import(request, site_id):
    site = get_object_or_404(Site, id=site_id)
    form = PageImportForm(site, request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        page = Page.objects.create(site=site, name=form.cleaned_data["name"], path=form.cleaned_data["path"])
        source = ImportSource.objects.create(
            page=page,
            raw_html=form.raw_html(),
            source_type=form.cleaned_data["source_type"],
            source_url=form.cleaned_data.get("source_url", ""),
            created_by=request.user,
        )
        job = ImportJob.objects.create(page=page, source=source)
        enqueue_import(job)
        return redirect("import_status", page_id=page.id, job_id=job.id)
    return render(request, "editor/page_import.html", {"site": site, "form": form})


@login_required
def import_status(request, page_id, job_id):
    page = get_object_or_404(Page, id=page_id)
    job = get_object_or_404(ImportJob, id=job_id, page=page)
    return render(request, "editor/import_status.html", {"page": page, "job": job})


@login_required
def import_status_json(request, page_id, job_id):
    job = get_object_or_404(ImportJob, id=job_id, page_id=page_id)
    return JsonResponse({"status": job.status, "error": job.error, "warnings": job.warnings})


@login_required
def page_edit(request, page_id):
    page = get_object_or_404(Page.objects.select_related("site", "draft_version"), id=page_id)
    if page.draft_version is None:
        latest_job = page.import_jobs.first()
        if latest_job:
            return redirect("import_status", page_id=page.id, job_id=latest_job.id)
        return redirect("site_detail", site_id=page.site_id)
    return render(
        request,
        "editor/page_edit.html",
        {
            "page": page,
            "site": page.site,
            "version": page.draft_version,
            "groups": _field_view_groups(page.draft_version),
            "forms": page.forms.select_related("success_page").all(),
            "sibling_pages": page.site.pages.exclude(id=page.id),
            "base_domain": settings.BASE_DOMAIN,
            "annotation_enabled": annotation_service.is_enabled(),
        },
    )


@login_required
@require_POST
def page_publish(request, page_id):
    """Snapshot the draft and put it live on the subdomain (§10)."""
    page = get_object_or_404(Page.objects.select_related("site", "draft_version"), id=page_id)
    try:
        publish_page(page, user=request.user)
    except NothingToPublish as exc:
        messages.error(request, str(exc))
    else:
        live = f"{page.site.subdomain}.{settings.BASE_DOMAIN}/{page.path + '/' if page.path else ''}"
        messages.success(request, f"“{page.name}” is live at {live}")
    return redirect("page_edit", page_id=page.id)


@login_required
@require_POST
def page_reannotate(request, page_id):
    """Re-run the import pipeline (incl. AI annotation) on the page's current
    draft HTML — the 'try again' for pages that imported with no fields, no
    manual re-import needed. Replaces the draft version on success."""
    page = get_object_or_404(Page.objects.select_related("draft_version"), id=page_id)
    version = page.draft_version
    if version is None:
        return redirect("page_edit", page_id=page.id)
    if not annotation_service.is_enabled():
        messages.error(
            request,
            "AI annotation is turned off — add OPENAI_API_KEY to .env and restart, then try again.",
        )
        return redirect("page_edit", page_id=page.id)
    source = ImportSource.objects.create(
        page=page,
        raw_html=_strip_stale_editable_ids(version.template_html),
        source_type=ImportSource.SourceType.PASTE,
        created_by=request.user,
    )
    job = ImportJob.objects.create(page=page, source=source)
    enqueue_import(job)
    return redirect("import_status", page_id=page.id, job_id=job.id)


def _strip_stale_editable_ids(template_html):
    """Old data-editable-id attributes must not survive a re-annotation — a new
    field could slug to the same id and the renderer would patch the stale node."""
    from lxml import html as lxml_html

    doc = lxml_html.document_fromstring(template_html)
    for el in doc.xpath("//*[@data-editable-id]"):
        del el.attrib["data-editable-id"]
    return lxml_html.tostring(doc, doctype="<!DOCTYPE html>", encoding="unicode")


@login_required
@require_POST
def form_save(request, form_id):
    """Save one Form's wiring: webhook URL, success destination, resilience."""
    form = get_object_or_404(Form.objects.select_related("page"), id=form_id)
    form.webhook_url = request.POST.get("webhook_url", "").strip()
    form.gate_redirect_on_success = bool(request.POST.get("gate_redirect_on_success"))

    success_page_id = request.POST.get("success_page", "")
    if success_page_id:
        form.success_page = get_object_or_404(
            Page, id=success_page_id, site=form.page.site
        )
        form.success_url = ""
    else:
        form.success_page = None
        form.success_url = request.POST.get("success_url", "").strip()

    form.save()
    messages.success(request, f"Saved “{form.name}”.")
    return redirect("page_edit", page_id=form.page_id)


def _field_view_groups(version):
    """Annotation fields for the side panel: grouped, with the draft value and a
    flag for whether this phase can actually edit the type yet."""
    values = version.field_values or {}
    groups = []
    for group_name, fields in version.fields_by_group().items():
        rendered = []
        for f in fields:
            rendered.append(
                {
                    **f,
                    "value": values.get(f["id"]),
                    "editable": f.get("field_type") in EDITABLE_FIELD_TYPES,
                }
            )
        groups.append({"name": group_name, "fields": rendered})
    return groups


@login_required
@xframe_options_sameorigin
def page_preview(request, page_id):
    """Draft preview for the editor iframe. Rendered through the same engine as
    publish (mode='edit' keeps data-editable-id) so draft field values show;
    imported scripts were stripped at import, and the iframe adds sandbox.
    The live-edit bridge is appended here, never on the publish path."""
    page = get_object_or_404(Page.objects.select_related("draft_version"), id=page_id)
    if page.draft_version is None:
        return HttpResponse("<!doctype html><p>Nothing imported yet.</p>")
    html = render_version(page.draft_version, mode="edit", page=page)
    bridge = f'<script src="{settings.STATIC_URL}js/preview-bridge.js"></script>'
    if "</body>" in html:
        html = html.replace("</body>", bridge + "</body>", 1)
    else:
        html += bridge
    return HttpResponse(html)


@login_required
@require_POST
def page_save(request, page_id):
    """Autosave endpoint: merge submitted field values into the draft version.
    Body is JSON {"values": {editable_id: value}}. Only known, this-phase-
    editable fields are accepted; anything else is ignored."""
    page = get_object_or_404(Page.objects.select_related("draft_version"), id=page_id)
    version = page.draft_version
    if version is None:
        return HttpResponseBadRequest("This page has nothing to edit yet.")

    try:
        payload = json.loads(request.body or "{}")
        incoming = payload["values"]
        if not isinstance(incoming, dict):
            raise ValueError
    except (json.JSONDecodeError, KeyError, ValueError):
        return HttpResponseBadRequest("Expected JSON body {\"values\": {...}}.")

    editable = {
        f["id"]: f
        for f in version.annotation_map.get("fields", [])
        if f.get("field_type") in EDITABLE_FIELD_TYPES
    }
    values = version.field_values or {}
    for field_id, value in incoming.items():
        if field_id in editable:
            values[field_id] = value

    version.field_values = values
    version.save(update_fields=["field_values", "updated_at"])
    return JsonResponse({"saved": True})
