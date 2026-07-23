"""Deterministic render engine (architecture.md §10). Pure lxml patch, no AI.

Same path for editor preview (mode='edit', annotation attributes kept) and
publish (mode='publish', all annotation attributes stripped). Field values are
injected into their data-editable-id nodes according to field type; plain text
is escaped by lxml at serialization, richtext fragments are re-sanitized.
"""

import re

from lxml import etree
from lxml import html as lxml_html

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", re.IGNORECASE)


def render_version(version, mode="publish", page=None):
    page = page or version.page
    doc = lxml_html.document_fromstring(version.template_html)
    values = version.field_values or {}
    for field in (version.annotation_map or {}).get("fields", []):
        node = _find(doc, field["id"])
        if node is None:
            continue  # template drifted; never crash a render over one field
        value = values.get(field["id"])
        if value is None:
            continue  # untouched field keeps the imported content
        _apply(node, field.get("field_type", "text"), value)
    _apply_seo(doc, page)
    _apply_forms(doc, page)
    if mode == "publish":
        _strip_annotations(doc)
    return lxml_html.tostring(doc, doctype="<!DOCTYPE html>", encoding="unicode")


def _apply_forms(doc, page):
    """Point managed <form>s at the /_submit proxy + add honeypot. Lazy import
    keeps the render engine decoupled from the forms app (architecture.md §11)."""
    from apps.forms.integration import apply_forms

    apply_forms(doc, page)


def _find(doc, editable_id):
    nodes = doc.xpath("//*[@data-editable-id=$eid]", eid=editable_id)
    return nodes[0] if nodes else None


def _apply(node, field_type, value):
    if field_type in ("text", "link_text"):
        _set_text(node, str(value))
    elif field_type == "richtext":
        _set_inner_html(node, str(value))
    elif field_type == "image":
        if isinstance(value, str):
            value = {"src": value}
        if value.get("src"):
            node.set("src", value["src"])
            if node.get("srcset"):
                del node.attrib["srcset"]  # replaced image: candidates no longer apply
        if value.get("alt") is not None:
            node.set("alt", value["alt"])
    elif field_type == "background_image":
        src = value.get("src") if isinstance(value, dict) else value
        if src:
            _set_background(node, src)
    elif field_type == "link_url":
        if value:
            node.set("href", str(value))
    elif field_type == "cta":
        if isinstance(value, dict):
            if value.get("url"):
                node.set("href", value["url"])
            if value.get("text") is not None:
                _set_text(node, value["text"])
    # Unknown/later types (countdown, form, …) are handled by their own phases.


def _set_text(node, text):
    for child in list(node):
        node.remove(child)
    node.text = text


def _set_inner_html(node, fragment_html):
    for child in list(node):
        node.remove(child)
    node.text = None
    if not fragment_html.strip():
        return
    for frag in lxml_html.fragments_fromstring(fragment_html):
        if isinstance(frag, str):
            if len(node):
                node[-1].tail = (node[-1].tail or "") + frag
            else:
                node.text = (node.text or "") + frag
        elif isinstance(frag.tag, str) and frag.tag == "script":
            continue  # a bare script fragment is dropped outright
        else:
            _sanitize_fragment(frag)
            node.append(frag)


def _sanitize_fragment(frag):
    """Same hygiene as import (§12): richtext values may carry markup, never scripts."""
    for el in frag.xpath(".//script"):
        el.drop_tree()
    for el in frag.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in list(el.attrib):
            if attr.lower().startswith("on"):
                del el.attrib[attr]
        for attr in ("href", "src"):
            v = el.get(attr)
            if v and v.strip().lower().startswith("javascript:"):
                el.set(attr, "#")


def _set_background(node, src):
    style = node.get("style") or ""
    if CSS_URL_RE.search(style):
        style = CSS_URL_RE.sub(f'url("{src}")', style, count=1)
    else:
        prefix = style.rstrip().rstrip(";") + "; " if style.strip() else ""
        style = f"{prefix}background-image: url(\"{src}\")"
    node.set("style", style)


def _apply_seo(doc, page):
    head = doc.head
    if head is None:
        return
    if page.seo_title:
        title = doc.find(".//title")
        if title is None:
            title = etree.SubElement(head, "title")
        title.text = page.seo_title
    if page.seo_description:
        metas = doc.xpath("//meta[@name='description']")
        meta = metas[0] if metas else etree.SubElement(head, "meta", name="description")
        meta.set("content", page.seo_description)


def _strip_annotations(doc):
    for attr in ("data-anno-tmp", "data-editable-id"):
        for el in doc.xpath(f"//*[@{attr}]"):
            del el.attrib[attr]
