"""Publishing plane URLs — public pages on {subdomain}.BASE_DOMAIN.

Selected per-request by HostRouterMiddleware, which guarantees request.site
is set before any view here runs.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

# DEBUG only: rehosted assets referenced by pages are served off the same
# subdomain in dev. Production serves media from object storage/CDN.
urlpatterns = static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) + [
    path("", include("apps.publishing.urls")),
]
