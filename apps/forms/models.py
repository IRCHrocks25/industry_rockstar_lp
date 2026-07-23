"""Forms & lead capture (architecture.md §11, §8).

A `Form` wires an imported <form> on a Page to a webhook + a success destination
(another Page = the thank-you). Every submit is written to the `Submission`
ledger (decided §13.1) as lead backup + retry bookkeeping. The resilient default
(§13.2) stores the submission, redirects immediately, and forwards the webhook
async with retries so a flaky endpoint never costs a conversion.
"""

import uuid

from django.db import models

from apps.pages.models import Page


class Form(models.Model):
    class SubmitMode(models.TextChoices):
        PROXY = "proxy", "Server-side proxy"
        # 'intercept' (client-side) is a later option (architecture.md §11).

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="forms")
    editable_id = models.CharField(
        max_length=200, help_text="data-editable-id of the <form> node this configures."
    )
    name = models.CharField(max_length=200, default="Lead form")
    webhook_url = models.URLField(blank=True, default="", max_length=1000)
    submit_mode = models.CharField(max_length=16, choices=SubmitMode.choices, default=SubmitMode.PROXY)
    success_page = models.ForeignKey(
        Page, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="Thank-you Page in this Site to send visitors to on success.",
    )
    success_url = models.URLField(blank=True, default="", max_length=1000, help_text="External success URL (if no Page).")
    gate_redirect_on_success = models.BooleanField(
        default=False,
        help_text="Off (default): store + redirect immediately, forward async. "
        "On: wait for the webhook to succeed before redirecting.",
    )
    field_map = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["page", "editable_id"], name="unique_form_per_page"),
        ]
        ordering = ["editable_id"]

    def __str__(self):
        return f"{self.name} ({self.editable_id})"

    def success_destination(self) -> str:
        """Where to send the visitor after a successful submit. Same-Site Page
        path (relative to the subdomain) wins, then an external URL, then '/'."""
        if self.success_page_id and self.success_page:
            return "/" + self.success_page.path
        return self.success_url or "/"


class Submission(models.Model):
    """Lead ledger: every submit, its payload, and webhook delivery state."""

    class WebhookStatus(models.TextChoices):
        SKIPPED = "skipped", "No webhook configured"
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Delivered"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="submissions")
    payload = models.JSONField(default=dict)
    webhook_status = models.CharField(
        max_length=16, choices=WebhookStatus.choices, default=WebhookStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["form", "-created_at"])]

    def __str__(self):
        return f"Submission {self.id} ({self.webhook_status})"
