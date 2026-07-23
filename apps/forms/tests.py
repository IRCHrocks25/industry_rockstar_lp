from unittest import mock

from django.test import TestCase, override_settings
from lxml import html as lxml_html

from apps.pages.models import Page
from apps.pages.render import render_version
from apps.sites.models import Site

from . import integration, tasks, webhook
from .models import Form, Submission

PUBLISHING = dict(
    APP_HOST_NAME="app.testbase.com",
    BASE_DOMAIN_NAME="testbase.com",
    ALLOWED_HOSTS=["app.testbase.com", "testbase.com", ".testbase.com"],
)


class FormModelTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(subdomain="promo", name="Promo")
        self.lp = Page.objects.create(site=self.site, name="Landing", path="")
        self.ty = Page.objects.create(site=self.site, name="Thanks", path="thank-you")

    def test_success_destination_prefers_page(self):
        form = Form.objects.create(page=self.lp, editable_id="f1", success_page=self.ty)
        self.assertEqual(form.success_destination(), "/thank-you")

    def test_success_destination_falls_back_to_url_then_root(self):
        form = Form.objects.create(page=self.lp, editable_id="f1", success_url="https://x.example/ok")
        self.assertEqual(form.success_destination(), "https://x.example/ok")
        form.success_url = ""
        self.assertEqual(form.success_destination(), "/")


class DetectionTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(subdomain="promo", name="Promo")
        self.page = Page.objects.create(site=self.site, name="Landing", path="")

    def test_detect_creates_form_records_and_stamps_ids(self):
        html = "<html><body><form><input name='email'></form><form id='newsletter'></form></body></html>"
        out = integration.detect_and_sync(self.page, html)
        self.assertEqual(self.page.forms.count(), 2)
        self.assertIn("data-editable-id", out)
        # The named form keeps its name as the id; the anonymous one gets form-1.
        ids = set(self.page.forms.values_list("editable_id", flat=True))
        self.assertEqual(ids, {"form-1", "newsletter"})

    def test_detection_is_idempotent(self):
        html = "<html><body><form id='lead'></form></body></html>"
        integration.detect_and_sync(self.page, html)
        integration.detect_and_sync(self.page, html)
        self.assertEqual(self.page.forms.count(), 1)

    def test_no_forms_is_a_noop(self):
        html = "<html><body><h1>No forms here</h1></body></html>"
        out = integration.detect_and_sync(self.page, html)
        self.assertEqual(self.page.forms.count(), 0)
        self.assertEqual(out, html)


class RenderFormTests(TestCase):
    def setUp(self):
        self.site = Site.objects.create(subdomain="promo", name="Promo")
        self.page = Page.objects.create(site=self.site, name="Landing", path="")
        from apps.pages.models import PageVersion

        self.version = PageVersion.objects.create(
            page=self.page,
            template_html='<!DOCTYPE html><html><head></head><body>'
            '<form data-editable-id="lead"><input name="email"></form></body></html>',
            annotation_map={"fields": []},
        )
        self.form = Form.objects.create(page=self.page, editable_id="lead")

    def test_render_rewrites_action_and_injects_honeypot(self):
        html = render_version(self.version, mode="publish", page=self.page)
        doc = lxml_html.document_fromstring(html)
        node = doc.xpath("//form")[0]
        self.assertEqual(node.get("action"), f"/_submit/{self.form.id}")
        self.assertEqual(node.get("method"), "post")
        self.assertTrue(node.xpath(f".//input[@name='{integration.HONEYPOT_FIELD}']"))


