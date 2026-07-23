import re
from unittest import mock, skipUnless

from django.test import TestCase
from lxml import html as lxml_html

from apps.pages.models import ImportJob, ImportSource, Page
from apps.pages.render import _set_background
from apps.sites.models import Site

from . import backgrounds, materialize, service, skeleton
from .client import AnnotationError, AnnotationResult

STAMPED_HTML = """<!DOCTYPE html>
<html><head><title>Promo</title></head>
<body>
  <section data-anno-tmp="sec1">
    <h1 data-anno-tmp="h1" class="hero">Big Sale</h1>
    <p data-anno-tmp="p1">Hurry <b data-anno-tmp="b1">now</b></p>
    <a data-anno-tmp="a1" href="https://buy.example/x">Buy now</a>
    <img data-anno-tmp="img1" src="https://cdn.example/pic.jpg" alt="Product">
  </section>
</body></html>"""


class SkeletonTests(TestCase):
    def test_skeleton_carries_temp_ids_and_text(self):
        doc = lxml_html.document_fromstring(STAMPED_HTML)
        chunks = skeleton.build_skeletons(doc)
        self.assertEqual(len(chunks), 1)
        text = chunks[0]
        self.assertIn("t=h1", text)
        self.assertIn("Big Sale", text)
        self.assertIn("src=", text)  # img hint present
        self.assertIn("href=", text)  # link hint present

    def test_scripts_and_styles_are_excluded(self):
        html = STAMPED_HTML.replace(
            "<h1", "<script data-anno-tmp='s'>evil()</script><h1"
        )
        doc = lxml_html.document_fromstring(html)
        text = skeleton.build_skeletons(doc)[0]
        self.assertNotIn("evil()", text)

    def test_large_page_is_chunked(self):
        blocks = "".join(
            f'<div data-anno-tmp="d{i}"><p data-anno-tmp="p{i}">{"copy " * 40}</p></div>'
            for i in range(60)
        )
        doc = lxml_html.document_fromstring(f"<html><body>{blocks}</body></html>")
        # Text is truncated hard, so force chunking with a small budget rather
        # than an implausibly huge page.
        with mock.patch.object(skeleton, "MAX_SKELETON_CHARS", 500):
            chunks = skeleton.build_skeletons(doc)
        self.assertGreater(len(chunks), 1)
        # Chunking must not lose nodes: every stamped id appears in some chunk.
        joined = "\n".join(chunks)
        for i in range(60):
            self.assertIn(f"t=d{i}", joined)


class MaterializeTests(TestCase):
    def _doc(self):
        return lxml_html.document_fromstring(STAMPED_HTML)

    def test_maps_ids_extracts_values_and_strips_temp_ids(self):
        doc = self._doc()
        fields = [
            {"tmp_id": "h1", "label": "Hero headline", "field_type": "text", "group": "Hero", "notes": ""},
            {"tmp_id": "a1", "label": "Buy button", "field_type": "cta", "group": "Hero", "notes": ""},
            {"tmp_id": "img1", "label": "Product image", "field_type": "image", "group": "Hero", "notes": ""},
        ]
        annotation_map, values = materialize.materialize(doc, fields)

        ids = [f["id"] for f in annotation_map["fields"]]
        self.assertEqual(ids, ["hero-headline", "buy-button", "product-image"])
        self.assertEqual(values["hero-headline"], "Big Sale")
        self.assertEqual(values["buy-button"], {"text": "Buy now", "url": "https://buy.example/x"})
        self.assertEqual(values["product-image"], {"src": "https://cdn.example/pic.jpg", "alt": "Product"})

        # Chosen nodes carry stable ids; no temp ids survive anywhere.
        self.assertIsNotNone(doc.xpath("//*[@data-editable-id='hero-headline']"))
        self.assertEqual(doc.xpath("//*[@data-anno-tmp]"), [])

    def test_hallucinated_temp_id_is_skipped(self):
        doc = self._doc()
        fields = [
            {"tmp_id": "does-not-exist", "label": "Ghost", "field_type": "text", "group": "X", "notes": ""},
            {"tmp_id": "h1", "label": "Headline", "field_type": "text", "group": "Hero", "notes": ""},
        ]
        annotation_map, _ = materialize.materialize(doc, fields)
        self.assertEqual([f["id"] for f in annotation_map["fields"]], ["headline"])

    def test_same_temp_id_twice_yields_one_field(self):
        doc = self._doc()
        fields = [
            {"tmp_id": "h1", "label": "Headline", "field_type": "text", "group": "Hero", "notes": ""},
            {"tmp_id": "h1", "label": "Headline again", "field_type": "cta", "group": "Hero", "notes": ""},
        ]
        annotation_map, values = materialize.materialize(doc, fields)
        self.assertEqual([f["id"] for f in annotation_map["fields"]], ["headline"])
        # The node carries exactly the one id we kept — no orphaned editable id.
        self.assertEqual(len(doc.xpath("//*[@data-editable-id]")), 1)
        self.assertEqual(list(values.keys()), ["headline"])

    def test_duplicate_labels_get_unique_ids(self):
        doc = self._doc()
        fields = [
            {"tmp_id": "h1", "label": "Heading", "field_type": "text", "group": "A", "notes": ""},
            {"tmp_id": "p1", "label": "Heading", "field_type": "text", "group": "A", "notes": ""},
        ]
        annotation_map, _ = materialize.materialize(doc, fields)
        self.assertEqual([f["id"] for f in annotation_map["fields"]], ["heading", "heading-2"])


