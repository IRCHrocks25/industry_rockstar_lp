from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.sites.models import Site


@override_settings(
    APP_HOST_NAME="app.testbase.com",
    BASE_DOMAIN_NAME="testbase.com",
    ALLOWED_HOSTS=["app.testbase.com", ".testbase.com"],
)
class EditorShellTests(TestCase):
    HOST = "app.testbase.com"

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="teammate", password="pass12345")

    def test_sites_list_requires_login(self):
        response = self.client.get("/", HTTP_HOST=self.HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_sites_list_shows_sites_when_authenticated(self):
        Site.objects.create(subdomain="promo", name="Promo Funnel")
        self.client.force_login(self.user)
        response = self.client.get("/", HTTP_HOST=self.HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Promo Funnel")

    def test_login_page_renders(self):
        response = self.client.get("/login/", HTTP_HOST=self.HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")
