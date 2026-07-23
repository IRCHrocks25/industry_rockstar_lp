"""OpenAI structured-output call (architecture.md §7 step 5).

The only place a network call to OpenAI happens. `openai` is imported lazily so
the rest of the app (and the test suite) runs without the package or a key. The
callable shape — (skeletons) -> AnnotationResult — is what the service depends
on, so tests inject a stub instead of this.
"""

import json
from dataclasses import dataclass, field

from django.conf import settings

from . import schema


@dataclass
class AnnotationResult:
    fields: list[dict] = field(default_factory=list)
    tokens: int = 0


class AnnotationError(RuntimeError):
    """Raised when the model call fails or returns unusable output. The import
    task catches this and degrades to an empty annotation rather than dying."""


def annotate(skeletons: list[str], *, model=None, api_key=None) -> AnnotationResult:
    """Annotate one or more skeleton chunks and merge the results. First field
    wins on a duplicate temp id (chunks don't overlap, so this is just belt and
    braces)."""
    api_key = api_key or settings.OPENAI_API_KEY
    model = model or settings.OPENAI_MODEL
    if not api_key:
        raise AnnotationError("OPENAI_API_KEY is not set.")

    client = _make_client(api_key)
    merged: dict[str, dict] = {}
    total_tokens = 0
    for skeleton in skeletons:
        result = _annotate_one(client, model, skeleton)
        total_tokens += result.tokens
        for f in result.fields:
            tmp_id = f.get("tmp_id")
            if tmp_id and tmp_id not in merged:
                merged[tmp_id] = f
    return AnnotationResult(fields=list(merged.values()), tokens=total_tokens)


def _make_client(api_key):
    try:
        from openai import OpenAI
    except ImportError as exc:  # dependency present only where annotation runs
        raise AnnotationError(
            "The 'openai' package is not installed (pip install -r requirements.txt)."
        ) from exc
    return OpenAI(api_key=api_key)


def _annotate_one(client, model, skeleton) -> AnnotationResult:
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": schema.SYSTEM_PROMPT},
                {"role": "user", "content": skeleton},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.SCHEMA_NAME,
                    "strict": True,
                    "schema": schema.RESPONSE_SCHEMA,
                },
            },
        )
    except Exception as exc:  # network, auth, rate limit, bad model, ...
        raise AnnotationError(f"OpenAI request failed: {exc}") from exc

    choice = response.choices[0]
    content = choice.message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AnnotationError("OpenAI returned non-JSON content.") from exc

    tokens = getattr(getattr(response, "usage", None), "total_tokens", 0) or 0
    fields = data.get("fields", []) if isinstance(data, dict) else []
    return AnnotationResult(fields=fields, tokens=tokens)
