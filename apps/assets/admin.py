from django.contrib import admin

from .models import Asset


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("storage_key", "content_type", "bytes", "created_at")
    search_fields = ("original_url", "sha256")
