from django.contrib import admin

from .models import ImportJob, ImportSource, Page, PageVersion, PublishRecord


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("name", "site", "path", "status", "updated_at")
    list_filter = ("site",)
    search_fields = ("name", "path")


@admin.register(PageVersion)
class PageVersionAdmin(admin.ModelAdmin):
    list_display = ("page", "note", "created_by", "created_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ImportSource)
class ImportSourceAdmin(admin.ModelAdmin):
    list_display = ("page", "source_type", "source_url", "created_at")


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = ("page", "status", "created_at", "finished_at")
    list_filter = ("status",)


@admin.register(PublishRecord)
class PublishRecordAdmin(admin.ModelAdmin):
    list_display = ("page", "rendered_key", "published_at", "published_by")
