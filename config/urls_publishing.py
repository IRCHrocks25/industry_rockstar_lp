"""Publishing plane URLs — public pages on {subdomain}.BASE_DOMAIN.

Selected per-request by HostRouterMiddleware, which guarantees request.site
is set before any view here runs.
"""

from django.urls import include, path

urlpatterns = [
    path("", include("apps.publishing.urls")),
]
