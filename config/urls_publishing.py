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
    # /_submit/{form_id} — the form proxy (architecture.md §11). Before the page
    # server so it's never shadowed by a page path.
    path("", include("apps.forms.urls")),
    path("", include("apps.publishing.urls")),
]
