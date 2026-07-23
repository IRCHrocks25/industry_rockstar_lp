"""Stylesheet background-image coverage.

Custom-authored pages set their hero/section backgrounds in a `<style>` block,
not inline — e.g. `.final-cta { background: url('hero.png') center/cover }`. This
resolves those rules back to the nodes they style so:

  1. the skeleton can hint the annotator that the node has a background image, and
  2. materialize can inline the declaration onto the node, making it editable.

Inlining is what makes editing work AND safe: an inline style outranks the
stylesheet, and the render engine replaces only the `url(...)` token, so gradient
and overlay layers in a multi-layer background survive an image swap.

Requires `cssselect` (via lxml) to match selectors; without it this degrades to a
no-op and pages fall back to inline-only background support.
"""

import re

try:  # optional dep — full power when present, graceful no-op when not
    import cssselect as _cssselect  # noqa: F401

    HAS_CSSSELECT = True
except ImportError:
    HAS_CSSSELECT = False

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", re.IGNORECASE)
# One CSS rule: `selector-group { declarations }`. Good enough for real
# stylesheets; @media/@font-face blocks are skipped by the url()-in-background
# requirement below.
_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)
# A background / background-image declaration whose value contains a url().
_BG_DECL_RE = re.compile(
    r"\b(background(?:-image)?)\s*:\s*([^;{}]*url\([^;{}]*\)[^;{}]*)", re.IGNORECASE
)
# Pseudo-elements/classes cssselect can't map to real nodes — strip them so the
# host element still matches (`.card::before` -> `.card`).
_PSEUDO_RE = re.compile(r"::?[a-zA-Z][\w-]*(?:\([^)]*\))?")


def index_stylesheet_backgrounds(doc) -> dict[str, str]:
    """Map `data-anno-tmp` id -> the full background declaration (e.g.
    "background: url('x.png') center/cover") for nodes whose background image is
    defined in an inline <style> block. Later rules win. {} if cssselect is
    missing or there are no <style> blocks."""
    if not HAS_CSSSELECT:
        return {}
    styles = doc.xpath("//style")
    if not styles:
        return {}

    index: dict[str, str] = {}
    for style in styles:
        css = _strip_comments(style.text or "")
        for selector_group, body in _RULE_RE.findall(css):
            match = _BG_DECL_RE.search(body)
            if not match:
                continue
            declaration = f"{match.group(1).strip()}: {match.group(2).strip()}"
            for raw_selector in selector_group.split(","):
                selector = _PSEUDO_RE.sub("", raw_selector).strip()
                if not selector:
                    continue
                try:
                    nodes = doc.cssselect(selector)
                except Exception:
                    continue  # unsupported/exotic selector — skip, don't crash
                for node in nodes:
                    tmp = node.get("data-anno-tmp")
                    if tmp:
                        index[tmp] = declaration
    return index


def ensure_inline_background(node, declaration):
    """Make a node's background image editable: if it has no inline url() yet but
    a stylesheet gives it one, copy that declaration inline. No-op when the node
    already carries an inline background image."""
    style = node.get("style") or ""
    if CSS_URL_RE.search(style):
        return  # already an inline image to edit
    if not declaration:
        return
    prefix = style.rstrip().rstrip(";") + "; " if style.strip() else ""
    node.set("style", prefix + declaration)


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
