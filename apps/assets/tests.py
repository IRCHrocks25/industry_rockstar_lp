import shutil
import tempfile
from io import BytesIO
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from lxml import html as lxml_html

from .fetcher import FetchError, FetchResult, fetch_url, validate_url
from .models import Asset
from .rehost import Rehoster


def _addrinfo(ip):
    return [(2, 1, 6, "", (ip, 0))]


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b"", encoding="utf-8"):
        self.status_code = status
        self.headers = headers or {"Content-Type": "text/html"}
        self._body = body
        self.encoding = encoding

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308) and "Location" in self.headers

    is_permanent_redirect = False

    def iter_content(self, chunk_size):
        stream = BytesIO(self._body)
        while chunk := stream.read(chunk_size):
            yield chunk

    def close(self):
        pass


@mock.patch("apps.assets.fetcher.socket.getaddrinfo")
class ValidateUrlTests(SimpleTestCase):
    def test_rejects_non_http_schemes(self, gai):
        for url in ("ftp://x.com/a", "file:///etc/passwd", "gopher://x"):
            with self.assertRaises(FetchError):
                validate_url(url)
        gai.assert_not_called()

    def test_rejects_private_loopback_linklocal_metadata(self, gai):
        for ip in ("10.0.0.5", "192.168.1.1", "172.16.0.9", "127.0.0.1",
                   "169.254.169.254", "100.64.0.1", "0.0.0.0", "::1", "fd00::1"):
            gai.return_value = _addrinfo(ip)
            with self.assertRaises(FetchError, msg=ip):
                validate_url("http://evil.example.com/")

    def test_rejects_if_any_resolved_ip_is_blocked(self, gai):
        gai.return_value = _addrinfo("93.184.216.34") + _addrinfo("127.0.0.1")
        with self.assertRaises(FetchError):
            validate_url("http://mixed.example.com/")

    def test_accepts_global_address(self, gai):
        gai.return_value = _addrinfo("93.184.216.34")
        self.assertEqual(validate_url("https://ok.example.com/x").hostname, "ok.example.com")

    def test_rejects_unresolvable(self, gai):
        import socket as socket_mod

        gai.side_effect = socket_mod.gaierror
        with self.assertRaises(FetchError):
            validate_url("http://nope.invalid/")


@mock.patch("apps.assets.fetcher.socket.getaddrinfo", return_value=_addrinfo("93.184.216.34"))
@mock.patch("apps.assets.fetcher.requests.get")
class FetchUrlTests(SimpleTestCase):
    def test_fetches_content(self, get, gai):
        get.return_value = FakeResponse(body=b"<html>hi</html>")
        result = fetch_url("http://ok.example.com/")
        self.assertEqual(result.content, b"<html>hi</html>")
        self.assertEqual(result.content_type, "text/html")

    def test_follows_redirects_and_validates_each_hop(self, get, gai):
        get.side_effect = [
            FakeResponse(status=302, headers={"Location": "http://internal.example.com/x",
                                              "Content-Type": "text/html"}),
            FakeResponse(body=b"fine"),
        ]
        # Second hop resolves to a blocked address -> whole fetch fails.
        gai.side_effect = [_addrinfo("93.184.216.34"), _addrinfo("10.0.0.1")]
        with self.assertRaises(FetchError):
            fetch_url("http://ok.example.com/")

    def test_redirect_loop_bails(self, get, gai):
        get.return_value = FakeResponse(
            status=302, headers={"Location": "http://ok.example.com/", "Content-Type": "text/html"}
        )
        with self.assertRaises(FetchError):
            fetch_url("http://ok.example.com/")

    def test_size_cap(self, get, gai):
        get.return_value = FakeResponse(body=b"x" * 2048)
        with self.assertRaises(FetchError):
            fetch_url("http://ok.example.com/", max_bytes=1024)

    def test_content_type_allowlist(self, get, gai):
        get.return_value = FakeResponse(headers={"Content-Type": "application/zip"})
        with self.assertRaises(FetchError):
            fetch_url("http://ok.example.com/", allowed_types=("text/html",))

    def test_non_200_fails(self, get, gai):
        get.return_value = FakeResponse(status=404)
        with self.assertRaises(FetchError):
            fetch_url("http://ok.example.com/missing")


PNG = b"\x89PNG-fake-image-bytes"
JPG = b"\xff\xd8JPEG-fake-image-bytes"
CSS = b'.hero { background: url("bg.jpg"); }'


