"""Async annotation for templates pasted as plain HTML (no DSL attributes).

Mirrors the import job (§7): sanitize + rehost + stamp via the importer
pipeline, then the AI annotation pass. With annotation disabled or failing,
the template still becomes READY — just without editable fields — matching the
import behavior (§2: the LLM never blocks the loop). Only a pipeline error
(unparseable/empty HTML) marks the page FAILED.
"""

from django_q.tasks import async_task

from apps.annotation import service as annotation
from apps.annotation.client import AnnotationError
from apps.importer import pipeline

from .models import TemplatePage


def enqueue_template_annotation(template_page):
    async_task("apps.library.tasks.annotate_template_page", str(template_page.id))


def annotate_template_page(template_page_id):
    page = TemplatePage.objects.get(id=template_page_id)
    if page.status != TemplatePage.Status.ANNOTATING:
        return  # idempotence guard against duplicate deliveries

    try:
        html, _warnings = pipeline.process_html(page.html_source, rehost=_rehost_step())
        if annotation.is_enabled():
            try:
                outcome = annotation.annotate_html(html)
            except AnnotationError as exc:
                outcome = annotation.AnnotationOutcome(template_html=html)
                page.error = f"AI annotation skipped: {exc}"
        else:
            outcome = annotation.AnnotationOutcome(template_html=html)
        page.template_html = outcome.template_html
        page.annotation_map = outcome.annotation_map
        page.default_values = outcome.field_values
        page.status = TemplatePage.Status.READY
    except Exception as exc:  # row is the source of truth; don't re-raise
        page.status = TemplatePage.Status.FAILED
        page.error = str(exc)[:2000] or exc.__class__.__name__
    page.save()


def _rehost_step():
    from apps.assets.rehost import Rehoster

    def step(doc):
        return Rehoster(base_url=None).rehost_document(doc)

    return step
