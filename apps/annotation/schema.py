"""Field taxonomy + the OpenAI structured-output schema (architecture.md §7 step 5).

The LLM is schema-forced: it can only return a list of field objects, each
pointing at a stamped node by its temp id. It never sees or emits markup.
"""

# architecture.md §7: the closed set of field types the annotator may assign.
FIELD_TYPES = (
    "text",
    "richtext",
    "image",
    "link_url",
    "link_text",
    "cta",
    "countdown",
    "form",
    "background_image",
    "color",
    "visibility",
    "meta_title",
    "meta_description",
)

# Types the Phase-1 render engine (apps/pages/render.py) knows how to patch and
# the editor knows how to present. Others are still recorded (so the field is
# visible) but wait on their own phase (countdown=§9, form=§11).
EDITABLE_FIELD_TYPES = (
    "text",
    "richtext",
    "image",
    "link_url",
    "link_text",
    "cta",
    "background_image",
)


# JSON schema handed to OpenAI as response_format=json_schema (strict). Strict
# mode requires every property listed in `required` and additionalProperties
# false, so the model can only return well-formed field objects.
RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tmp_id": {
                        "type": "string",
                        "description": "The data-anno-tmp id of the node this field edits.",
                    },
                    "label": {
                        "type": "string",
                        "description": "Short human label for a non-technical marketer, e.g. 'Hero headline'.",
                    },
                    "field_type": {
                        "type": "string",
                        "enum": list(FIELD_TYPES),
                    },
                    "group": {
                        "type": "string",
                        "description": "Section this field belongs to, e.g. 'Hero', 'Features', 'Footer'.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional guidance for the editor; '' if none.",
                    },
                },
                "required": ["tmp_id", "label", "field_type", "group", "notes"],
            },
        }
    },
    "required": ["fields"],
}

SCHEMA_NAME = "page_annotations"

SYSTEM_PROMPT = (
    "You annotate landing-page HTML for a non-technical marketing team so they can "
    "edit the page through labeled form fields. You are given a stripped DOM "
    "skeleton: indentation shows nesting, and each element carries a `t` attribute "
    "(its temp id) plus its tag, classes, cheap hints (href/src/bg-image/"
    "countdown-like), and truncated text. Return one field per editable region.\n\n"
    "What TO annotate — content a marketer changes per campaign:\n"
    "- Headlines, subheadings, and body copy (the visible marketing message).\n"
    "- Images (<img>) and CSS background images that carry brand/product visuals.\n"
    "- Call-to-action buttons and meaningful links.\n"
    "- Forms.\n\n"
    "What NOT to annotate — skip these entirely:\n"
    "- Navigation menus, headers/footers chrome, cookie/consent banners, legal or "
    "copyright boilerplate, social-icon rows.\n"
    "- Purely structural or decorative wrappers with no direct text of their own.\n"
    "- The same content twice: choose ONE node per visible piece of content.\n\n"
    "Precision rules:\n"
    "- tmp_id MUST be an exact `t` value copied from the skeleton. Never invent or "
    "guess one; if unsure a region exists, omit it.\n"
    "- Attach the field to the MOST SPECIFIC node that holds the content — the "
    "element whose own text is the copy, the <img>, the <a> — never an ancestor "
    "wrapper, and never both a parent and its child for the same text.\n"
    "- field_type, narrowest correct choice: `cta` for a button/link that drives an "
    "action (has text AND a destination); `link_text`/`link_url` for a plain link's "
    "words vs. its URL; `image` for <img>; `background_image` for a bg-image node; "
    "`richtext` ONLY when inline formatting (bold/italic/lists/links inside a "
    "paragraph) must survive editing; `form` for a form; otherwise `text`.\n"
    "- label: 2-4 plain words a non-technical user understands ('Hero headline', "
    "'Primary button', 'Pricing subtext') — not a class name or the raw copy.\n"
    "- group: the visible section the field lives in (Hero, Benefits, Features, "
    "Pricing, Testimonials, FAQ, Footer, ...). Reuse the same group name for "
    "fields in the same section so the editor panel stays organized.\n"
    "- notes: '' unless one short hint genuinely helps the editor.\n"
    "- Prefer precision over recall: a few correct, well-labeled fields beat many "
    "noisy ones."
)
