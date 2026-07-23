from django.contrib import admin

from .models import SiteTemplate, TemplatePage


class TemplatePageInline(admin.StackedInline):
    model = TemplatePage
    extra = 0
    fields = ("name", "path", "sort", "html_source")


@admin.register(SiteTemplate)
class SiteTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "sort", "page_count", "updated_at")
    list_editable = ("is_active", "sort")
    inlines = [TemplatePageInline]

    @admin.display(description="Pages")
    def page_count(self, obj):
        return obj.pages.count()
