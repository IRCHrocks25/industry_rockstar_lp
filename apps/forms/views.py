"""The /_submit/{form_id} proxy (architecture.md §11).

Public, on the publishing plane. Resilient by default (§13.2): store the
submission, redirect to the thank-you immediately, forward the webhook async with
retries. Per-form `gate_redirect_on_success` flips to synchronous gating. Spam
defence is a honeypot + payload cap + best-effort per-IP throttle (§12).

CSRF-exempt on purpose: visitors are anonymous with no session to protect, so a
token would add friction without security value; the honeypot guards abuse.
"""

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .integration import HONEYPOT_FIELD
from .models import Form, Submission
from .tasks import enqueue_forward
from .webhook import WebhookError, post_webhook

RESERVED_FIELDS = {HONEYPOT_FIELD, "csrfmiddlewaretoken"}


@csrf_exempt
@require_POST
def submit(request, form_id):
    if len(request.body) > settings.SUBMIT_MAX_BYTES:
        return HttpResponseForbidden("Submission too large.")
    if _rate_limited(request):
        return HttpResponse("Too many submissions — try again shortly.", status=429)

    form = get_object_or_404(Form, id=form_id)
    destination = form.success_destination()

    # Honeypot: a real visitor never fills the hidden field. Accept-and-drop so a
    # bot can't tell it was caught.
    if request.POST.get(HONEYPOT_FIELD, "").strip():
        return redirect(destination)

    payload = {k: v for k, v in request.POST.items() if k not in RESERVED_FIELDS}

    has_webhook = bool(form.webhook_url)
    submission = Submission.objects.create(
        form=form,
        payload=payload,
        webhook_status=(
            Submission.WebhookStatus.PENDING if has_webhook else Submission.WebhookStatus.SKIPPED
        ),
    )

    if not has_webhook:
        return redirect(destination)

    if form.gate_redirect_on_success:
        return _forward_and_gate(submission, form, destination)

    # Resilient default: forward async, redirect now.
    enqueue_forward(submission)
    return redirect(destination)


def _forward_and_gate(submission, form, destination):
    submission.attempts = 1
    try:
        post_webhook(form.webhook_url, submission.payload)
    except WebhookError as exc:
        submission.webhook_status = Submission.WebhookStatus.FAILED
        submission.last_error = str(exc)[:2000]
        submission.save(update_fields=["webhook_status", "attempts", "last_error"])
        # Gated + failed: bounce back to the form with an error marker.
        return redirect(f"{_form_page_url(form)}?form_error=1")

    submission.webhook_status = Submission.WebhookStatus.SUCCEEDED
    submission.save(update_fields=["webhook_status", "attempts"])
    return redirect(destination)


def _form_page_url(form):
    return "/" + form.page.path


def _rate_limited(request) -> bool:
    limit = settings.SUBMIT_RATE_LIMIT
    if not limit:
        return False
    ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
          or request.META.get("REMOTE_ADDR", "unknown"))
    key = f"submit-throttle:{ip}"
    try:
        count = cache.get_or_set(key, 0, settings.SUBMIT_RATE_WINDOW)
        cache.incr(key)
    except Exception:
        return False  # cache hiccup must never block a real lead
    return count is not None and count >= limit
