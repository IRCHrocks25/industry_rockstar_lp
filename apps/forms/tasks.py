"""Async webhook forwarding with retries (architecture.md §11).

Enqueued by the /_submit proxy in the resilient path. Django-Q re-runs the task
on failure (Q_CLUSTER max_attempts); each run bumps `attempts` and records the
last error on the Submission so delivery is auditable without a UI.
"""

from django_q.tasks import async_task

from .models import Submission
from .webhook import WebhookError, post_webhook


def enqueue_forward(submission):
    async_task("apps.forms.tasks.forward_submission", str(submission.id))


def forward_submission(submission_id):
    sub = Submission.objects.select_related("form").get(id=submission_id)
    if sub.webhook_status == Submission.WebhookStatus.SUCCEEDED:
        return  # idempotent against duplicate deliveries
    form = sub.form
    if not form.webhook_url:
        sub.webhook_status = Submission.WebhookStatus.SKIPPED
        sub.save(update_fields=["webhook_status"])
        return

    sub.attempts = (sub.attempts or 0) + 1
    try:
        post_webhook(form.webhook_url, sub.payload)
    except WebhookError as exc:
        sub.webhook_status = Submission.WebhookStatus.FAILED
        sub.last_error = str(exc)[:2000]
        sub.save(update_fields=["webhook_status", "attempts", "last_error"])
        raise  # surface to Django-Q so it retries

    sub.webhook_status = Submission.WebhookStatus.SUCCEEDED
    sub.last_error = ""
    sub.save(update_fields=["webhook_status", "attempts", "last_error"])
