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


@override_settings(
    APP_HOST_NAME="app.testbase.com",
    BASE_DOMAIN_NAME="testbase.com",
    ALLOWED_HOSTS=["app.testbase.com", ".testbase.com"],
)
class SiteCreateTests(TestCase):
    HOST = "app.testbase.com"

    def setUp(self):
        user = get_user_model().objects.create_user(username="teammate", password="pass12345")
        self.client.force_login(user)

    def _post(self, data):
        return self.client.post("/sites/new/", data, HTTP_HOST=self.HOST)

    def test_creates_site_and_redirects(self):
        response = self._post({"name": "Spring Promo", "subdomain": "spring-promo"})
        self.assertRedirects(response, "/")
        self.assertTrue(Site.objects.filter(subdomain="spring-promo").exists())

    def test_subdomain_is_normalized_to_lowercase(self):
        self._post({"name": "Loud", "subdomain": "LOUD"})
        self.assertTrue(Site.objects.filter(subdomain="loud").exists())

    def test_reserved_subdomain_rejected(self):
        response = self._post({"name": "Sneaky", "subdomain": "app"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "reserved")
        self.assertFalse(Site.objects.exists())

    def test_duplicate_subdomain_rejected(self):
        Site.objects.create(subdomain="promo", name="First")
        response = self._post({"name": "Second", "subdomain": "promo"})
        self.assertContains(response, "already taken")
        self.assertEqual(Site.objects.count(), 1)

    def test_invalid_characters_rejected(self):
        response = self._post({"name": "Bad", "subdomain": "no spaces!"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Site.objects.exists())

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get("/sites/new/", HTTP_HOST=self.HOST)
        self.assertEqual(response.status_code, 302)