class BackgroundTests(TestCase):
    def test_inline_background_is_left_alone(self):
        node = lxml_html.fragment_fromstring('<div style="background: url(\'a.png\')"></div>')
        backgrounds.ensure_inline_background(node, "background: url('b.png')")
        self.assertIn("a.png", node.get("style"))
        self.assertNotIn("b.png", node.get("style"))

    def test_stylesheet_declaration_is_inlined_when_absent(self):
        node = lxml_html.fragment_fromstring('<section class="hero"></section>')
        backgrounds.ensure_inline_background(node, "background: url('hero.png') center/cover")
        self.assertIn("url('hero.png')", node.get("style"))

    def test_editing_multilayer_background_preserves_other_layers(self):
        node = lxml_html.fragment_fromstring(
            "<section style=\"background: linear-gradient(#000, #111), "
            "url('old.png') center/cover, radial-gradient(#222, #333)\"></section>"
        )
        _set_background(node, "new.png")
        style = node.get("style")
        self.assertIn("new.png", style)
        self.assertNotIn("old.png", style)
        self.assertIn("linear-gradient", style)  # overlay layers survive the swap
        self.assertIn("radial-gradient", style)
        self.assertIn("center/cover", style)

    @skipUnless(backgrounds.HAS_CSSSELECT, "cssselect not installed")
    def test_stylesheet_background_indexed_by_temp_id(self):
        html = (
            "<html><head><style>.hero { background: url('h.png') center/cover; }</style></head>"
            '<body><section class="hero" data-anno-tmp="s1"><h1 data-anno-tmp="h1">Hi</h1></section>'
            "</body></html>"
        )
        doc = lxml_html.document_fromstring(html)
        index = backgrounds.index_stylesheet_backgrounds(doc)
        self.assertIn("s1", index)
        self.assertIn("h.png", index["s1"])
        self.assertNotIn("h1", index)

    @skipUnless(backgrounds.HAS_CSSSELECT, "cssselect not installed")
    def test_materialize_makes_stylesheet_background_editable(self):
        html = (
            "<html><head><style>.hero { background: url('h.png') center/cover; }</style></head>"
            '<body><section class="hero" data-anno-tmp="s1"></section></body></html>'
        )
        doc = lxml_html.document_fromstring(html)
        fields = [{"tmp_id": "s1", "label": "Hero background", "field_type": "background_image",
                   "group": "Hero", "notes": ""}]
        _, values = materialize.materialize(doc, fields)
        node = doc.xpath("//*[@data-editable-id='hero-background']")[0]
        self.assertIn("h.png", node.get("style"))  # inlined -> editable
        self.assertEqual(values["hero-background"], {"src": "h.png"})

    @skipUnless(backgrounds.HAS_CSSSELECT, "cssselect not installed")
    def test_skeleton_hints_stylesheet_background(self):
        html = (
            "<html><head><style>.hero { background: url('h.png') center/cover; }</style></head>"
            '<body><section class="hero" data-anno-tmp="s1">Book now</section></body></html>'
        )
        doc = lxml_html.document_fromstring(html)
        text = skeleton.build_skeletons(doc)[0]
        hero_line = [ln for ln in text.splitlines() if "t=s1" in ln][0]
        self.assertIn("bg-image", hero_line)


