"""Materialize LLM output into the template (architecture.md §7 steps 6-7).

Deterministic, no AI: map each returned temp id back to its node, swap the
throwaway data-anno-tmp for a stable, collision-safe data-editable-id, extract
the node's current content as the field's initial value, and strip every
leftover temp id. Hallucinated ids and unknown field types degrade quietly —
the worst case stays "a human fixes one field", never a broken page.
"""

import re

from django.utils.text import slugify
from lxml import html as lxml_html

from . import backgrounds
from .schema import FIELD_TYPES

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", re.IGNORECASE)


def materialize(doc, fields: list[dict]) -> tuple[dict, dict]:
    """Mutate `doc` in place; return (annotation_map, field_values).

    annotation_map = {"fields": [{id, label, field_type, group, notes}, ...]}
    field_values   = {editable_id: initial_value} for the types we can extract.
    """
    annotation_fields: list[dict] = []
    field_values: dict = {}
    used_ids: set[str] = set()
    seen_tmp: set[str] = set()
    # Stylesheet-defined backgrounds, resolved before we strip temp ids.
    bg_index = backgrounds.index_stylesheet_backgrounds(doc)

    for raw in fields:
        tmp_id = (raw or {}).get("tmp_id")
        if not tmp_id or tmp_id in seen_tmp:
            continue  # skip blanks and any node the model named more than once
        seen_tmp.add(tmp_id)
        node = _find_by_tmp(doc, tmp_id)
        if node is None:
            continue  # model referenced a node that isn't there — skip it

        field_type = raw.get("field_type")
        if field_type not in FIELD_TYPES:
            field_type = "text"
        label = (raw.get("label") or "").strip() or field_type.replace("_", " ").title()
        editable_id = _unique_id(label, field_type, used_ids)

        node.set("data-editable-id", editable_id)
        # Inline a stylesheet background so it becomes editable (before we drop
        # the temp id the index is keyed on).
        if field_type == "background_image":
            backgrounds.ensure_inline_background(node, bg_index.get(tmp_id))
        if "data-anno-tmp" in node.attrib:
            del node.attrib["data-anno-tmp"]

        annotation_fields.append(
            {
                "id": editable_id,
                "label": label,
                "field_type": field_type,
                "group": (raw.get("group") or "Content").strip() or "Content",
                "notes": (raw.get("notes") or "").strip(),
            }
        )
        value = extract_value(node, field_type)
        if value is not None:
            field_values[editable_id] = value

    _strip_remaining_tmp(doc)
    return {"fields": annotation_fields}, field_values


def _find_by_tmp(doc, tmp_id):
    nodes = doc.xpath("//*[@data-anno-tmp=$t]", t=tmp_id)
    return nodes[0] if nodes else None


def _unique_id(label, field_type, used_ids) -> str:
    base = slugify(label) or slugify(field_type) or "field"
    candidate = base
    n = 2
    while candidate in used_ids:
        candidate = f"{base}-{n}"
        n += 1
    used_ids.add(candidate)
    return candidate


def extract_value(node, field_type):
    """Read a node's current content as the field's initial value. Public:
    the template library (apps.library.parser) extracts defaults with the
    same shapes the render engine patches."""
    if field_type in ("text", "link_text"):
        return _inner_text(node)
    if field_type == "richtext":
        return _inner_html(node)
    if field_type == "image":
        return {"src": node.get("src", ""), "alt": node.get("alt", "")}
    if field_type == "background_image":
        match = CSS_URL_RE.search(node.get("style") or "")
        return {"src": match.group(2).strip()} if match else {"src": ""}
    if field_type == "link_url":
        return node.get("href", "")
    if field_type == "cta":
        return {"text": _inner_text(node), "url": node.get("href", "")}
    # countdown / form / color / visibility / meta_* carry no editable value yet
    # (their own phases own that); the annotation entry is enough for now.
    return None


def _inner_text(node) -> str:
    return " ".join("".join(node.itertext()).split())


def _inner_html(node) -> str:
    parts = [node.text or ""]
    for child in node:
        parts.append(lxml_html.tostring(child, encoding="unicode"))
    return "".join(parts).strip()


def _strip_remaining_tmp(doc):
    for el in doc.xpath("//*[@data-anno-tmp]"):
        del el.attrib["data-anno-tmp"]
