import uuid

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

subdomain_validator = RegexValidator(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    "Use lowercase letters, digits and hyphens (no leading/trailing hyphen).",
)

# Never routable as published sites: the control plane and common noise.
RESERVED_SUBDOMAINS = {"app", "www", "admin", "api", "mail"}


class Site(models.Model):
    """A subdomain-hosted funnel: one or more Pages under {subdomain}.BASE_DOMAIN."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subdomain = models.CharField(max_length=63, unique=True, validators=[subdomain_validator])
    name = models.CharField(max_length=200)
    default_head_scripts = models.TextField(
        blank=True, default="", help_text="Managed scripts injected into <head> of every published page."
    )
    default_body_scripts = models.TextField(
        blank=True, default="", help_text="Managed scripts injected before </body> of every published page."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.subdomain})"

    def clean(self):
        if self.subdomain in RESERVED_SUBDOMAINS:
            raise ValidationError({"subdomain": "This subdomain is reserved."})


class Domain(models.Model):
    """A hostname pointing at a Site. Subdomains now; custom domains in v2."""

    class TlsStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        ERROR = "error", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="domains")
    hostname = models.CharField(max_length=253, unique=True)
    is_primary = models.BooleanField(default=False)
    tls_status = models.CharField(max_length=16, choices=TlsStatus.choices, default=TlsStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["hostname"]

    def __str__(self):
        return self.hostname

    def clean(self):
        self.hostname = self.hostname.strip().lower().rstrip(".")
