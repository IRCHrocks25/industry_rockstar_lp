from django import forms
from django.core.exceptions import ValidationError

from apps.library import parser as template_parser
from apps.library.models import SiteTemplate
from apps.pages.models import ImportSource, Page
from apps.sites.models import Site

MAX_UPLOAD_BYTES = 2 * 1024 * 1024


class SiteForm(forms.ModelForm):
    """Marketer-facing site creation — validation lives on the model
    (subdomain format + reserved names); this just surfaces it politely.

    `start` picks the starting point: "blank" (import a page later), "paste"
    (own HTML through the import pipeline), or a SiteTemplate id."""

    START_BLANK = "blank"
    START_PASTE = "paste"

    start = forms.CharField(required=False, empty_value=START_BLANK)
    html_text = forms.CharField(required=False, widget=forms.Textarea)
    html_file = forms.FileField(required=False)

    class Meta:
        model = Site
        fields = ["name", "subdomain"]
        error_messages = {
            "subdomain": {
                "unique": "That subdomain is already taken by another site.",
            }
        }

    def clean_subdomain(self):
        return self.cleaned_data["subdomain"].strip().lower()

    def clean(self):
        cleaned = super().clean()
        start = (cleaned.get("start") or self.START_BLANK).strip()
        cleaned["start"] = start
        cleaned["template"] = None
        if start == self.START_PASTE:
            upload = cleaned.get("html_file")
            if upload and upload.size > MAX_UPLOAD_BYTES:
                self.add_error("html_file", "That file is over 2 MB — export just the page HTML.")
            elif not upload and not (cleaned.get("html_text") or "").strip():
                self.add_error("html_text", "Paste the page HTML (or choose a file) first.")
        elif start != self.START_BLANK:
            try:
                cleaned["template"] = SiteTemplate.gallery().get(id=start)
            except (SiteTemplate.DoesNotExist, ValidationError, ValueError):
                self.add_error(None, "Pick a starting design from the list.")
        return cleaned

    def pasted_html(self):
        """(raw_html, source_type) for start=paste; the file wins over the box."""
        if self.cleaned_data.get("html_file"):
            raw = self.cleaned_data["html_file"].read().decode("utf-8", errors="replace")
            return raw, ImportSource.SourceType.UPLOAD
        return self.cleaned_data.get("html_text", ""), ImportSource.SourceType.PASTE


class TemplateCreateForm(forms.ModelForm):
    """Add a design to the gallery: name + the landing page HTML (pasted or
    uploaded), optionally a thank-you page. DSL-annotated HTML becomes
    editable instantly; plain HTML goes through the AI annotation task."""

    landing_text = forms.CharField(required=False, widget=forms.Textarea)
    landing_file = forms.FileField(required=False)
    thanks_text = forms.CharField(required=False, widget=forms.Textarea)
    thanks_file = forms.FileField(required=False)

    class Meta:
        model = SiteTemplate
        fields = ["name", "description"]
        error_messages = {
            "name": {"unique": "A template with that name already exists."}
        }

    def clean(self):
        cleaned = super().clean()
        cleaned["landing_html"] = self._resolve_html("landing", required=True)
        cleaned["thanks_html"] = self._resolve_html("thanks", required=False)
        return cleaned

    def _resolve_html(self, prefix, required):
        upload = self.cleaned_data.get(f"{prefix}_file")
        text = (self.cleaned_data.get(f"{prefix}_text") or "").strip()
        if upload:
            if upload.size > MAX_UPLOAD_BYTES:
                self.add_error(f"{prefix}_file", "That file is over 2 MB — export just the page HTML.")
                return ""
            html = upload.read().decode("utf-8", errors="replace")
        elif text:
            html = text
        else:
            if required:
                self.add_error(f"{prefix}_text", "Paste the page HTML (or choose a file) first.")
            return ""
        if template_parser.has_annotations(html):
            try:
                template_parser.build(html)
            except template_parser.TemplateSourceError as exc:
                self.add_error(f"{prefix}_text", f"Problem in the annotations: {exc}")
        return html


class PageImportForm(forms.Form):
    """One form for the whole intake: page identity + exactly one HTML source."""

    name = forms.CharField(max_length=200)
    path = forms.CharField(max_length=200, required=False, empty_value="")
    source_type = forms.ChoiceField(choices=ImportSource.SourceType.choices)
    html_text = forms.CharField(required=False, widget=forms.Textarea)
    html_file = forms.FileField(required=False)
    source_url = forms.URLField(required=False, max_length=1000)

    def __init__(self, site, *args, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)

    def clean_path(self):
        path = self.cleaned_data["path"].strip().strip("/").lower()
        if path:
            from apps.pages.models import path_validator

            path_validator(path)
        return path

    def clean(self):
        cleaned = super().clean()
        path = cleaned.get("path", "")
        if self.site.pages.filter(path=path).exists():
            label = f"/{path}" if path else "the homepage"
            self.add_error("path", f"This site already has a page at {label}.")

        source_type = cleaned.get("source_type")
        if source_type == ImportSource.SourceType.PASTE:
            if not (cleaned.get("html_text") or "").strip():
                self.add_error("html_text", "Paste the page HTML first.")
        elif source_type == ImportSource.SourceType.UPLOAD:
            upload = cleaned.get("html_file")
            if not upload:
                self.add_error("html_file", "Choose an HTML file first.")
            elif upload.size > MAX_UPLOAD_BYTES:
                self.add_error("html_file", "That file is over 2 MB — export just the page HTML.")
        elif source_type == ImportSource.SourceType.URL:
            if not cleaned.get("source_url"):
                self.add_error("source_url", "Enter the page URL first.")
        return cleaned

    def raw_html(self):
        """The pasted or uploaded HTML ('' for URL imports — fetched by the job)."""
        if self.cleaned_data["source_type"] == ImportSource.SourceType.PASTE:
            return self.cleaned_data["html_text"]
        if self.cleaned_data["source_type"] == ImportSource.SourceType.UPLOAD:
            return self.cleaned_data["html_file"].read().decode("utf-8", errors="replace")
        return ""
