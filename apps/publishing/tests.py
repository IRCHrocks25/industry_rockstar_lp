from django.test import TestCase, override_settings

from apps.sites.models import Site


@override_settings(
    APP_HOST_NAME="app.testbase.com",
    BASE_DOMAIN_NAME="testbase.com",
    ALLOWED_HOSTS=["app.testbase.com", "testbase.com", ".testbase.com"],
)
class PublishingPlaneTests(TestCase):
    """Full request-cycle checks through HostRouterMiddleware."""

    def setUp(self):
        self.site = Site.objects.create(subdomain="promo", name="Promo Funnel")

    def test_site_root_serves_placeholder(self):
        response = self.client.get("/", HTTP_HOST="promo.testbase.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Promo Funnel")

    def test_unknown_subdomain_404s(self):
        response = self.client.get("/", HTTP_HOST="nope.testbase.com")
        self.assertEqual(response.status_code, 404)

    def test_control_plane_urls_not_reachable_on_subdomain(self):
        response = self.client.get("/admin/login/", HTTP_HOST="promo.testbase.com")
        self.assertEqual(response.status_code, 404)

    def test_admin_reachable_on_app_host_only(self):
        response = self.client.get("/admin/login/", HTTP_HOST="app.testbase.com")
        self.assertEqual(response.status_code, 200)
