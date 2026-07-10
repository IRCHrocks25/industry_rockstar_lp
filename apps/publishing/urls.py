"""Public page routes for a resolved Site (request.site is always set here)."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="site_home"),
]
