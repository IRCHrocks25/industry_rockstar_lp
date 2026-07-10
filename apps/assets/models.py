import uuid

from django.db import models


class Asset(models.Model):
    """Rehosted media, deduped by content hash (architecture.md §8)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sha256 = models.CharField(max_length=64, unique=True)
    storage_key = models.CharField(max_length=500)
    original_url = models.TextField(blank=True, default="")
    content_type = models.CharField(max_length=100)
    bytes = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.storage_key