def fake_fetch(url, max_bytes=None, allowed_types=None):
    routes = {
        "https://cdn.ghl.example/a.png": (PNG, "image/png"),
        "https://cdn.ghl.example/a2x.png": (PNG + b"2x", "image/png"),
        "https://cdn.ghl.example/dupe.png": (PNG, "image/png"),
        "https://cdn.ghl.example/bg.jpg": (JPG, "image/jpeg"),
        "https://cdn.ghl.example/style.css": (CSS, "text/css"),
        "https://page.example.com/relative.png": (PNG + b"rel", "image/png"),
    }
    if url not in routes:
        raise FetchError(f"HTTP 404 fetching {url}")
    content, ctype = routes[url]
    return FetchResult(content=content, content_type=ctype, final_url=url, encoding="utf-8")


@mock.patch("apps.assets.rehost.fetch_url", side_effect=fake_fetch)
class RehostTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media = tempfile.mkdtemp()
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)
        super().tearDownClass()

    def _run(self, html, base_url=None):
        doc = lxml_html.document_fromstring(html)
        rehoster = Rehoster(base_url=base_url)
        warnings = rehoster.rehost_document(doc)
        return lxml_html.tostring(doc, encoding="unicode"), warnings

    def test_img_src_rewritten_and_asset_stored(self, _):
        out, warnings = self._run('<img src="https://cdn.ghl.example/a.png">')
        self.assertNotIn("cdn.ghl.example/a.png", out)
        self.assertIn("/media/assets/", out)
        self.assertEqual(Asset.objects.count(), 1)
        asset = Asset.objects.get()
        self.assertEqual(asset.content_type, "image/png")
        self.assertEqual(warnings, [])

    def test_identical_content_dedupes_to_one_asset(self, _):
        out, _w = self._run(
            '<img src="https://cdn.ghl.example/a.png"><img src="https://cdn.ghl.example/dupe.png">'
        )
        self.assertEqual(Asset.objects.count(), 1)

    def test_srcset_candidates_rewritten(self, _):
        out, _w = self._run(
            '<img srcset="https://cdn.ghl.example/a.png 1x, https://cdn.ghl.example/a2x.png 2x" src="https://cdn.ghl.example/a.png">'
        )
        self.assertNotIn("cdn.ghl.example", out)
        self.assertIn("1x", out)
        self.assertIn("2x", out)

    def test_inline_style_background_rewritten(self, _):
        out, _w = self._run(
            '<div style="background: url(https://cdn.ghl.example/bg.jpg) no-repeat;">x</div>'
        )
        self.assertNotIn("cdn.ghl.example", out)
        self.assertIn("/media/assets/", out)

    def test_style_block_rewritten(self, _):
        out, _w = self._run(
            "<style>.h { background-image: url('https://cdn.ghl.example/bg.jpg'); }</style><p>x</p>"
        )
        self.assertNotIn("cdn.ghl.example", out)

    def test_external_stylesheet_fetched_and_inner_urls_rehosted(self, _):
        out, warnings = self._run(
            '<link rel="stylesheet" href="https://cdn.ghl.example/style.css"><p>x</p>'
        )
        self.assertNotIn("cdn.ghl.example/style.css", out)
        self.assertEqual(warnings, [])
        css_asset = Asset.objects.get(content_type="text/css")
        from django.core.files.storage import default_storage

        stored_css = default_storage.open(css_asset.storage_key).read().decode()
        self.assertIn("/media/assets/", stored_css)  # bg.jpg inside the css was rehosted
        self.assertNotIn("bg.jpg", stored_css)

    def test_failed_asset_keeps_original_url_and_warns(self, _):
        out, warnings = self._run('<img src="https://cdn.ghl.example/missing.png">')
        self.assertIn("cdn.ghl.example/missing.png", out)
        self.assertEqual(len(warnings), 1)
        self.assertIn("missing.png", warnings[0])

    def test_relative_url_resolved_against_base(self, _):
        out, _w = self._run('<img src="relative.png">', base_url="https://page.example.com/lp")
        self.assertNotIn('src="relative.png"', out)
        self.assertIn("/media/assets/", out)

    def test_relative_url_without_base_left_alone(self, _):
        out, warnings = self._run('<img src="relative.png">')
        self.assertIn('src="relative.png"', out)
        self.assertEqual(warnings, [])

    def test_data_uri_left_alone(self, _):
        html = '<img src="data:image/png;base64,AAAA">'
        out, warnings = self._run(html)
        self.assertIn("data:image/png;base64,AAAA", out)
        self.assertEqual(Asset.objects.count(), 0)
