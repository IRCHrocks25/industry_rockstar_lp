"""Form detection (import) and form rewriting (render) — architecture.md §7.8, §11.

Detection is deterministic (never the LLM): at import we find every <form>, give
it a stable data-editable-id, and ensure a Form record exists for it. At render
we rewrite each managed form's action to the /_submit proxy and inject a honeypot
field, so we own submission + redirect (§11) and get basic spam defence (§12).
"""

from lxml import html as lxml_html

from django.utils.text import slugify

HONEYPOT_FIELD = "hp_contact_url"


def detect_and_sync(page, template_html: str) -> str:
    """Find <form>s, stamp stable ids, create missing Form records. Returns the
    (possibly rewritten) template HTML. Idempotent across re-imports."""
    from .models import Form

    doc = lxml_html.document_fromstring(template_html)
    forms = doc.xpath("//form")
    if not forms:
        return template_html

    used = set()
    changed = False
    for i, node in enumerate(forms):
        editable_id = node.get("data-editable-id") or _form_id(node, i, used)
        used.add(editable_id)
        if node.get("data-editable-id") != editable_id:
            node.set("data-editable-id", editable_id)
            changed = True
        Form.objects.get_or_create(
            page=page,
            editable_id=editable_id,
            defaults={"name": f"Form {i + 1}"},
        )

    if not changed:
        return template_html
    return lxml_html.tostring(doc, doctype="<!DOCTYPE html>", encoding="unicode")


def _form_id(node, index, used):
    base = slugify(node.get("id") or node.get("name") or "") or f"form-{index + 1}"
    candidate, n = base, 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def apply_forms(doc, page):
    """Render step: point each managed form at /_submit/{form_id}, force POST,
    and ensure a honeypot input is present. Called from the render engine."""
    from .models import Form

    forms = {f.editable_id: f for f in page.forms.all()}
    if not forms:
        return
    for node in doc.xpath("//form[@data-editable-id]"):
        form = forms.get(node.get("data-editable-id"))
        if form is None:
            continue
        node.set("action", f"/_submit/{form.id}")
        node.set("method", "post")
        _ensure_honeypot(node)


def _ensure_honeypot(form_node):
    if form_node.xpath(f".//input[@name='{HONEYPOT_FIELD}']"):
        return
    wrapper = lxml_html.fragment_fromstring(
        f'<div style="position:absolute;left:-9999px" aria-hidden="true">'
        f'<input type="text" name="{HONEYPOT_FIELD}" tabindex="-1" autocomplete="off"></div>'
    )
    form_node.insert(0, wrapper)
