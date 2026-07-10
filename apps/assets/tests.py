from io import BytesIO
from unittest import mock

from django.test import SimpleTestCase

from .fetcher import FetchError, fetch_url, validate_url


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
