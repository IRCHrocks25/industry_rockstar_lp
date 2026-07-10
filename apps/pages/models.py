import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from apps.sites.models import Site

path_validator = RegexValidator(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
    "Use lowercase letters, digits and hyphens (no leading/trailing hyphen).",
)


class Page(models.Model):
    """A single URL within a Site ('' = the homepage). architecture.md §8."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="pages")
    name = models.CharField(max_length=200, help_text="Team-facing label, e.g. “Landing page”.")
    path = models.CharField(
        max_length=200, blank=True, default="", validators=[path_validator],
        help_text="URL path under the subdomain; empty = homepage.",
    )
    seo_title = models.CharField(max_length=200, blank=True, default="")
    seo_description = models.CharField(max_length=300, blank=True, default="")
    og_image = models.URLField(blank=True, default="")
    draft_version = models.ForeignKey(
        "PageVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    published_version = models.ForeignKey(
        "PageVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["site", "path"], name="unique_path_per_site"),
        ]
        ordering = ["path"]

    def __str__(self):
        return f"{self.name} (/{self.path})"

    @property
    def is_published(self):
        return self.published_version_id is not None

    @property
    def status(self):
        return "published" if self.is_published else "draft"


class PageVersion(models.Model):
    """The editable state: template HTML + annotation map + field values.

    The Page.draft_version pointer targets the mutable autosave version;
    publishing snapshots it into an immutable row (see publish flow).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="versions")
    template_html = models.TextField()
    annotation_map = models.JSONField(default=dict, blank=True)
    field_values = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.page_id} @ {self.created_at:%Y-%m-%d %H:%M}"

    def fields_by_group(self):
        """Annotation fields grouped for the editor side panel, in stable order."""
        groups = {}
        for field in self.annotation_map.get("fields", []):
            groups.setdefault(field.get("group") or "Content", []).append(field)
        return groups


class ImportSource(models.Model):
    """Immutable record of what was imported."""

    class SourceType(models.TextChoices):
        PASTE = "paste", "Pasted HTML"
        UPLOAD = "upload", "Uploaded file"
        URL = "url", "Fetched from URL"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="import_sources")
    raw_html = models.TextField(blank=True, default="")  # filled by the job for URL imports
    source_type = models.CharField(max_length=16, choices=SourceType.choices)
    source_url = models.URLField(blank=True, default="", max_length=1000)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ImportJob(models.Model):
    """Async tracking for the import pipeline (architecture.md §7)."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="import_jobs")
    source = models.ForeignKey(ImportSource, null=True, on_delete=models.SET_NULL, related_name="jobs")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    error = models.TextField(blank=True, default="")
    warnings = models.JSONField(default=list, blank=True)  # e.g. assets that failed to rehost
    llm_tokens = models.PositiveIntegerField(default=0)  # stays 0 until Phase 3
    cost_cents = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class PublishRecord(models.Model):
    """History for rollback: which version was rendered to which blob, when."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="publish_records")
    version = models.ForeignKey(PageVersion, on_delete=models.PROTECT, related_name="publish_records")
    rendered_key = models.CharField(max_length=500)
    published_at = models.DateTimeField(auto_now_add=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["-published_at"]