class ServiceTests(TestCase):
    def test_annotate_html_produces_editable_template(self):
        def stub(skeletons):
            return AnnotationResult(
                fields=[{"tmp_id": "h1", "label": "Hero headline", "field_type": "text", "group": "Hero", "notes": ""}],
                tokens=123,
            )

        outcome = service.annotate_html(STAMPED_HTML, annotator=stub)
        self.assertIn('data-editable-id="hero-headline"', outcome.template_html)
        self.assertNotIn("data-anno-tmp", outcome.template_html)
        self.assertEqual(outcome.field_values["hero-headline"], "Big Sale")
        self.assertEqual(outcome.tokens, 123)
        self.assertEqual(outcome.field_count, 1)

    def test_no_body_returns_original_without_calling_model(self):
        calls = []

        def stub(skeletons):
            calls.append(1)
            return AnnotationResult()

        outcome = service.annotate_html("<html><head></head></html>", annotator=stub)
        self.assertEqual(calls, [])
        self.assertEqual(outcome.field_count, 0)


class ImportAnnotationTests(TestCase):
    """The annotation pass wired into the import task (real skeleton + materialize,
    only the model call stubbed)."""

    def setUp(self):
        site = Site.objects.create(subdomain="promo", name="Promo")
        self.page = Page.objects.create(site=site, name="Landing page", path="")

    def _run_with_stub(self, annotator):
        from apps.annotation import service as service_module

        original = service_module._default_annotator
        service_module._default_annotator = annotator
        try:
            from apps.importer import tasks

            source = ImportSource.objects.create(
                page=self.page, raw_html="<h1 class='hero'>Big Sale</h1>", source_type="paste"
            )
            job = ImportJob.objects.create(page=self.page, source=source)
            tasks.run_import(str(job.id))
            return ImportJob.objects.get(id=job.id)
        finally:
            service_module._default_annotator = original

    def test_import_annotates_and_records_tokens(self):
        def stub(skeletons):
            # Grab the real (random) temp id the h1 got stamped with.
            match = re.search(r"h1 t=(\w+)", skeletons[0])
            self.assertIsNotNone(match)
            return AnnotationResult(
                fields=[{"tmp_id": match.group(1), "label": "Hero headline",
                         "field_type": "text", "group": "Hero", "notes": ""}],
                tokens=250,
            )

        with self.settings(OPENAI_API_KEY="sk-test", OPENAI_COST_CENTS_PER_1K=1.0):
            job = self._run_with_stub(stub)

        job.page.refresh_from_db()
        version = job.page.draft_version
        self.assertEqual(job.status, ImportJob.Status.SUCCEEDED)
        self.assertEqual(job.llm_tokens, 250)
        self.assertEqual([f["id"] for f in version.annotation_map["fields"]], ["hero-headline"])
        self.assertIn('data-editable-id="hero-headline"', version.template_html)

    def test_model_failure_is_non_fatal(self):
        def boom(skeletons):
            raise AnnotationError("openai exploded")

        with self.settings(OPENAI_API_KEY="sk-test"):
            job = self._run_with_stub(boom)

        job.page.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.SUCCEEDED)  # import still lands
        self.assertEqual(job.page.draft_version.annotation_map, {"fields": []})
        self.assertTrue(any("annotation skipped" in w.lower() for w in job.warnings))
