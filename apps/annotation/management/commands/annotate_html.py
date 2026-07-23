"""Quality-inspection harness for the LLM annotator.

Runs a real annotation pass over an HTML file (or stdin) and prints the detected
fields as a readable table — WITHOUT touching the database. This is the fast
loop for judging label/type/grouping quality and iterating on the prompt/model.

    python manage.py annotate_html path/to/page.html
    python manage.py annotate_html path/to/page.html --model gpt-4o-mini
    cat page.html | python manage.py annotate_html -

Requires OPENAI_API_KEY (and the openai package) — it makes a live API call.
"""

import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.annotation import service
from apps.annotation.client import AnnotationError, annotate
from apps.importer import pipeline


class Command(BaseCommand):
    help = "Run the LLM annotator over an HTML file and print the detected fields."

    def add_arguments(self, parser):
        parser.add_argument("path", help="HTML file to annotate, or '-' for stdin.")
        parser.add_argument("--model", default=None, help="Override OPENAI_MODEL for this run.")
        parser.add_argument(
            "--show-values", action="store_true",
            help="Also print each field's extracted starting value.",
        )

    def handle(self, *args, **options):
        if not settings.OPENAI_API_KEY:
            raise CommandError("OPENAI_API_KEY is not set — add it to .env first.")

        raw_html = self._read(options["path"])
        # Same front half as a real import: sanitize + stamp (no asset rehosting).
        template_html, _ = pipeline.process_html(raw_html)

        model = options["model"]
        annotator = (lambda skeletons: annotate(skeletons, model=model)) if model else None

        try:
            outcome = service.annotate_html(template_html, annotator=annotator)
        except AnnotationError as exc:
            raise CommandError(str(exc))

        self._print(outcome, show_values=options["show_values"], model=model or settings.OPENAI_MODEL)

    def _read(self, path):
        if path == "-":
            data = sys.stdin.read()
        else:
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    data = fh.read()
            except OSError as exc:
                raise CommandError(f"Could not read {path}: {exc}")
        if not data.strip():
            raise CommandError("The input HTML is empty.")
        return data

    def _print(self, outcome, *, show_values, model):
        fields = outcome.annotation_map.get("fields", [])
        self.stdout.write("")
        self.stdout.write(f"Model: {model}   Fields: {len(fields)}   Tokens: {outcome.tokens}")
        self.stdout.write("=" * 72)
        if not fields:
            self.stdout.write("No editable fields detected.")
            return

        last_group = None
        for f in fields:
            group = f.get("group") or "Content"
            if group != last_group:
                self.stdout.write("")
                self.stdout.write(self.style.SUCCESS(group))
                last_group = group
            line = f"  · {f['label']}  [{f['field_type']}]  ({f['id']})"
            self.stdout.write(line)
            if f.get("notes"):
                self.stdout.write(f"      note: {f['notes']}")
            if show_values:
                value = outcome.field_values.get(f["id"])
                if value is not None:
                    self.stdout.write(f"      value: {self._preview(value)}")

    @staticmethod
    def _preview(value):
        text = value if isinstance(value, str) else str(value)
        text = " ".join(text.split())
        return text if len(text) <= 80 else text[:79] + "…"
