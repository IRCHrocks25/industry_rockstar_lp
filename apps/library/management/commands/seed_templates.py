"""Load/refresh the built-in starter templates from apps/library/starters/.

Idempotent: matches templates by name and pages by path, so re-running after
editing a starter file updates in place. Marketer-created sites keep their own
copies — provisioning deep-copies, so refreshing a template never touches
existing sites.
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from apps.library.models import SiteTemplate, TemplatePage

STARTERS_DIR = Path(__file__).resolve().parents[2] / "starters"

STARTERS = [
    {
        "name": "Lead magnet funnel",
        "description": "Give away a free guide and collect leads — landing page plus thank-you page.",
        "sort": 10,
        "pages": [
            {"name": "Landing page", "path": "", "sort": 0, "file": "lead_magnet_landing.html"},
            {"name": "Thank you", "path": "thank-you", "sort": 1, "file": "lead_magnet_thank_you.html"},
        ],
    },
    {
        "name": "Webinar registration",
        "description": "Fill seats for a live session — registration page plus confirmation page.",
        "sort": 20,
        "pages": [
            {"name": "Registration page", "path": "", "sort": 0, "file": "webinar_landing.html"},
            {"name": "You're registered", "path": "thank-you", "sort": 1, "file": "webinar_thank_you.html"},
        ],
    },
]


class Command(BaseCommand):
    help = "Create or refresh the built-in starter templates."

    def handle(self, *args, **options):
        for starter in STARTERS:
            template, created = SiteTemplate.objects.update_or_create(
                name=starter["name"],
                defaults={"description": starter["description"], "sort": starter["sort"]},
            )
            for page in starter["pages"]:
                html_source = (STARTERS_DIR / page["file"]).read_text(encoding="utf-8")
                obj, _ = TemplatePage.objects.get_or_create(
                    template=template,
                    path=page["path"],
                    defaults={"name": page["name"], "sort": page["sort"], "html_source": html_source},
                )
                obj.name = page["name"]
                obj.sort = page["sort"]
                obj.html_source = html_source
                obj.save()  # rebuilds template_html + schema from source
            verb = "Created" if created else "Refreshed"
            self.stdout.write(self.style.SUCCESS(f"{verb} “{template.name}” ({template.pages.count()} pages)"))
