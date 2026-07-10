"""Control plane URLs — editor + admin, served only on APP_HOST."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.editor.urls")),
]
