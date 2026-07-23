"""Public page routes for a resolved Site (request.site is always set here)."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.serve_page, name="site_home"),
    path("<slug:path>/", views.serve_page, name="site_page"),
]
