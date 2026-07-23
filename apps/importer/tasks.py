"""Django-Q2 task for the import pipeline. Job state lives on ImportJob."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_q.tasks import async_task

from apps.annotation import service as annotation
from apps.annotation.client import AnnotationError
from apps.assets.fetcher import FetchError, fetch_url
from apps.pages.models import ImportJob, ImportSource, PageVersion

from . import pipeline


def enqueue_import(job):
    async_task("apps.importer.tasks.run_import", str(job.id))


def run_import(job_id):
    job = ImportJob.objects.select_related("source", "page").get(id=job_id)
    if job.status == ImportJob.Status.SUCCEEDED:
        return  # idempotence guard against duplicate deliveries
    job.status = ImportJob.Status.RUNNING
    job.save(update_fields=["status"])

    try:
        raw_html = _resolve_raw_html(job.source)
        template_html, warnings = pipeline.process_html(raw_html, rehost=_rehost_step(job))
        outcome, note = _annotate_step(template_html, warnings)
        with transaction.atomic():
            # Deterministic form detection: stamp ids + create Form records (§11).
            final_html = _detect_forms(job.page, outcome.template_html)
            version = PageVersion.objects.create(
                page=job.page,
                template_html=final_html,
                annotation_map=outcome.annotation_map,
                field_values=outcome.field_values,
                created_by=job.source.created_by if job.source else None,
                note=note,
            )
            job.page.draft_version = version
            job.page.save(update_fields=["draft_version", "updated_at"])
            job.status = ImportJob.Status.SUCCEEDED
            job.warnings = warnings
            job.llm_tokens = outcome.tokens
            job.cost_cents = round(outcome.tokens / 1000 * settings.OPENAI_COST_CENTS_PER_1K)
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "warnings", "llm_tokens", "cost_cents", "finished_at"])
    except Exception as exc:  # job row is the source of truth; don't re-raise
        job.status = ImportJob.Status.FAILED
        job.error = str(exc)[:2000] or exc.__class__.__name__
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])


def _detect_forms(page, template_html):
    from apps.forms.integration import detect_and_sync

    return detect_and_sync(page, template_html)


def _annotate_step(template_html, warnings):
    """Run the LLM annotation pass if enabled. Failure is non-fatal (§2: the LLM
    never blocks the core loop) — the import still lands, just without fields,
    and the reason is surfaced as an ImportJob warning. Returns
    (AnnotationOutcome, version_note); mutates `warnings` in place."""
    if not annotation.is_enabled():
        return annotation.AnnotationOutcome(template_html=template_html), "Imported"
    try:
        outcome = annotation.annotate_html(template_html)
    except AnnotationError as exc:
        warnings.append(f"AI annotation skipped: {exc}")
        return annotation.AnnotationOutcome(template_html=template_html), "Imported (annotation failed)"
    return outcome, f"Imported ({outcome.field_count} fields annotated)"


def _resolve_raw_html(source):
    if source is None:
        raise ValueError("This import has no source.")
    if source.raw_html:
        return source.raw_html
    if source.source_type == ImportSource.SourceType.URL and source.source_url:
        try:
            result = fetch_url(
                source.source_url,
                max_bytes=5 * 1024 * 1024,
                allowed_types=("text/html", "application/xhtml"),
            )
        except FetchError as exc:
            raise ValueError(str(exc))
        source.raw_html = result.text
        source.save(update_fields=["raw_html"])
        return source.raw_html
    raise ValueError("The import was empty.")


def _rehost_step(job):
    from apps.assets.rehost import Rehoster

    base_url = job.source.source_url or None if job.source else None

    def step(doc):
        rehoster = Rehoster(base_url=base_url)
        return rehoster.rehost_document(doc)

    return step
