"""Template library (architecture.md §17): agency-authored starting points.

A SiteTemplate is annotated HTML with derived schema — structure the agency
owns, values the marketer edits. The schema (annotation_map + default values)
is ALWAYS rebuilt from html_source on save; it is never edited directly, so
HTML and schema cannot drift.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.pages.models import path_validator

from . import parser


class SiteTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    description = models.CharField(
        max_length=300, blank=True, default="",
        help_text="One line the marketer sees in the gallery, e.g. “Collect leads with a free download”.",
    )
    is_active = models.BooleanField(default=True, help_text="Shown on the New site screen.")
    sort = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort", "name"]

    def __str__(self):
        return self.name

    @property
    def homepage(self):
        return self.pages.filter(path="").first() or self.pages.first()

    @classmethod
    def gallery(cls):
        """What the New site screen offers: active, has pages, none of them
        still annotating or failed."""
        return (
            cls.objects.filter(is_active=True, pages__isnull=False)
            .exclude(pages__status__in=[TemplatePage.Status.ANNOTATING, TemplatePage.Status.FAILED])
            .distinct()
        )


class TemplatePage(models.Model):
    """One page of a template funnel (e.g. landing + thank-you).

    Two authoring paths: html_source with DSL annotations derives
    template_html / annotation_map / default_values synchronously on save;
    plain HTML (a GHL export pasted in the UI) is filled in by the async AI
    annotation task (tasks.annotate_template_page) and carries a status."""

    class Status(models.TextChoices):
        READY = "ready", "Ready"
        ANNOTATING = "annotating", "Annotating"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(SiteTemplate, on_delete=models.CASCADE, related_name="pages")
    name = models.CharField(max_length=200, help_text="Page label the marketer sees, e.g. “Landing page”.")
    path = models.CharField(
        max_length=200, blank=True, default="", validators=[path_validator],
        help_text="URL path on the created site; empty = homepage.",
    )
    sort = models.PositiveSmallIntegerField(default=0)
    html_source = models.TextField(
        help_text="Annotated HTML: mark editable slots with data-edit/data-type/data-label "
        "inside data-section blocks. Saving derives the schema.",
    )
    template_html = models.TextField(editable=False, default="")
    annotation_map = models.JSONField(editable=False, default=dict, blank=True)
    default_values = models.JSONField(editable=False, default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.READY, editable=False
    )
    error = models.TextField(blank=True, default="", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["template", "path"], name="unique_path_per_template"),
        ]
        ordering = ["sort", "path"]

    def __str__(self):
        return f"{self.template} — {self.name} (/{self.path})"

    def clean(self):
        if not parser.has_annotations(self.html_source):
            return  # plain HTML: the AI task fills the derived fields
        try:
            parser.build(self.html_source)
        except parser.TemplateSourceError as exc:
            raise ValidationError({"html_source": str(exc)})

    def save(self, *args, **kwargs):
        if parser.has_annotations(self.html_source):
            self.template_html, self.annotation_map, self.default_values = parser.build(self.html_source)
            self.status = self.Status.READY
            self.error = ""
        super().save(*args, **kwargs)
