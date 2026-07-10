"""Host-based routing between the control and publishing planes (architecture.md §6)."""

from django.conf import settings
from django.http import Http404

from .models import Site


class HostRouterMiddleware:
    """Resolve the Host header to a plane before URL resolution.

    - APP_HOST                    -> control plane (editor/admin)
    - {subdomain}.BASE_DOMAIN     -> publishing plane, request.site attached
    - anything else               -> 404 (no information leaked)

    Matching is port-insensitive so dev hosts like promo.localhost:8000 work.
    Custom domains (v2) will add a Domain-table lookup before the 404.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # get_host() has already validated against ALLOWED_HOSTS (DisallowedHost -> 400).
        host = request.get_host().rsplit(":", 1)[0].lower()

        if host == settings.APP_HOST_NAME:
            request.urlconf = "config.urls_control"
            return self.get_response(request)

        suffix = f".{settings.BASE_DOMAIN_NAME}"
        if host.endswith(suffix):
            subdomain = host.removesuffix(suffix)
            if subdomain and "." not in subdomain:
                site = Site.objects.filter(subdomain=subdomain).first()
                if site is not None:
                    request.site = site
                    request.urlconf = "config.urls_publishing"
                    return self.get_response(request)

        raise Http404
