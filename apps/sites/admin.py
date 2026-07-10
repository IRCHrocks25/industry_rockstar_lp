from django.contrib import admin

from .models import Domain, Site


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("name", "subdomain", "created_at")
    search_fields = ("name", "subdomain")
    inlines = [DomainInline]


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("hostname", "site", "is_primary", "tls_status")
    list_filter = ("tls_status", "is_primary")
    search_fields = ("hostname",)
