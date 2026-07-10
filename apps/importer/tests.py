from django.test import TestCase
from lxml import html as lxml_html

from apps.pages.models import ImportJob, ImportSource, Page
from apps.sites.models import Site

from . import pipeline, tasks

GHL_LIKE_HTML = """
<!DOCTYPE html>
<html><head>
  <title>Promo</title>
  <script src="https://cdn.evil.example/track.js"></script>
  <base href="https://cdn.ghl.example/">
</head>
<body onload="boom()">
  <h1 class="hero">Big Sale</h1>
  <a href="javascript:alert(1)">Click</a>
  <script>inline()</script>
  <p>Hurry <b>now</b></p>
</body></html>
"""


class PipelineTests(TestCase):
    def test_sanitize_strips_scripts_base_and_handlers(self):
        template, warnings = pipeline.process_html(GHL_LIKE_HTML)
        self.assertNotIn("<script", template)
        self.assertNotIn("<base", template)
        self.assertNotIn("onload", template)
        self.assertNotIn("javascript:", template)
        self.assertEqual(warnings, [])

    def test_stamp_gives_every_body_element_a_unique_tmp_id(self):
        template, _ = pipeline.process_html(GHL_LIKE_HTML)
        doc = lxml_html.document_fromstring(template)
        stamped = doc.xpath("//body//*[@data-anno-tmp] | //body[@data-anno-tmp]")
        body_elements = [el for el in doc.body.iter() if isinstance(el.tag, str)]
        self.assertEqual(len(stamped), len(body_elements))
        ids = [el.get("data-anno-tmp") for el in stamped]
        self.assertEqual(len(ids), len(set(ids)))

    def test_content_and_structure_survive(self):
        template, _ = pipeline.process_html(GHL_LIKE_HTML)
        self.assertIn("Big Sale", template)
        self.assertIn(">now</b>", template)  # inline structure kept (stamped, not rewritten)
        self.assertIn("<!DOCTYPE html>", template)

    def test_partial_html_fragment_is_wrapped(self):
        template, _ = pipeline.process_html("<h1>Just a heading</h1>")
        self.assertIn("<body", template)
        self.assertIn("Just a heading", template)

    def test_empty_import_raises(self):
        with self.assertRaises(ValueError):
            pipeline.process_html("   ")


class RunImportTests(TestCase):
    def setUp(self):
        site = Site.objects.create(subdomain="promo", name="Promo")
        self.page = Page.objects.create(site=site, name="Landing page", path="")

    def _job(self, **source_kwargs):
        source = ImportSource.objects.create(page=self.page, **source_kwargs)
        return ImportJob.objects.create(page=self.page, source=source)

    def test_successful_paste_import_creates_draft_version(self):
        job = self._job(raw_html=GHL_LIKE_HTML, source_type="paste")
        tasks.run_import(str(job.id))
        job.refresh_from_db()
        self.page.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.SUCCEEDED)
        self.assertIsNotNone(job.finished_at)
        self.assertIsNotNone(self.page.draft_version)
        self.assertIn("data-anno-tmp", self.page.draft_version.template_html)
        self.assertNotIn("<script", self.page.draft_version.template_html)

    def test_failed_import_records_error_without_raising(self):
        job = self._job(raw_html="", source_type="paste")
        tasks.run_import(str(job.id))
        job.refresh_from_db()
        self.assertEqual(job.status, ImportJob.Status.FAILED)
        self.assertIn("empty", job.error.lower())
        self.page.refresh_from_db()
        self.assertIsNone(self.page.draft_version)

    def test_succeeded_job_is_not_rerun(self):
        job = self._job(raw_html=GHL_LIKE_HTML, source_type="paste")
        tasks.run_import(str(job.id))
        version_id = Page.objects.get(id=self.page.id).draft_version_id
        tasks.run_import(str(job.id))  # duplicate delivery
        self.assertEqual(Page.objects.get(id=self.page.id).draft_version_id, version_id)
        self.assertEqual(self.page.versions.count(), 1)
