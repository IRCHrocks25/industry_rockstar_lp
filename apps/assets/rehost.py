"""Asset rehosting (architecture.md §7 step 2).

Downloads every asset the imported page references — <img src>, srcset,
inline style url(), <style> blocks and external stylesheets (including
url() refs inside the CSS) — stores them deduped by sha256 via the Django
storage API, and rewrites the DOM to point at our copies.

A single failed asset never fails the import: the original URL is kept and
a human-readable warning is recorded on the ImportJob.
"""

import hashlib
import mimetypes
import re
from urllib.parse import urljoin, urlparse

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .fetcher import FetchError, fetch_url
from .models import Asset

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", re.IGNORECASE)

MAX_ASSET_BYTES = 10 * 1024 * 1024
IMAGE_TYPES = ("image/",)
CSS_TYPES = ("text/css", "text/plain")  # some CDNs serve CSS as text/plain

EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "text/css": ".css",
    "font/woff": ".woff",
    "font/woff2": ".woff2",
    "font/ttf": ".ttf",
}

SKIP_PREFIXES = ("data:", "blob:", "#", "mailto:", "tel:", "about:")


class Rehoster:
    def __init__(self, base_url=None):
        self.base_url = base_url
        self.warnings = []
        self._url_cache = {}  # absolute original URL -> rehosted URL (or None)

    # --- document walk -------------------------------------------------------

    def rehost_document(self, doc):
        for el in doc.xpath("//img[@src]"):
            new = self._rehost(el.get("src"), IMAGE_TYPES)
            if new:
                el.set("src", new)
        for el in doc.xpath("//img[@srcset] | //source[@srcset]"):
            el.set("srcset", self._rewrite_srcset(el.get("srcset")))
        for el in doc.xpath("//*[@style]"):
            el.set("style", self._rewrite_css_text(el.get("style"), self.base_url))
        for el in doc.xpath("//style"):
            if el.text:
                el.text = self._rewrite_css_text(el.text, self.base_url)
        for el in doc.xpath("//link[@rel='stylesheet' and @href]"):
            new = self._rehost_stylesheet(el.get("href"))
            if new:
                el.set("href", new)
        return self.warnings

    # --- pieces ----------------------------------------------------------------

    def _rewrite_srcset(self, srcset):
        parts = []
        for candidate in srcset.split(","):
            candidate = candidate.strip()
            if not candidate:
                continue
            bits = candidate.split(None, 1)
            new = self._rehost(bits[0], IMAGE_TYPES)
            bits[0] = new or bits[0]
            parts.append(" ".join(bits))
        return ", ".join(parts)

    def _rewrite_css_text(self, css_text, css_base):
        def replace(match):
            original = match.group(2).strip()
            new = self._rehost(original, None, base=css_base)
            return f'url("{new or original}")'

        return CSS_URL_RE.sub(replace, css_text)

    def _rehost_stylesheet(self, href):
        absolute = self._absolute(href, self.base_url)
        if not absolute:
            return None
        try:
            result = fetch_url(absolute, max_bytes=MAX_ASSET_BYTES, allowed_types=CSS_TYPES)
        except FetchError as exc:
            self.warnings.append(f"Stylesheet kept at original URL ({href}): {exc}")
            return None
        # Rewrite url() refs inside the CSS relative to the stylesheet itself.
        css_text = self._rewrite_css_text(result.text, result.final_url)
        return self._store(css_text.encode("utf-8"), "text/css", absolute)

    def _rehost(self, raw_url, allowed_types, base=None):
        absolute = self._absolute(raw_url, base or self.base_url)
        if not absolute:
            return None
        if absolute in self._url_cache:
            return self._url_cache[absolute]
        try:
            result = fetch_url(absolute, max_bytes=MAX_ASSET_BYTES, allowed_types=allowed_types)
            new_url = self._store(result.content, result.content_type, absolute)
        except FetchError as exc:
            self.warnings.append(f"Asset kept at original URL ({raw_url}): {exc}")
            new_url = None
        self._url_cache[absolute] = new_url
        return new_url

    def _absolute(self, url, base):
        if not url:
            return None
        url = url.strip()
        if url.lower().startswith(SKIP_PREFIXES):
            return None
        if urlparse(url).scheme in ("http", "https"):
            return url
        if base:
            joined = urljoin(base, url)
            if urlparse(joined).scheme in ("http", "https"):
                return joined
        # Relative URL with no base to resolve against (pasted HTML): leave it.
        return None

    def _store(self, content, content_type, original_url):
        sha = hashlib.sha256(content).hexdigest()
        asset = Asset.objects.filter(sha256=sha).first()
        if asset is None:
            ext = EXT_BY_TYPE.get(content_type) or mimetypes.guess_extension(content_type) or ""
            key = f"assets/{sha[:2]}/{sha}{ext}"
            key = default_storage.save(key, ContentFile(content))
            asset = Asset.objects.create(
                sha256=sha,
                storage_key=key,
                original_url=original_url[:5000],
                content_type=content_type,
                bytes=len(content),
            )
        return default_storage.url(asset.storage_key)
