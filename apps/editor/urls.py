"""Control-plane UI routes (auth-gated)."""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.sites_list, name="sites_list"),
    path("sites/new/", views.site_create, name="site_create"),
    path("sites/<uuid:site_id>/", views.site_detail, name="site_detail"),
    path("sites/<uuid:site_id>/pages/new/", views.page_import, name="page_import"),
    path("pages/<uuid:page_id>/import/<uuid:job_id>/", views.import_status, name="import_status"),
    path("pages/<uuid:page_id>/import/<uuid:job_id>/status/", views.import_status_json, name="import_status_json"),
    path("pages/<uuid:page_id>/edit/", views.page_edit, name="page_edit"),
    path("pages/<uuid:page_id>/preview/", views.page_preview, name="page_preview"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="editor/login.html", redirect_authenticated_user=True
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
