from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.importer.tasks import enqueue_import
from apps.pages.models import ImportJob, ImportSource, Page
from apps.sites.models import Site

from .forms import PageImportForm, SiteForm


@login_required
def sites_list(request):
    return render(
        request,
        "editor/sites_list.html",
        {"sites": Site.objects.all(), "base_domain": settings.BASE_DOMAIN},
    )


@login_required
def site_create(request):
    form = SiteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        site = form.save()
        messages.success(request, f"“{site.name}” is live at {site.subdomain}.{settings.BASE_DOMAIN}.")
        return redirect("sites_list")
    return render(
        request,
        "editor/site_form.html",
        {"form": form, "base_domain": settings.BASE_DOMAIN},
    )


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
        {"page": page, "site": page.site, "version": page.draft_version,
         "base_domain": settings.BASE_DOMAIN},
    )


@login_required
@xframe_options_sameorigin
def page_preview(request, page_id):
    """Draft preview for the editor iframe. Imported scripts are stripped at
    import time, so this HTML is inert; the iframe adds sandbox on top."""
    page = get_object_or_404(Page.objects.select_related("draft_version"), id=page_id)
    if page.draft_version is None:
        return HttpResponse("<!doctype html><p>Nothing imported yet.</p>")
    return HttpResponse(page.draft_version.template_html)
