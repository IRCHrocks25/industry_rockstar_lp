"""Deterministic import pipeline steps (architecture.md §7, no AI).

parse -> sanitize -> (rehost assets) -> stamp temp ids -> serialize.
All DOM mutation is lxml; nothing here ever calls a model or the network
except the asset rehost step, which takes an injected fetch function.
"""

import uuid

from lxml import etree
from lxml import html as lxml_html


def parse(raw_html: str):
    """Parse (possibly partial) HTML into a full document tree."""
    if not raw_html or not raw_html.strip():
        raise ValueError("The import was empty.")
    return lxml_html.document_fromstring(raw_html)


def sanitize(doc):
    """Strip active content per §12: imported HTML keeps its look, loses its
    scripts. Pixels/GTM come back later as managed script fields (Phase 5)."""
    for el in doc.xpath("//script"):
        el.drop_tree()
    for el in doc.xpath("//base"):
        el.drop_tree()
    for el in doc.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in list(el.attrib):
            if attr.lower().startswith("on"):
                del el.attrib[attr]
        for attr in ("href", "src"):
            value = el.get(attr)
            if value and value.strip().lower().startswith("javascript:"):
                el.set(attr, "#")


def stamp(doc):
    """Give every body element a data-anno-tmp id — the handle both manual
    annotation (Phase 1) and the LLM skeleton (Phase 3) use to reference
    nodes without touching markup structure."""
    seen = set()
    body = doc.body
    for el in body.iter():
        if not isinstance(el.tag, str):
            continue
        tmp_id = uuid.uuid4().hex[:8]
        while tmp_id in seen:
            tmp_id = uuid.uuid4().hex[:8]
        seen.add(tmp_id)
        el.set("data-anno-tmp", tmp_id)


def serialize(doc) -> str:
    return lxml_html.tostring(doc, doctype="<!DOCTYPE html>", encoding="unicode")


def process_html(raw_html: str, rehost=None) -> tuple[str, list[str]]:
    """Full pipeline. `rehost` is an optional callable(doc) -> warnings list,
    injected so the asset step stays independently testable."""
    doc = parse(raw_html)
    sanitize(doc)
    warnings = rehost(doc) if rehost else []
    stamp(doc)
    return serialize(doc), warnings
