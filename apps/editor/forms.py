from django import forms

from apps.sites.models import Site


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
