import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.pages.models import Page, PageVersion, PublishRecord
from apps.sites.models import Site

from .service import publish_page

TEST_MEDIA = tempfile.mkdtemp(prefix="ir-test-media-")


@override_settings(
    APP_HOST_NAME="app.testbase.com",
    BASE_DOMAIN_NAME="testbase.com",
    ALLOWED_HOSTS=["app.testbase.com", "testbase.com", ".testbase.com"],
    MEDIA_ROOT=TEST_MEDIA,
)
class PublishingPlaneTests(TestCase):
    """Full request-cycle checks through HostRouterMiddleware."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA, ignore_errors=True)

    def setUp(self):
        self.site = Site.objects.create(subdomain="promo", name="Promo Funnel")

    def _page_with_draft(self, path="", headline="Big Sale"):
        page = Page.objects.create(site=self.site, name="Landing page", path=path)
        version = PageVersion.objects.create(
            page=page,
            template_html="<!DOCTYPE html><html><head></head><body>"
            f'<h1 data-editable-id="hero">{headline}</h1></body></html>',
            annotation_map={"fields": [
                {"id": "hero", "label": "Headline", "field_type": "text", "group": "Hero", "notes": ""},
            ]},
            field_values={},
        )
        page.draft_version = version
        page.save(update_fields=["draft_version"])
        return page

    def test_site_root_serves_placeholder_until_published(self):
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

    def test_publish_snapshots_and_serves(self):
        page = self._page_with_draft()
        record = publish_page(page)

        page.refresh_from_db()
        self.assertIsNotNone(page.published_version)
        self.assertNotEqual(page.published_version_id, page.draft_version_id)
        self.assertEqual(PublishRecord.objects.filter(page=page).count(), 1)
        self.assertTrue(record.rendered_key)

        response = self.client.get("/", HTTP_HOST="promo.testbase.com")
        self.assertContains(response, "Big Sale")
        self.assertNotContains(response, "data-editable-id")  # publish strips annotations

    def test_draft_edits_after_publish_stay_private_until_republished(self):
        page = self._page_with_draft()
        publish_page(page)

        draft = page.draft_version
        draft.field_values = {"hero": "New unpublished headline"}
        draft.save(update_fields=["field_values"])

        response = self.client.get("/", HTTP_HOST="promo.testbase.com")
        self.assertContains(response, "Big Sale")
        self.assertNotContains(response, "New unpublished headline")

        publish_page(page)
        response = self.client.get("/", HTTP_HOST="promo.testbase.com")
        self.assertContains(response, "New unpublished headline")

    def test_non_homepage_path_serves_and_unpublished_404s(self):
        thanks = self._page_with_draft(path="thank-you", headline="Thanks!")
        publish_page(thanks)

        response = self.client.get("/thank-you/", HTTP_HOST="promo.testbase.com")
        self.assertContains(response, "Thanks!")
        response = self.client.get("/nope/", HTTP_HOST="promo.testbase.com")
        self.assertEqual(response.status_code, 404)


@override_settings(
    APP_HOST_NAME="app.testbase.com",
    BASE_DOMAIN_NAME="testbase.com",
    BASE_DOMAIN="testbase.com",
    ALLOWED_HOSTS=["app.testbase.com", "testbase.com", ".testbase.com"],
    MEDIA_ROOT=TEST_MEDIA,
)
class PublishFromEditorTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="teammate", password="pass12345")
        self.client.force_login(user)
        self.site = Site.objects.create(subdomain="promo", name="Promo Funnel")
        self.page = Page.objects.create(site=self.site, name="Landing page", path="")
        version = PageVersion.objects.create(
            page=self.page,
            template_html="<!DOCTYPE html><html><head></head><body><h1>Hello</h1></body></html>",
        )
        self.page.draft_version = version
        self.page.save(update_fields=["draft_version"])

    def test_publish_button_flow(self):
        response = self.client.post(
            f"/pages/{self.page.id}/publish/", HTTP_HOST="app.testbase.com"
        )
        self.assertRedirects(
            response, f"/pages/{self.page.id}/edit/", fetch_redirect_response=False
        )
        self.page.refresh_from_db()
        self.assertTrue(self.page.is_published)

        live = self.client.get("/", HTTP_HOST="promo.testbase.com")
        self.assertContains(live, "Hello")

    def test_editor_shows_publish_button_and_live_link_state(self):
        response = self.client.get(f"/pages/{self.page.id}/edit/", HTTP_HOST="app.testbase.com")
        self.assertContains(response, "Publish")
        self.assertNotContains(response, "Publish changes")
        self.assertNotContains(response, "View live")

        self.client.post(f"/pages/{self.page.id}/publish/", HTTP_HOST="app.testbase.com")
        response = self.client.get(f"/pages/{self.page.id}/edit/", HTTP_HOST="app.testbase.com")
        self.assertContains(response, "Publish changes")
        self.assertContains(response, "View live")
        self.assertContains(response, "promo.testbase.com")
