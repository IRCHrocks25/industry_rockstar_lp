"""Stripped DOM skeleton for the annotator (architecture.md §7 step 4).

Turns a stamped doc (every body element carries data-anno-tmp) into a compact,
indented outline: tag, temp id, classes, a couple of cheap hints (href/src/
countdown-like text), and truncated inner text. Scripts/styles and long
attributes never make it in, keeping the token count — and the model's
attention — on structure and copy.

Output is a plain string (or a list of chunk strings for very large pages),
NOT markup the model edits: it only reads it and returns temp-id references.
"""

import copy
import re

from . import backgrounds

MAX_TEXT = 100  # chars of direct text per node
MAX_SKELETON_CHARS = 20_000  # ~5k tokens; larger pages chunk by body children
COUNTDOWN_RE = re.compile(r"\b\d{1,3}\s*:\s*\d{2}(?:\s*:\s*\d{2})?\b")
SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}


def build_skeletons(doc) -> list[str]:
    """One skeleton string when the page fits the budget; otherwise split into
    chunks by the body's top-level children (each chunk stays self-contained so
    its temp ids still resolve). Returns [] if there's nothing to annotate."""
    bodies = doc.xpath("//body")  # doc.body raises when there's no <body>
    if not bodies:
        return []
    # Nodes whose background image comes from a <style> rule — hint them so the
    # annotator can label them even though the copy has no inline bg-image.
    bg_ids = set(backgrounds.index_stylesheet_backgrounds(doc).keys())
    working = copy.deepcopy(bodies[0])

    whole = "\n".join(_render(working, 0, bg_ids))
    if not whole.strip():
        return []
    if len(whole) <= MAX_SKELETON_CHARS:
        return [whole]

    chunks, current, size = [], [], 0
    for child in working:
        if not isinstance(child.tag, str) or child.tag in SKIP_TAGS:
            continue
        lines = _render(child, 0, bg_ids)
        block = "\n".join(lines)
        if current and size + len(block) > MAX_SKELETON_CHARS:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def _render(el, depth, bg_ids) -> list[str]:
    if not isinstance(el.tag, str) or el.tag in SKIP_TAGS:
        return []
    lines = [_line(el, depth, bg_ids)]
    for child in el:
        lines.extend(_render(child, depth + 1, bg_ids))
    return lines


def _line(el, depth, bg_ids) -> str:
    parts = [el.tag]
    tmp = el.get("data-anno-tmp")
    if tmp:
        parts.append(f"t={tmp}")
    cls = (el.get("class") or "").split()
    if cls:
        parts.append("." + ".".join(cls[:4]))  # a few classes are plenty of signal

    if el.tag == "a" and el.get("href"):
        parts.append(f"href={_clip(el.get('href'), 60)}")
    if el.tag in ("img", "source"):
        if el.get("src"):
            parts.append(f"src={_clip(el.get('src'), 60)}")
        if el.get("alt"):
            parts.append(f'alt="{_clip(el.get("alt"), 40)}"')
        if el.get("srcset"):
            parts.append("srcset")
    if el.tag == "form":
        parts.append(f"action={_clip(el.get('action') or '', 60)}")
    style = (el.get("style") or "").lower()
    inline_bg = "background" in style and "url(" in style
    if inline_bg or el.get("data-anno-tmp") in bg_ids:
        parts.append("bg-image")

    text = _direct_text(el)
    if text:
        if COUNTDOWN_RE.search(text):
            parts.append("countdown-like")
        parts.append(f'"{text}"')

    return ("  " * depth) + " ".join(parts)


def _direct_text(el) -> str:
    """The element's own text plus the tails between its children — the copy
    that visually belongs to this node, not its descendants' text."""
    pieces = [el.text or ""]
    for child in el:
        pieces.append(child.tail or "")
    collapsed = " ".join(" ".join(pieces).split())
    return _clip(collapsed, MAX_TEXT)


def _clip(value: str, limit: int) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"