@override_settings(**PUBLISHING)
class SubmitEndpointTests(TestCase):
    HOST = "promo.testbase.com"

    def setUp(self):
        self.site = Site.objects.create(subdomain="promo", name="Promo")
        self.lp = Page.objects.create(site=self.site, name="Landing", path="")
        self.ty = Page.objects.create(site=self.site, name="Thanks", path="thank-you")
        self.form = Form.objects.create(
            page=self.lp, editable_id="lead", webhook_url="https://hook.example/x", success_page=self.ty
        )

    def _url(self):
        return f"/_submit/{self.form.id}"

    @mock.patch("apps.forms.views.enqueue_forward")
    def test_resilient_stores_redirects_and_enqueues(self, enqueue):
        response = self.client.post(self._url(), {"email": "a@b.com"}, HTTP_HOST=self.HOST)
        self.assertRedirects(response, "/thank-you", fetch_redirect_response=False)
        sub = Submission.objects.get()
        self.assertEqual(sub.payload, {"email": "a@b.com"})
        self.assertEqual(sub.webhook_status, Submission.WebhookStatus.PENDING)
        enqueue.assert_called_once()

    @mock.patch("apps.forms.views.enqueue_forward")
    def test_honeypot_is_accepted_but_dropped(self, enqueue):
        response = self.client.post(
            self._url(), {"email": "a@b.com", integration.HONEYPOT_FIELD: "bot"}, HTTP_HOST=self.HOST
        )
        self.assertRedirects(response, "/thank-you", fetch_redirect_response=False)
        self.assertEqual(Submission.objects.count(), 0)
        enqueue.assert_not_called()

    def test_no_webhook_marks_skipped(self):
        self.form.webhook_url = ""
        self.form.save()
        response = self.client.post(self._url(), {"email": "a@b.com"}, HTTP_HOST=self.HOST)
        self.assertRedirects(response, "/thank-you", fetch_redirect_response=False)
        self.assertEqual(Submission.objects.get().webhook_status, Submission.WebhookStatus.SKIPPED)

    @mock.patch("apps.forms.views.post_webhook")
    def test_gated_success_redirects_to_destination(self, post):
        self.form.gate_redirect_on_success = True
        self.form.save()
        response = self.client.post(self._url(), {"email": "a@b.com"}, HTTP_HOST=self.HOST)
        self.assertRedirects(response, "/thank-you", fetch_redirect_response=False)
        self.assertEqual(Submission.objects.get().webhook_status, Submission.WebhookStatus.SUCCEEDED)
        post.assert_called_once()

    @mock.patch("apps.forms.views.post_webhook", side_effect=webhook.WebhookError("boom"))
    def test_gated_failure_bounces_back_with_error(self, post):
        self.form.gate_redirect_on_success = True
        self.form.save()
        response = self.client.post(self._url(), {"email": "a@b.com"}, HTTP_HOST=self.HOST)
        self.assertRedirects(response, "/?form_error=1", fetch_redirect_response=False)
        self.assertEqual(Submission.objects.get().webhook_status, Submission.WebhookStatus.FAILED)

    def test_oversized_body_rejected(self):
        with override_settings(SUBMIT_MAX_BYTES=10):
            response = self.client.post(self._url(), {"email": "a-very-long-value@example.com"}, HTTP_HOST=self.HOST)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Submission.objects.count(), 0)

    def test_unknown_form_404s(self):
        response = self.client.post(
            "/_submit/00000000-0000-0000-0000-000000000000", {"x": "1"}, HTTP_HOST=self.HOST
        )
        self.assertEqual(response.status_code, 404)


class WebhookTests(TestCase):
    @override_settings(WEBHOOK_ALLOWED_HOSTS=["hook.allowed.example"])
    @mock.patch("apps.forms.webhook.validate_url")
    def test_allowlist_blocks_other_hosts(self, validate):
        validate.return_value = mock.Mock(hostname="evil.example")
        with self.assertRaises(webhook.WebhookError):
            webhook.post_webhook("https://evil.example/x", {"a": 1})

    @mock.patch("apps.forms.webhook.requests.post")
    @mock.patch("apps.forms.webhook.validate_url")
    def test_non_2xx_raises(self, validate, post):
        validate.return_value = mock.Mock(hostname="hook.example")
        post.return_value = mock.Mock(status_code=500)
        with self.assertRaises(webhook.WebhookError):
            webhook.post_webhook("https://hook.example/x", {"a": 1})

    @mock.patch("apps.forms.webhook.requests.post")
    @mock.patch("apps.forms.webhook.validate_url")
    def test_success_returns_status(self, validate, post):
        validate.return_value = mock.Mock(hostname="hook.example")
        post.return_value = mock.Mock(status_code=200)
        self.assertEqual(webhook.post_webhook("https://hook.example/x", {"a": 1}), 200)


class ForwardTaskTests(TestCase):
    def setUp(self):
        site = Site.objects.create(subdomain="promo", name="Promo")
        page = Page.objects.create(site=site, name="Landing", path="")
        self.form = Form.objects.create(page=page, editable_id="lead", webhook_url="https://hook.example/x")
        self.sub = Submission.objects.create(form=self.form, payload={"email": "a@b.com"})

    @mock.patch("apps.forms.tasks.post_webhook")
    def test_success_marks_delivered(self, post):
        tasks.forward_submission(str(self.sub.id))
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.webhook_status, Submission.WebhookStatus.SUCCEEDED)
        self.assertEqual(self.sub.attempts, 1)

    @mock.patch("apps.forms.tasks.post_webhook", side_effect=webhook.WebhookError("down"))
    def test_failure_records_and_reraises_for_retry(self, post):
        with self.assertRaises(webhook.WebhookError):
            tasks.forward_submission(str(self.sub.id))
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.webhook_status, Submission.WebhookStatus.FAILED)
        self.assertIn("down", self.sub.last_error)
