"""SSRF-guarded HTTP fetcher (architecture.md §12).

Used for every outbound fetch: import-by-URL, asset rehosting and (Phase 2)
webhook forwarding. Blocks non-global addresses (private, loopback,
link-local, cloud-metadata, shared ranges) and re-validates every redirect
hop. Residual DNS-rebinding TOCTOU risk (resolve-then-connect) is accepted
for v1 — sources are the client's own pages, not untrusted user input.
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests

MAX_REDIRECTS = 5
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
TIMEOUT = (5, 20)  # connect, read
USER_AGENT = "IndustryRockstarImporter/1.0"


class FetchError(Exception):
    """Any reason a URL may not / could not be fetched. Message is user-safe."""


@dataclass
class FetchResult:
    content: bytes
    content_type: str
    final_url: str
    encoding: str | None

    @property
    def text(self):
        return self.content.decode(self.encoding or "utf-8", errors="replace")


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("Only http(s) URLs can be fetched.")
    if not parsed.hostname:
        raise FetchError("That URL has no host name.")
    _validate_host(parsed.hostname)
    return parsed


def _validate_host(hostname):
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise FetchError(f"Could not resolve {hostname}.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # is_global rejects private, loopback, link-local (incl. 169.254.169.254
        # metadata), shared 100.64/10, reserved and unspecified ranges.
        if not ip.is_global:
            raise FetchError(f"{hostname} resolves to a blocked address.")


def fetch_url(url, max_bytes=DEFAULT_MAX_BYTES, allowed_types=None):
    """Fetch a URL with SSRF validation on every hop and a hard size cap.

    allowed_types: optional iterable of content-type prefixes, e.g.
    ("text/html",) or ("image/",).
    """
    for _ in range(MAX_REDIRECTS + 1):
        validate_url(url)
        response = requests.get(
            url,
            stream=True,
            allow_redirects=False,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        try:
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                if not location:
                    raise FetchError("Redirect without a Location header.")
                url = urljoin(url, location)
                continue
            if response.status_code != 200:
                raise FetchError(f"Got HTTP {response.status_code} fetching that URL.")
            content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if allowed_types and not any(content_type.startswith(t) for t in allowed_types):
                raise FetchError(f"Unexpected content type: {content_type or 'unknown'}.")
            chunks, total = [], 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise FetchError("That file is too large to import.")
                chunks.append(chunk)
            return FetchResult(
                content=b"".join(chunks),
                content_type=content_type,
                final_url=url,
                encoding=response.encoding,
            )
        finally:
            response.close()
    raise FetchError("Too many redirects.")
