"""Control-plane UI routes (auth-gated)."""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.sites_list, name="sites_list"),
    path("sites/new/", views.site_create, name="site_create"),
    path("templates/", views.templates_list, name="templates_list"),
    path("templates/new/", views.template_create, name="template_create"),
    path("templates/<uuid:template_id>/delete/", views.template_delete, name="template_delete"),
    path("templates/<uuid:template_id>/preview/", views.template_preview, name="template_preview"),
    path("sites/<uuid:site_id>/", views.site_detail, name="site_detail"),
    path("sites/<uuid:site_id>/pages/new/", views.page_import, name="page_import"),
    path("pages/<uuid:page_id>/import/<uuid:job_id>/", views.import_status, name="import_status"),
    path("pages/<uuid:page_id>/import/<uuid:job_id>/status/", views.import_status_json, name="import_status_json"),
    path("pages/<uuid:page_id>/edit/", views.page_edit, name="page_edit"),
    path("pages/<uuid:page_id>/preview/", views.page_preview, name="page_preview"),
    path("pages/<uuid:page_id>/save/", views.page_save, name="page_save"),
    path("pages/<uuid:page_id>/reannotate/", views.page_reannotate, name="page_reannotate"),
    path("pages/<uuid:page_id>/publish/", views.page_publish, name="page_publish"),
    path("forms/<uuid:form_id>/save/", views.form_save, name="form_save"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="editor/login.html", redirect_authenticated_user=True
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
