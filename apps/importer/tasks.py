"""Django-Q2 task for the import pipeline. Job state lives on ImportJob."""

from django.db import transaction
from django.utils import timezone
from django_q.tasks import async_task

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
        with transaction.atomic():
            version = PageVersion.objects.create(
                page=job.page,
                template_html=template_html,
                created_by=job.source.created_by if job.source else None,
                note="Imported",
            )
            job.page.draft_version = version
            job.page.save(update_fields=["draft_version", "updated_at"])
            job.status = ImportJob.Status.SUCCEEDED
            job.warnings = warnings
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "warnings", "finished_at"])
    except Exception as exc:  # job row is the source of truth; don't re-raise
        job.status = ImportJob.Status.FAILED
        job.error = str(exc)[:2000] or exc.__class__.__name__
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])


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
