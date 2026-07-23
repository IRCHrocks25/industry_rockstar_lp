"""Seed a fresh Site from a SiteTemplate (architecture.md §17).

Deterministic and synchronous — no import job, no LLM. Each TemplatePage
becomes a Page with a draft PageVersion whose field_values start as the
template's defaults, so the marketer lands straight in the editor. Forms get
the same detection the import pipeline runs (§11), and a form's
data-success-path wires its thank-you page across the new siblings.
"""

from copy import deepcopy

from django.db import transaction
from lxml import html as lxml_html

from apps.forms.integration import detect_and_sync
from apps.pages.models import Page, PageVersion


@transaction.atomic
def provision_site(site, template, user=None):
    """Create every template page on `site`. Returns the homepage Page (or the
    first page) — the natural place to send the marketer next."""
    created = []
    for template_page in template.pages.all():
        page = Page.objects.create(site=site, name=template_page.name, path=template_page.path)
        html = detect_and_sync(page, template_page.template_html)
        version = PageVersion.objects.create(
            page=page,
            template_html=html,
            annotation_map=deepcopy(template_page.annotation_map),
            field_values=deepcopy(template_page.default_values),
            created_by=user,
            note=f"Started from the “{template.name}” template",
        )
        page.draft_version = version
        page.save(update_fields=["draft_version", "updated_at"])
        created.append((page, version))

    _wire_success_pages(created)
    pages = [page for page, _ in created]
    return next((p for p in pages if p.path == ""), pages[0] if pages else None)


def _wire_success_pages(created):
    """A template form may declare data-success-path="thank-you"; point that
    Form's success_page at the sibling created from that path."""
    by_path = {page.path: page for page, _ in created}
    for page, version in created:
        doc = lxml_html.document_fromstring(version.template_html)
        for node in doc.xpath("//form[@data-editable-id][@data-success-path]"):
            target = by_path.get((node.get("data-success-path") or "").strip().strip("/"))
            if target is None or target.id == page.id:
                continue
            page.forms.filter(editable_id=node.get("data-editable-id")).update(success_page=target)
