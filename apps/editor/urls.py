"""Control-plane UI routes (auth-gated)."""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.sites_list, name="sites_list"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="editor/login.html", redirect_authenticated_user=True
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
