"""Publish flow (architecture.md §10): snapshot the draft, render, store the
blob keyed by version, repoint Page.published_version, record history.

The draft version keeps autosaving after publish; the published snapshot is a
separate immutable PageVersion row, so "unpublished changes" and rollback
(Phase 5) both fall out of the data model.
"""

from copy import deepcopy

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from apps.pages.models import PageVersion, PublishRecord
from apps.pages.render import render_version


class NothingToPublish(ValueError):
    pass


@transaction.atomic
def publish_page(page, user=None):
    """Publish the page's current draft. Returns the PublishRecord."""
    draft = page.draft_version
    if draft is None:
        raise NothingToPublish("This page has nothing to publish yet.")

    snapshot = PageVersion.objects.create(
        page=page,
        template_html=draft.template_html,
        annotation_map=deepcopy(draft.annotation_map),
        field_values=deepcopy(draft.field_values),
        created_by=user,
        note="Published snapshot",
    )
    html = render_version(snapshot, mode="publish", page=page)
    key = f"published/{page.site.subdomain}/{snapshot.id}.html"
    default_storage.save(key, ContentFile(html.encode("utf-8")))

    page.published_version = snapshot
    page.save(update_fields=["published_version", "updated_at"])
    return PublishRecord.objects.create(
        page=page, version=snapshot, rendered_key=key, published_by=user
    )


def read_published_html(page):
    """The stored blob for the page's latest publish; falls back to re-rendering
    the published snapshot if the blob is gone (e.g. wiped local media)."""
    record = page.publish_records.select_related("version").first()
    if record and default_storage.exists(record.rendered_key):
        with default_storage.open(record.rendered_key) as fh:
            return fh.read().decode("utf-8")
    if page.published_version_id:
        return render_version(page.published_version, mode="publish", page=page)
    return None
