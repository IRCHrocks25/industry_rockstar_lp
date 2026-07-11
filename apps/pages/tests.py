from django.test import TestCase

from apps.sites.models import Site

from .models import Page, PageVersion
from .render import render_version

TEMPLATE = """<!DOCTYPE html>
<html><head><title>Old title</title></head>
<body data-anno-tmp="b0">
  <h1 data-anno-tmp="a1" data-editable-id="hero-headline">Old headline</h1>
  <p data-anno-tmp="a2" data-editable-id="hero-copy">Old <b>copy</b></p>
  <img data-anno-tmp="a3" data-editable-id="hero-image" src="/media/old.png" srcset="/media/old.png 1x" alt="old">
  <a data-anno-tmp="a4" data-editable-id="cta-button" href="/old">Buy now</a>
  <div data-anno-tmp="a5" data-editable-id="hero-bg" style="background: url('/media/old-bg.jpg') center;">x</div>
</body></html>"""

FIELDS = [
    {"id": "hero-headline", "label": "Hero headline", "field_type": "text", "group": "Hero"},
    {"id": "hero-copy", "label": "Hero copy", "field_type": "richtext", "group": "Hero"},
    {"id": "hero-image", "label": "Hero image", "field_type": "image", "group": "Hero"},
    {"id": "cta-button", "label": "CTA button", "field_type": "cta", "group": "Hero"},
    {"id": "hero-bg", "label": "Hero background", "field_type": "background_image", "group": "Hero"},
]


class RenderVersionTests(TestCase):
    def setUp(self):
        site = Site.objects.create(subdomain="promo", name="Promo")
        self.page = Page.objects.create(site=site, name="LP", path="")

    def _version(self, values, fields=FIELDS):
        return PageVersion.objects.create(
            page=self.page,
            template_html=TEMPLATE,
            annotation_map={"fields": fields},
            field_values=values,
        )

    def test_text_value_is_injected_and_escaped(self):
        version = self._version({"hero-headline": 'Deal <script>alert("x")</script> & more'})
        out = render_version(version)
        self.assertIn("Deal &lt;script&gt;", out)
        self.assertIn("&amp; more", out)
        self.assertNotIn("<script>", out)

    def test_richtext_replaces_inner_html_and_sanitizes(self):
        version = self._version(
            {"hero-copy": 'New <em>copy</em> <a href="javascript:x" onclick="p()">link</a><script>bad()</script>'}
        )
        out = render_version(version)
        self.assertIn("<em>copy</em>", out)
        self.assertNotIn("onclick", out)
        self.assertNotIn("javascript:", out)
        self.assertNotIn("<script>", out)
        self.assertNotIn("Old", out.split("<body")[1])  # old copy fully replaced

    def test_image_sets_src_alt_and_drops_stale_srcset(self):
        version = self._version({"hero-image": {"src": "/media/assets/ab/new.png", "alt": "New alt"}})
        out = render_version(version)
        self.assertIn('src="/media/assets/ab/new.png"', out)
        self.assertIn('alt="New alt"', out)
        self.assertNotIn("srcset", out)

    def test_cta_updates_href_and_text(self):
        version = self._version({"cta-button": {"url": "/thank-you", "text": "Claim it"}})
        out = render_version(version)
        self.assertIn('href="/thank-you"', out)
        self.assertIn(">Claim it</a>", out)

    def test_background_image_rewrites_style_url(self):
        version = self._version({"hero-bg": "/media/assets/cd/new-bg.jpg"})
        out = render_version(version)
        self.assertIn("new-bg.jpg", out)
        self.assertNotIn("old-bg.jpg", out)

    def test_untouched_fields_keep_imported_content(self):
        version = self._version({})
        out = render_version(version)
        self.assertIn("Old headline", out)
        self.assertIn("<b>copy</b>", out)

    def test_missing_node_is_tolerated(self):
        fields = FIELDS + [{"id": "ghost", "label": "Ghost", "field_type": "text", "group": "X"}]
        version = self._version({"ghost": "boo"}, fields=fields)
        out = render_version(version)  # must not raise
        self.assertNotIn("boo", out)

    def test_publish_mode_strips_annotation_attributes(self):
        version = self._version({"hero-headline": "New"})
        out = render_version(version, mode="publish")
        self.assertNotIn("data-editable-id", out)
        self.assertNotIn("data-anno-tmp", out)

    def test_edit_mode_keeps_annotation_attributes(self):
        version = self._version({})
        out = render_version(version, mode="edit")
        self.assertIn('data-editable-id="hero-headline"', out)
        self.assertIn("data-anno-tmp", out)

    def test_seo_title_and_description_injected(self):
        self.page.seo_title = "Big Promo — 50% off"
        self.page.seo_description = "Limited time offer."
        self.page.save()
        version = self._version({})
        out = render_version(version)
        self.assertIn("<title>Big Promo — 50% off</title>", out)
        self.assertIn('name="description"', out)
        self.assertIn('content="Limited time offer."', out)
