"""Annotation orchestration (architecture.md §7 steps 4-7).

One entry point the importer calls: take the stamped template HTML, build the
skeleton, ask the model (injectable — real client by default), materialize the
answer into stable editable ids + initial field values, and hand back the new
template. All AI lives behind `annotator`; everything else is deterministic.
"""

from dataclasses import dataclass, field

from django.conf import settings
from lxml import html as lxml_html

from . import materialize, skeleton
from .client import annotate as _default_annotator


@dataclass
class AnnotationOutcome:
    template_html: str
    annotation_map: dict = field(default_factory=lambda: {"fields": []})
    field_values: dict = field(default_factory=dict)
    tokens: int = 0

    @property
    def field_count(self) -> int:
        return len(self.annotation_map.get("fields", []))


def is_enabled() -> bool:
    """Annotation runs only when a key is configured; otherwise imports take the
    manual path (empty annotation) so the LLM never blocks the core loop."""
    return bool(settings.OPENAI_API_KEY)


def annotate_html(template_html: str, *, annotator=None) -> AnnotationOutcome:
    """Annotate stamped template HTML. `annotator` is a callable
    (list[str]) -> AnnotationResult; tests pass a stub. Raises AnnotationError
    (from the client) on model failure — the caller decides how to degrade."""
    annotator = annotator or _default_annotator
    doc = lxml_html.document_fromstring(template_html)

    skeletons = skeleton.build_skeletons(doc)
    if not skeletons:
        return AnnotationOutcome(template_html=template_html)

    result = annotator(skeletons)
    annotation_map, field_values = materialize.materialize(doc, result.fields)
    new_html = lxml_html.tostring(doc, doctype="<!DOCTYPE html>", encoding="unicode")
    return AnnotationOutcome(
        template_html=new_html,
        annotation_map=annotation_map,
        field_values=field_values,
        tokens=getattr(result, "tokens", 0),
    )
