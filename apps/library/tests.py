"""Template library: DSL parsing, schema derivation, and site provisioning."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.forms.models import Form
from apps.pages.render import render_version
from apps.sites.models import Site

from . import parser
from .models import SiteTemplate, TemplatePage
from .provision import provision_site

ANNOTATED = """
<!DOCTYPE html>
<html><head><title>t</title><script>alert(1)</script></head><body>
<section data-section="hero" data-label="Top banner">
  <h1 data-edit="hero.title" data-type="text" data-label="Headline">Hello world</h1>
  <a href="#go" data-edit="hero.cta" data-type="cta" data-label="Button">Go now</a>
  <img src="/x.png" alt="pic" data-edit="hero.photo" data-type="image">
</section>
<div data-edit="about.body" data-type="richtext" data-group="About">
  <p>Some <strong>rich</strong> copy</p>
</div>
<form id="signup" data-success-path="thank-you"><input name="email"></form>
</body></html>
"""


class ParserTests(TestCase):
    def test_build_derives_schema_and_defaults(self):
        html, annotation_map, values = parser.build(ANNOTATED)
        fields = {f["id"]: f for f in annotation_map["fields"]}

        self.assertEqual(set(fields), {"hero.title", "hero.cta", "hero.photo", "about.body"})
        self.assertEqual(fields["hero.title"]["label"], "Headline")
        self.assertEqual(fields["hero.title"]["group"], "Top banner")
        self.assertEqual(fields["hero.photo"]["label"], "Photo")  # derived from id
        self.assertEqual(fields["about.body"]["group"], "About")

        self.assertEqual(values["hero.title"], "Hello world")
        self.assertEqual(values["hero.cta"], {"text": "Go now", "url": "#go"})
        self.assertEqual(values["hero.photo"], {"src": "/x.png", "alt": "pic"})
        self.assertIn("<strong>rich</strong>", values["about.body"])

        # Built HTML: stable ids in, DSL + scripts out.
        self.assertIn('data-editable-id="hero.title"', html)
        self.assertNotIn("data-edit=", html)
        self.assertNotIn("data-section=", html)
        self.assertNotIn("<script", html)
        self.assertIn('data-success-path="thank-you"', html)  # provisioning reads this

    def test_duplicate_and_bad_ids_reported_together(self):
        bad = """<html><body>
          <p data-edit="a.one">x</p><p data-edit="a.one">y</p>
          <p data-edit="Bad Id!">z</p>
          <p data-edit="a.two" data-type="nope">w</p>
        </body></html>"""
        with self.assertRaises(parser.TemplateSourceError) as ctx:
            parser.build(bad)
        message = str(ctx.exception)
        self.assertIn("more than once", message)
        self.assertIn("Bad Id!", message)
        self.assertIn("nope", message)

    def test_model_save_rebuilds_derived_fields(self):
        template = SiteTemplate.objects.create(name="T")
        page = TemplatePage.objects.create(template=template, name="LP", html_source=ANNOTATED)
        self.assertEqual(len(page.annotation_map["fields"]), 4)
        self.assertIn('data-editable-id="hero.title"', page.template_html)

        page.html_source = "<html><body><h1 data-edit='only.one'>Hi</h1></body></html>"
        page.save()
        self.assertEqual([f["id"] for f in page.annotation_map["fields"]], ["only.one"])


class ProvisionTests(TestCase):
    def setUp(self):
        self.template = SiteTemplate.objects.create(name="Funnel")
        TemplatePage.objects.create(
            template=self.template, name="Landing page", path="", sort=0, html_source=ANNOTATED
        )
        TemplatePage.objects.create(
            template=self.template, name="Thank you", path="thank-you", sort=1,
            html_source="<html><body><h1 data-edit='hero.title'>Thanks</h1></body></html>",
        )
        self.site = Site.objects.create(name="Acme", subdomain="acme")

    def test_provision_creates_pages_versions_and_wires_forms(self):
        homepage = provision_site(self.site, self.template)

        self.assertEqual(self.site.pages.count(), 2)
        self.assertEqual(homepage.path, "")
        for page in self.site.pages.all():
            self.assertIsNotNone(page.draft_version)
            self.assertIn("template", page.draft_version.note)

        form = Form.objects.get(page=homepage)
        self.assertEqual(form.success_page, self.site.pages.get(path="thank-you"))

    def test_provisioned_page_renders_defaults_and_edits(self):
        homepage = provision_site(self.site, self.template)
        version = homepage.draft_version

        html = render_version(version, mode="publish", page=homepage)
        self.assertIn("Hello world", html)
        self.assertNotIn("data-editable-id", html)  # publish strips annotations

        version.field_values["hero.title"] = "New headline"
        version.save()
        self.assertIn("New headline", render_version(version, mode="publish", page=homepage))


@override_settings(
    APP_HOST_NAME="app.testbase.com",
    BASE_DOMAIN_NAME="testbase.com",
    ALLOWED_HOSTS=["app.testbase.com", ".testbase.com"],
)
class NewSiteScreenTests(TestCase):
    HOST = "app.testbase.com"

    def setUp(self):
        user = get_user_model().objects.create_user(username="teammate", password="pass12345")
        self.client.force_login(user)
        self.template = SiteTemplate.objects.create(name="Funnel")
        TemplatePage.objects.create(
            template=self.template, name="Landing page", html_source=ANNOTATED
        )

    def test_gallery_shown(self):
        response = self.client.get("/sites/new/", HTTP_HOST=self.HOST)
        self.assertContains(response, "Start from")
        self.assertContains(response, "Funnel")
        self.assertContains(response, "Start blank")
        self.assertContains(response, "Paste your own HTML")

    def test_create_with_template_redirects_to_editor(self):
        response = self.client.post(
            "/sites/new/",
            {"name": "Acme", "subdomain": "acme", "start": str(self.template.id)},
            HTTP_HOST=self.HOST,
        )
        site = Site.objects.get(subdomain="acme")
        homepage = site.pages.get(path="")
        self.assertRedirects(
            response, f"/pages/{homepage.id}/edit/", fetch_redirect_response=False
        )
        self.assertIsNotNone(homepage.draft_version)

    def test_create_blank_keeps_old_behavior(self):
        response = self.client.post(
            "/sites/new/",
            {"name": "Acme", "subdomain": "acme", "start": "blank"},
            HTTP_HOST=self.HOST,
        )
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(Site.objects.get(subdomain="acme").pages.count(), 0)

    def test_create_with_pasted_html_starts_an_import(self):
        response = self.client.post(
            "/sites/new/",
            {
                "name": "Acme", "subdomain": "acme", "start": "paste",
                "html_text": "<html><body><h1>My GHL page</h1></body></html>",
            },
            HTTP_HOST=self.HOST,
        )
        site = Site.objects.get(subdomain="acme")
        page = site.pages.get(path="")
        job = page.import_jobs.first()
        self.assertIsNotNone(job)
        self.assertRedirects(
            response, f"/pages/{page.id}/import/{job.id}/", fetch_redirect_response=False
        )
        self.assertEqual(page.import_sources.first().raw_html.strip()[:5], "<html")

    def test_paste_without_html_is_rejected(self):
        response = self.client.post(
            "/sites/new/",
            {"name": "Acme", "subdomain": "acme", "start": "paste", "html_text": ""},
            HTTP_HOST=self.HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paste the page HTML")
        self.assertFalse(Site.objects.filter(subdomain="acme").exists())

    def test_template_preview_serves_html(self):
        response = self.client.get(
            f"/templates/{self.template.id}/preview/", HTTP_HOST=self.HOST
        )
        self.assertContains(response, "Hello world")


@override_settings(
    APP_HOST_NAME="app.testbase.com",
    BASE_DOMAIN_NAME="testbase.com",
    ALLOWED_HOSTS=["app.testbase.com", ".testbase.com"],
)
class TemplatesScreenTests(TestCase):
    HOST = "app.testbase.com"

    def setUp(self):
        user = get_user_model().objects.create_user(username="teammate", password="pass12345")
        self.client.force_login(user)

    def test_create_annotated_template_is_ready_immediately(self):
        response = self.client.post(
            "/templates/new/",
            {"name": "My design", "description": "d", "landing_text": ANNOTATED},
            HTTP_HOST=self.HOST,
        )
        self.assertRedirects(response, "/templates/", fetch_redirect_response=False)
        template = SiteTemplate.objects.get(name="My design")
        page = template.pages.get(path="")
        self.assertEqual(page.status, TemplatePage.Status.READY)
        self.assertEqual(len(page.annotation_map["fields"]), 4)
        self.assertIn(template, SiteTemplate.gallery())

    def test_create_plain_html_template_goes_to_annotation(self):
        self.client.post(
            "/templates/new/",
            {"name": "Raw GHL", "landing_text": "<html><body><h1>Plain</h1></body></html>"},
            HTTP_HOST=self.HOST,
        )
        page = SiteTemplate.objects.get(name="Raw GHL").pages.get(path="")
        self.assertEqual(page.status, TemplatePage.Status.ANNOTATING)
        # Still annotating -> not offered on the New site screen.
        self.assertNotIn(page.template, SiteTemplate.gallery())

        # The task (annotation disabled in tests) finishes it without fields.
        from .tasks import annotate_template_page

        annotate_template_page(str(page.id))
        page.refresh_from_db()
        self.assertEqual(page.status, TemplatePage.Status.READY)
        self.assertIn("Plain", page.template_html)
        self.assertIn(page.template, SiteTemplate.gallery())

    def test_create_with_thank_you_page(self):
        self.client.post(
            "/templates/new/",
            {
                "name": "Two pager",
                "landing_text": ANNOTATED,
                "thanks_text": "<html><body><h1 data-edit='hero.title'>Thanks</h1></body></html>",
            },
            HTTP_HOST=self.HOST,
        )
        template = SiteTemplate.objects.get(name="Two pager")
        self.assertEqual(template.pages.count(), 2)
        self.assertEqual(template.pages.get(path="thank-you").status, TemplatePage.Status.READY)

    def test_bad_annotations_rejected_on_the_form(self):
        response = self.client.post(
            "/templates/new/",
            {"name": "Broken", "landing_text": "<html><body><p data-edit='x'>a</p><p data-edit='x'>b</p></body></html>"},
            HTTP_HOST=self.HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "more than once")
        self.assertFalse(SiteTemplate.objects.filter(name="Broken").exists())

    def test_delete_removes_template_but_not_sites(self):
        template = SiteTemplate.objects.create(name="Doomed")
        TemplatePage.objects.create(template=template, name="LP", html_source=ANNOTATED)
        site = Site.objects.create(name="Keeper", subdomain="keeper")
        provision_site(site, template)

        response = self.client.post(
            f"/templates/{template.id}/delete/", HTTP_HOST=self.HOST
        )
        self.assertRedirects(response, "/templates/", fetch_redirect_response=False)
        self.assertFalse(SiteTemplate.objects.filter(id=template.id).exists())
        page = site.pages.get(path="")
        self.assertIsNotNone(page.draft_version)  # provisioned copy untouched

    def test_failed_page_marks_template_not_ready(self):
        template = SiteTemplate.objects.create(name="Sad")
        page = TemplatePage(template=template, name="LP", html_source="   ")
        page.status = TemplatePage.Status.ANNOTATING
        page.save()

        from .tasks import annotate_template_page

        annotate_template_page(str(page.id))
        page.refresh_from_db()
        self.assertEqual(page.status, TemplatePage.Status.FAILED)
        self.assertNotIn(template, SiteTemplate.gallery())
