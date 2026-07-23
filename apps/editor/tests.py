import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.pages.models import Page, PageVersion
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


@override_settings(
    APP_HOST_NAME="app.testbase.com",
    BASE_DOMAIN_NAME="testbase.com",
    ALLOWED_HOSTS=["app.testbase.com", ".testbase.com"],
)
class EditorFieldsTests(TestCase):
    HOST = "app.testbase.com"

    def setUp(self):
        user = get_user_model().objects.create_user(username="teammate", password="pass12345")
        self.client.force_login(user)
        site = Site.objects.create(subdomain="promo", name="Promo")
        self.page = Page.objects.create(site=site, name="Landing page", path="")
        self.version = PageVersion.objects.create(
            page=self.page,
            template_html='<!DOCTYPE html><html><head></head><body>'
            '<h1 data-editable-id="hero-headline">Big Sale</h1></body></html>',
            annotation_map={"fields": [
                {"id": "hero-headline", "label": "Hero headline", "field_type": "text", "group": "Hero", "notes": ""},
            ]},
            field_values={"hero-headline": "Big Sale"},
        )
        self.page.draft_version = self.version
        self.page.save(update_fields=["draft_version"])

    def test_edit_screen_lists_annotated_fields(self):
        response = self.client.get(f"/pages/{self.page.id}/edit/", HTTP_HOST=self.HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hero headline")
        self.assertContains(response, 'data-field-id="hero-headline"')

    def test_preview_renders_current_field_value(self):
        self.version.field_values = {"hero-headline": "Huge Sale"}
        self.version.save(update_fields=["field_values"])
        response = self.client.get(f"/pages/{self.page.id}/preview/", HTTP_HOST=self.HOST)
        self.assertContains(response, "Huge Sale")

    def test_preview_includes_live_bridge_but_publish_render_does_not(self):
        from apps.pages.render import render_version

        response = self.client.get(f"/pages/{self.page.id}/preview/", HTTP_HOST=self.HOST)
        self.assertContains(response, "js/preview-bridge.js")
        published = render_version(self.version, mode="publish", page=self.page)
        self.assertNotIn("preview-bridge", published)

    def test_save_merges_editable_values(self):
        response = self.client.post(
            f"/pages/{self.page.id}/save/",
            data=json.dumps({"values": {"hero-headline": "New headline"}}),
            content_type="application/json",
            HTTP_HOST=self.HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.version.refresh_from_db()
        self.assertEqual(self.version.field_values["hero-headline"], "New headline")

    def test_save_ignores_unknown_field_ids(self):
        response = self.client.post(
            f"/pages/{self.page.id}/save/",
            data=json.dumps({"values": {"not-a-field": "junk"}}),
            content_type="application/json",
            HTTP_HOST=self.HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.version.refresh_from_db()
        self.assertNotIn("not-a-field", self.version.field_values)

    def test_save_rejects_malformed_body(self):
        response = self.client.post(
            f"/pages/{self.page.id}/save/",
            data="not json",
            content_type="application/json",
            HTTP_HOST=self.HOST,
        )
        self.assertEqual(response.status_code, 400)


@override_settings(
    APP_HOST_NAME="app.testbase.com",
    BASE_DOMAIN_NAME="testbase.com",
    ALLOWED_HOSTS=["app.testbase.com", ".testbase.com"],
)
class ReannotateTests(TestCase):
    HOST = "app.testbase.com"

    def setUp(self):
        user = get_user_model().objects.create_user(username="teammate", password="pass12345")
        self.client.force_login(user)
        site = Site.objects.create(subdomain="promo", name="Promo")
        self.page = Page.objects.create(site=site, name="Landing page", path="")
        self.version = PageVersion.objects.create(
            page=self.page,
            template_html='<!DOCTYPE html><html><head></head><body>'
            '<h1 data-editable-id="stale-id">Big Sale</h1></body></html>',
            annotation_map={"fields": []},
        )
        self.page.draft_version = self.version
        self.page.save(update_fields=["draft_version"])

    @override_settings(OPENAI_API_KEY="")
    def test_disabled_annotation_bounces_back_with_message(self):
        response = self.client.post(
            f"/pages/{self.page.id}/reannotate/", HTTP_HOST=self.HOST
        )
        self.assertRedirects(
            response, f"/pages/{self.page.id}/edit/", fetch_redirect_response=False
        )
        self.assertEqual(self.page.import_jobs.count(), 0)

    @override_settings(OPENAI_API_KEY="test-key")
    def test_enqueues_job_from_draft_html_without_stale_ids(self):
        response = self.client.post(
            f"/pages/{self.page.id}/reannotate/", HTTP_HOST=self.HOST
        )
        job = self.page.import_jobs.first()
        self.assertIsNotNone(job)
        self.assertRedirects(
            response,
            f"/pages/{self.page.id}/import/{job.id}/",
            fetch_redirect_response=False,
        )
        source = job.source
        self.assertIn("Big Sale", source.raw_html)  # current draft, not the original
        self.assertNotIn("data-editable-id", source.raw_html)

    def test_empty_fields_panel_offers_the_button_only_when_enabled(self):
        with override_settings(OPENAI_API_KEY=""):
            response = self.client.get(f"/pages/{self.page.id}/edit/", HTTP_HOST=self.HOST)
            self.assertContains(response, "OPENAI_API_KEY")
        with override_settings(OPENAI_API_KEY="test-key"):
            response = self.client.get(f"/pages/{self.page.id}/edit/", HTTP_HOST=self.HOST)
            self.assertContains(response, "Ask AI to find the editable parts")
