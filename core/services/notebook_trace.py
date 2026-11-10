"""Sign, lock, amend and record deviations on Notebook entries."""

import hashlib
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.models.lab_tools.notebook_collab import NotebookRevision
from core.models.lab_tools.notebook_trace import NotebookDeviation, NotebookSignature
from core.permissions.notebook import can_edit_ignoring_signature, can_view_notebook_entry

MEANING_LABELS = dict(NotebookSignature.MEANINGS)
MIN_REASON = 10


def content_digest(entry) -> str:
    """SHA-256 of what the entry says: text, structured blocks, steps, tables and the current files."""
    document = {
        "title": entry.title, "content": entry.content, "protocol": entry.protocol_content, "type": entry.entry_type,
        "custom_id": entry.custom_id, "date": entry.experiment_date.isoformat() if entry.experiment_date else "", "metadata": entry.metadata,
        "blocks": [[b.block_type, b.title, b.order, b.content_data] for b in entry.blocks.order_by("order", "id")],
        "steps": [[s.position, s.group, s.body] for s in entry.steps.order_by("position", "id")],
        "tables": [[t.title, t.data] for t in entry.spreadsheets.order_by("id")],
        "files": [[a.pk, a.checksum_sha256, a.caption] for a in entry.attachments.filter(is_current=True).order_by("id")],
    }

    return hashlib.sha256(json.dumps(document, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def active_signatures(entry):
    return entry.signatures.filter(superseded_at__isnull=True)


def _name(user):
    return (user.get_full_name() or user.get_username()) if user else ""


def _signature_row(sig, current_digest):
    return {
        "id": sig.pk, "meaning": sig.meaning, "meaning_label": MEANING_LABELS.get(sig.meaning, sig.meaning),
        "signer": sig.signer_name or _name(sig.signer), "comment": sig.comment,
        "at": timezone.localtime(sig.signed_at).strftime("%Y-%m-%d %H:%M"), "sha256": sig.content_sha256,
        "intact": sig.content_sha256 == current_digest if sig.superseded_at is None else None,
        "superseded_at": timezone.localtime(sig.superseded_at).strftime("%Y-%m-%d %H:%M") if sig.superseded_at else "",
        "superseded_by": _name(sig.superseded_by), "superseded_reason": sig.superseded_reason,
    }


def _deviation_row(dev):
    return {
        "id": dev.pk, "step": dev.step_text, "description": dev.description, "impact": dev.impact, "impact_label": dev.get_impact_display(),
        "by": _name(dev.created_by), "at": timezone.localtime(dev.created_at).strftime("%Y-%m-%d %H:%M"),
        "resolved": dev.resolved_at is not None, "resolution": dev.resolution, "resolved_by": _name(dev.resolved_by),
        "resolved_at": timezone.localtime(dev.resolved_at).strftime("%Y-%m-%d %H:%M") if dev.resolved_at else "",
    }


def state(entry, user) -> dict:
    digest = content_digest(entry)
    signatures = list(entry.signatures.select_related("signer", "superseded_by"))
    active = [s for s in signatures if s.superseded_at is None]
    locked = entry.signed_at is not None
    mine = {s.meaning for s in active if s.signer_id == user.pk}
    is_author = entry.author_id == user.pk

    return {
        "locked": locked,
        "intact": all(s.content_sha256 == digest for s in active) if active else None,
        "sha256": digest,
        "signatures": [_signature_row(s, digest) for s in reversed(signatures)],
        "deviations": [_deviation_row(d) for d in entry.deviations.select_related("created_by", "resolved_by")],
        "can_sign_author": is_author and not locked and can_view_notebook_entry(user, entry),
        "can_sign_witness": locked and not is_author and can_view_notebook_entry(user, entry) and "witness" not in mine,
        "can_sign_reviewer": locked and not is_author and can_view_notebook_entry(user, entry) and "reviewer" not in mine,
        "can_amend": locked and (is_author or user.is_superuser),
        "can_record": can_edit_ignoring_signature(user, entry),
    }


def sign(entry, user, meaning, comment=""):
    comment = (comment or "").strip()[:500]

    if meaning not in MEANING_LABELS:
        raise ValidationError("Choose what your signature means.")
    if entry.deleted_at is not None:
        raise ValidationError("An entry in the trash cannot be signed.")
    if not can_view_notebook_entry(user, entry):
        raise PermissionDenied("You cannot sign an entry you cannot open.")

    with transaction.atomic():
        entry = type(entry).objects.select_for_update().get(pk=entry.pk)

        if meaning == "author":
            if entry.author_id != user.pk:
                raise PermissionDenied("Only the author can sign as the author.")
            if entry.signed_at is not None:
                raise ValidationError("This entry is already signed.")
        else:
            if entry.author_id == user.pk:
                raise PermissionDenied("The author cannot also witness or review their own entry.")
            if entry.signed_at is None:
                raise ValidationError("The author has to sign first.")
            if active_signatures(entry).filter(signer=user, meaning=meaning).exists():
                raise ValidationError("You already signed this entry.")

        sig = NotebookSignature.objects.create(
            entry=entry, signer=user, signer_name=_name(user), meaning=meaning, comment=comment, content_sha256=content_digest(entry),
        )

        if meaning == "author":
            type(entry).objects.filter(pk=entry.pk).update(signed_at=sig.signed_at)

    return sig


def amend(entry, user, reason):
    reason = (reason or "").strip()

    if entry.signed_at is None:
        raise ValidationError("This entry is not signed.")
    if not (user.is_superuser or entry.author_id == user.pk):
        raise PermissionDenied("Only the author can amend a signed entry.")
    if len(reason) < MIN_REASON:
        raise ValidationError(f"Say why in at least {MIN_REASON} characters.")

    with transaction.atomic():
        now = timezone.now()
        # Keep the signed text as a revision so the version that was signed can be compared and restored.
        NotebookRevision.objects.create(entry=entry, title=entry.title, content=entry.content, author=user)
        count = active_signatures(entry).update(superseded_at=now, superseded_by=user, superseded_reason=reason[:500])
        type(entry).objects.filter(pk=entry.pk).update(signed_at=None)

    return count


def add_deviation(entry, user, description, impact="minor", step_text=""):
    description = (description or "").strip()

    if not can_edit_ignoring_signature(user, entry):
        raise PermissionDenied("You cannot record deviations on this entry.")
    if not description:
        raise ValidationError("Describe what differed from the plan.")
    if impact not in dict(NotebookDeviation.IMPACTS):
        raise ValidationError("Choose the impact.")

    return NotebookDeviation.objects.create(
        entry=entry, created_by=user, description=description[:3000], impact=impact, step_text=(step_text or "").strip()[:500],
    )


def resolve_deviation(entry, user, deviation_id, resolution):
    if not can_edit_ignoring_signature(user, entry):
        raise PermissionDenied("You cannot change deviations on this entry.")

    deviation = entry.deviations.filter(pk=deviation_id).first()

    if deviation is None:
        raise ValidationError("That deviation no longer exists.")
    if not (resolution or "").strip():
        raise ValidationError("Say how it was resolved.")

    deviation.resolution = resolution.strip()[:3000]
    deviation.resolved_at, deviation.resolved_by = timezone.now(), user
    deviation.save(update_fields=["resolution", "resolved_at", "resolved_by"])

    return deviation
