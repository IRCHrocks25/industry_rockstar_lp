from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from .middleware import HostRouterMiddleware
from .models import Site


@override_settings(
    APP_HOST="app.testbase.com",
    APP_HOST_NAME="app.testbase.com",
    BASE_DOMAIN_NAME="testbase.com",
    ALLOWED_HOSTS=[
        "app.testbase.com",
        "testbase.com",
        ".testbase.com",
        "elsewhere.com",
        "127.0.0.1",
        "localhost",
    ],
)
class HostRouterMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = HostRouterMiddleware(lambda request: HttpResponse("ok"))
        self.site = Site.objects.create(subdomain="promo", name="Promo Funnel")

    def _request(self, host):
        return self.factory.get("/", HTTP_HOST=host)

    def test_app_host_routes_to_control_plane(self):
        request = self._request("app.testbase.com")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.urlconf, "config.urls_control")
        self.assertFalse(hasattr(request, "site"))

    def test_known_subdomain_routes_to_publishing_with_site(self):
        request = self._request("promo.testbase.com")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.urlconf, "config.urls_publishing")
        self.assertEqual(request.site, self.site)

    def test_matching_is_port_insensitive(self):
        for host, urlconf in [
            ("app.testbase.com:8000", "config.urls_control"),
            ("promo.testbase.com:8000", "config.urls_publishing"),
        ]:
            request = self._request(host)
            self.middleware(request)
            self.assertEqual(request.urlconf, urlconf, host)

    def test_unknown_subdomain_404s(self):
        with self.assertRaises(Http404):
            self.middleware(self._request("nope.testbase.com"))

    def test_unrelated_host_404s(self):
        with self.assertRaises(Http404):
            self.middleware(self._request("elsewhere.com"))

    def test_bare_base_domain_404s(self):
        with self.assertRaises(Http404):
            self.middleware(self._request("testbase.com"))

    def test_nested_subdomain_404s(self):
        with self.assertRaises(Http404):
            self.middleware(self._request("a.promo.testbase.com"))

    @override_settings(DEBUG=True)
    def test_loopback_redirects_to_app_host_in_debug(self):
        request = self.factory.get("/login/?next=/", HTTP_HOST="127.0.0.1:8001")
        response = self.middleware(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://app.testbase.com/login/?next=/")

    @override_settings(DEBUG=True)
    def test_bare_localhost_redirects_in_debug(self):
        response = self.middleware(self._request("localhost:8001"))
        self.assertEqual(response.status_code, 302)

    def test_loopback_404s_when_debug_off(self):
        with self.assertRaises(Http404):
            self.middleware(self._request("127.0.0.1"))

    def test_subdomain_match_is_case_insensitive(self):
        request = self._request("PROMO.testbase.com")
        self.middleware(request)
        self.assertEqual(request.site, self.site)


class SiteModelTests(TestCase):
    def test_reserved_subdomain_rejected(self):
        from django.core.exceptions import ValidationError

        site = Site(subdomain="app", name="Nope")
        with self.assertRaises(ValidationError):
            site.full_clean()
