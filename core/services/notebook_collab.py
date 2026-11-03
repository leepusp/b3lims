"""Revisions, exclusive edit and comments for Notebook entries (step 2.1)."""

import difflib
import html
import re
import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models.lab_tools.notebook_collab import NotebookEditLock, NotebookRevision

# A save by the same author within this window updates the last revision
# instead of adding a new one, so autosave does not create hundreds.
REVISION_COALESCE = timedelta(minutes=5)
MAX_REVISIONS = 200
LOCK_TTL = timedelta(seconds=90)


# ------------------------------------------------------------------ revisions

def record_revision(entry, previous_content, user):
    """Call after ``entry.content`` changed from ``previous_content``.

    Keeps a baseline (the text before the first tracked edit) so the first
    change can be compared and undone.
    """
    if (entry.content or "") == (previous_content or ""):
        return None
    with transaction.atomic():
        if not entry.revisions.exists() and (previous_content or "").strip():
            NotebookRevision.objects.create(
                entry=entry, title=entry.title, content=previous_content, author=entry.author
            )
        last = entry.revisions.order_by("-id").first()
        if (
            last is not None
            and last.author_id == getattr(user, "pk", None)
            and timezone.now() - last.updated_at < REVISION_COALESCE
            and last.pk != entry.revisions.order_by("id").first().pk
        ):
            last.content = entry.content
            last.title = entry.title
            last.save(update_fields=["content", "title", "updated_at"])
            return last
        revision = NotebookRevision.objects.create(
            entry=entry, title=entry.title, content=entry.content, author=user
        )
        extra = entry.revisions.order_by("-id").values_list("pk", flat=True)[MAX_REVISIONS:]
        if extra:
            NotebookRevision.objects.filter(pk__in=list(extra)).delete()
        return revision


_BLOCK_END = re.compile(r"</(p|div|h[1-6]|li|tr|table|ul|ol|blockquote|pre)>|<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")


def html_to_lines(content):
    """Readable text lines from entry HTML, one per block element."""
    text = _BLOCK_END.sub("\n", content or "")
    text = _TAG.sub("", text)
    lines = [html.unescape(line).replace("\xa0", " ").strip() for line in text.split("\n")]
    return [line for line in lines if line]


def diff_content(old, new):
    """Line diff as ``[{"type": "same|add|del", "text": ...}]``, collapsing long unchanged runs."""
    a, b = html_to_lines(old), html_to_lines(new)
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            out.extend({"type": "same", "text": line} for line in a[i1:i2])
        else:
            out.extend({"type": "del", "text": line} for line in a[i1:i2])
            out.extend({"type": "add", "text": line} for line in b[j1:j2])
    return collapse_same(out)


def collapse_same(rows, keep=2):
    result, run = [], []
    def flush(last):
        if len(run) > 2 * keep + 1:
            head = run[:keep] if result else []
            tail = run[-keep:] if not last else []
            skipped = len(run) - len(head) - len(tail)
            result.extend(head)
            result.append({"type": "skip", "text": f"{skipped} unchanged lines"})
            result.extend(tail)
        else:
            result.extend(run)
        run.clear()
    for row in rows:
        if row["type"] == "same":
            run.append(row)
        else:
            flush(False)
            result.append(row)
    flush(True)
    return result


# ---------------------------------------------------------------- exclusive edit

def _active(lock, now=None):
    now = now or timezone.now()
    return lock is not None and now - lock.heartbeat_at < LOCK_TTL


def lock_status(entry, token=None):
    lock = NotebookEditLock.objects.filter(entry=entry).select_related("user").first()
    if not _active(lock):
        return {"locked": False, "mine": False, "holder": "", "since": ""}
    mine = bool(token) and secrets.compare_digest(lock.token, token)
    return {
        "locked": True,
        "mine": mine,
        "holder": lock.user.get_full_name() or lock.user.get_username(),
        "since": timezone.localtime(lock.acquired_at).strftime("%H:%M"),
    }


def acquire_lock(entry, user, token, force=False):
    """Take the edit lock. Returns ``(granted, status)``."""
    if not token or len(token) > 64:
        raise ValidationError("Missing lock token.")
    now = timezone.now()
    with transaction.atomic():
        lock = NotebookEditLock.objects.select_for_update().filter(entry=entry).first()
        if lock is None:
            NotebookEditLock.objects.create(entry=entry, user=user, token=token, heartbeat_at=now)
        elif not _active(lock, now) or secrets.compare_digest(lock.token, token) or force:
            if not secrets.compare_digest(lock.token, token):
                lock.acquired_at = now
            lock.user, lock.token, lock.heartbeat_at = user, token, now
            lock.save()
        else:
            return False, lock_status(entry, token)
    return True, lock_status(entry, token)


def heartbeat_lock(entry, token):
    """Renew the lock. False if it was taken over meanwhile."""
    updated = NotebookEditLock.objects.filter(entry=entry, token=token or "").update(heartbeat_at=timezone.now())
    return bool(updated)


def release_lock(entry, token):
    NotebookEditLock.objects.filter(entry=entry, token=token or "").delete()


def check_lock(entry, token):
    """Raise unless the request may write: no active foreign lock."""
    lock = NotebookEditLock.objects.filter(entry=entry).select_related("user").first()
    if not _active(lock):
        return
    if token and secrets.compare_digest(lock.token, token):
        return
    raise LockedError(lock.user.get_full_name() or lock.user.get_username())


class LockedError(Exception):
    def __init__(self, holder):
        super().__init__(f"This entry is being edited by {holder}.")
        self.holder = holder
