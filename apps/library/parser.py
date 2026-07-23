"""Template annotation DSL → the same (template_html, annotation_map,
field_values) triple the import pipeline produces (architecture.md §17).

A template author marks editable slots directly in the HTML:

    <section data-section="hero" data-label="Welcome banner">
      <h1 data-edit="hero.title" data-type="text" data-label="Headline">…</h1>
      <a  data-edit="hero.cta"   data-type="cta"  data-label="Button">…</a>
    </section>

The parser never invents fields the author didn't tag. `data-edit` becomes the
stable `data-editable-id` the render engine patches, the field's default value
is extracted from the markup itself, and every DSL attribute is stripped from
the built HTML so nothing leaks to published pages.
"""

import re

from apps.annotation.materialize import extract_value
from apps.annotation.schema import EDITABLE_FIELD_TYPES
from apps.importer import pipeline

# section.field style ids: lowercase, digits, dots/dashes/underscores.
FIELD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")

HAS_DSL_RE = re.compile(r"data-edit\s*=")


def has_annotations(html_source: str) -> bool:
    """Cheap routing check: DSL-annotated HTML builds instantly via build();
    plain HTML (e.g. a GHL export) goes through the AI annotation task."""
    return bool(HAS_DSL_RE.search(html_source or ""))

# Every attribute the DSL owns; all are removed from the built template HTML.
DSL_ATTRIBUTES = (
    "data-edit",
    "data-type",
    "data-label",
    "data-notes",
    "data-section",
    "data-icon",
    "data-group",
)


class TemplateSourceError(ValueError):
    """The annotated HTML is malformed — surfaced verbatim to the author."""


def build(html_source: str) -> tuple[str, dict, dict]:
    """Derive (template_html, annotation_map, default_values) from annotated
    HTML. Raises TemplateSourceError listing every problem at once, so a
    template author fixes one round-trip, not one error per save."""
    try:
        doc = pipeline.parse(html_source)
    except ValueError as exc:
        raise TemplateSourceError(str(exc))
    pipeline.sanitize(doc)  # same hygiene as imports (§12): no scripts, no on*

    fields: list[dict] = []
    values: dict = {}
    seen: set[str] = set()
    errors: list[str] = []

    for node in doc.xpath("//*[@data-edit]"):
        field_id = (node.get("data-edit") or "").strip()
        if not FIELD_ID_RE.match(field_id):
            errors.append(
                f"data-edit=\"{field_id}\" is not a valid field id "
                "(lowercase letters, digits, dots, dashes)"
            )
            continue
        if field_id in seen:
            errors.append(f"data-edit=\"{field_id}\" is used more than once")
            continue
        seen.add(field_id)

        field_type = (node.get("data-type") or "text").strip()
        if field_type not in EDITABLE_FIELD_TYPES:
            errors.append(
                f"data-type=\"{field_type}\" on \"{field_id}\" is not editable "
                f"(use one of: {', '.join(EDITABLE_FIELD_TYPES)})"
            )
            continue

        node.set("data-editable-id", field_id)
        fields.append(
            {
                "id": field_id,
                "label": (node.get("data-label") or "").strip() or _default_label(field_id),
                "field_type": field_type,
                "group": _group_for(node),
                "notes": (node.get("data-notes") or "").strip(),
            }
        )
        value = extract_value(node, field_type)
        if value is not None:
            values[field_id] = value

    if errors:
        raise TemplateSourceError("; ".join(errors))

    _strip_dsl(doc)
    return pipeline.serialize(doc), {"fields": fields}, values


def _default_label(field_id: str) -> str:
    return field_id.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ").title()


def _group_for(node) -> str:
    """Editor panel group: the enclosing data-section's label, the field's own
    data-group, or 'Content'."""
    own = (node.get("data-group") or "").strip()
    if own:
        return own
    for ancestor in node.iterancestors():
        section = ancestor.get("data-section")
        if section:
            label = (ancestor.get("data-label") or "").strip()
            return label or section.replace("-", " ").replace("_", " ").title()
    return "Content"


def _strip_dsl(doc):
    for el in doc.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in DSL_ATTRIBUTES:
            if attr in el.attrib:
                del el.attrib[attr]
