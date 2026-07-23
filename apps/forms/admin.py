from django.contrib import admin

from .models import Form, Submission


@admin.register(Form)
class FormAdmin(admin.ModelAdmin):
    list_display = ("name", "editable_id", "page", "webhook_url", "gate_redirect_on_success")
    list_filter = ("submit_mode", "gate_redirect_on_success")
    search_fields = ("name", "editable_id", "webhook_url")
    raw_id_fields = ("page", "success_page")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "form", "webhook_status", "attempts", "created_at")
    list_filter = ("webhook_status",)
    search_fields = ("form__name", "form__editable_id")
    readonly_fields = ("form", "payload", "webhook_status", "attempts", "last_error", "created_at")
    date_hierarchy = "created_at"
