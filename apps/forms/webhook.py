"""Outbound webhook delivery (architecture.md §12).

Reuses the import fetcher's SSRF validation (blocks internal/metadata addresses)
and adds an optional hostname allowlist, so an attacker-set webhook_url can't be
turned into a server-side request forgery.
"""

import requests
from django.conf import settings

from apps.assets.fetcher import FetchError, validate_url

TIMEOUT = (5, 20)  # connect, read
USER_AGENT = "IndustryRockstarForms/1.0"


class WebhookError(Exception):
    """Delivery failed or the target URL is not allowed. Message is safe to log."""


def post_webhook(url, payload):
    """POST the payload as JSON. Raises WebhookError on a blocked target, a
    network failure, or a non-2xx response (so the caller can retry)."""
    if not url:
        raise WebhookError("No webhook URL configured.")
    try:
        parsed = validate_url(url)  # SSRF guard: scheme + resolves-to-global
    except FetchError as exc:
        raise WebhookError(str(exc)) from exc

    allowed = settings.WEBHOOK_ALLOWED_HOSTS
    if allowed and parsed.hostname not in allowed:
        raise WebhookError(f"{parsed.hostname} is not in the webhook allowlist.")

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=TIMEOUT,
            allow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException as exc:
        raise WebhookError(f"Webhook request failed: {exc}") from exc

    if response.status_code >= 400:
        raise WebhookError(f"Webhook returned HTTP {response.status_code}.")
    return response.status_code
