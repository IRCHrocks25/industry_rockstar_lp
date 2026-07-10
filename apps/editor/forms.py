from django import forms

from apps.pages.models import ImportSource, Page
from apps.sites.models import Site

MAX_UPLOAD_BYTES = 2 * 1024 * 1024


class SiteForm(forms.ModelForm):
    """Marketer-facing site creation — validation lives on the model
    (subdomain format + reserved names); this just surfaces it politely."""

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
