"""Activity history: signal handlers that record who added, changed or removed what."""

import logging
import threading
from datetime import timedelta

from django.apps import apps
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

_local = threading.local()
FOLD_WINDOW = timedelta(minutes=10)


def set_current_user(user):
    _local.user = user if getattr(user, "is_authenticated", False) else None


def current_user():
    return getattr(_local, "user", None)


def _url(name, *args):
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return ""


def _molecule_url(molecule):
    return _url("molecular_sequence_detail", molecule.pk)


# model label -> how to describe it. ``verbs`` limits which events are logged.
TRACKED = {
    "core.NotebookEntry": {
        "type": lambda o: "eln_entry",
        "label": lambda o: o.title,
        "actor": lambda o: o.author,
        "url": lambda o: _url("notebook_entry", o.pk),
    },
    "core.MolecularSequence": {
        "type": lambda o: f"molecular_{o.sequence_type}",
        "label": lambda o: o.name,
        "actor": lambda o: o.owner,
        "url": _molecule_url,
    },
    "core.MolecularStructure": {
        "type": lambda o: "molecular_structure",
        "label": lambda o: f"{o.label or o.original_filename} · {o.molecule.name}",
        "actor": lambda o: o.uploaded_by,
        "url": lambda o: _molecule_url(o.molecule),
        "verbs": ("created", "deleted"),
    },
    "core.MolecularAlignment": {
        "type": lambda o: "molecular_alignment",
        "label": lambda o: f"{getattr(o, 'name', '') or 'Alignment'} · {o.molecule.name}",
        "actor": lambda o: o.uploaded_by,
        "url": lambda o: _molecule_url(o.molecule),
        "verbs": ("created", "deleted"),
    },
    "core.MolecularSecondaryStructure": {
        "type": lambda o: "molecular_secondary_structure",
        "label": lambda o: f"{getattr(o, 'name', '') or 'Secondary structure'} · {o.molecule.name}",
        "actor": lambda o: o.created_by,
        "url": lambda o: _molecule_url(o.molecule),
        "verbs": ("created", "deleted"),
    },
    "core.NotebookAttachment": {
        "type": lambda o: "eln_file",
        "label": lambda o: o.caption or (o.file.name.rsplit("/", 1)[-1] if o.file else "File"),
        "actor": lambda o: o.uploaded_by,
        "url": lambda o: _url("notebook_entry", o.entry_id),
        "verbs": ("created", "deleted"),
    },
    "core.ToolRecord": {
        "type": lambda o: f"tool_{o.tool}",
        "label": lambda o: o.name,
        "actor": lambda o: o.owner,
        "url": lambda o: _url("tool_record_detail", o.pk),
    },
    "core.Sample": {
        "type": lambda o: "sample",
        "label": lambda o: o.sample_id,
        "actor": lambda o: o.owner,
        "url": lambda o: _url("sample_detail", o.pk),
    },
    "core.JupyterNotebook": {
        "type": lambda o: "jupyter_notebook",
        "label": lambda o: o.title,
        "actor": lambda o: o.owner,
        "url": lambda o: "",
    },
    "core.SubmissionPackage": {
        "type": lambda o: "submission",
        "label": lambda o: o.title,
        "actor": lambda o: o.owner,
        "url": lambda o: _url("submission_detail", o.pk),
    },
    "core.StorageMovement": {
        "type": lambda o: "storage_movement",
        "label": lambda o: (
            f"{o.get_movement_type_display()}: {o.origin_path or '—'} → {o.destination_path or '—'}"
            + (f" ({o.affected_sample_count} sample{'s' if o.affected_sample_count != 1 else ''})" if o.affected_sample_count else "")
        ),
        "actor": lambda o: o.performed_by,
        "url": lambda o: _url("storage_workspace"),
        "verbs": ("created",),
    },
    "bench.Booking": {
        "type": lambda o: "booking",
        "label": lambda o: o.title or f"Booking of {o.resource}",
        "actor": lambda o: o.user,
        "url": lambda o: _url("lab_calendar"),
    },
}


def record(verb, instance, config):
    """Write (or fold) one history row. Never raises: history must not break a save."""
    from core.models.activity import ActivityLog

    try:
        actor = current_user() or config["actor"](instance)
        label = str(config["label"](instance) or "")[:255]
        entity_type = config["type"](instance)
        url = "" if verb == "deleted" else (config["url"](instance) or "")[:300]
        name = actor.get_username() if actor else ""
        now = timezone.now()

        with transaction.atomic():
            if verb == "updated" and actor:
                recent = ActivityLog.objects.filter(
                    actor=actor, verb=verb, entity_type=entity_type, entity_id=instance.pk,
                    updated_at__gte=now - FOLD_WINDOW,
                ).first()

                if recent:
                    recent.count += 1
                    recent.entity_label = label
                    recent.save(update_fields=["count", "entity_label", "updated_at"])

                    return recent

            return ActivityLog.objects.create(
                actor=actor, actor_name=name, verb=verb, entity_type=entity_type,
                entity_id=instance.pk, entity_label=label, url=url,
            )
    except Exception:  # noqa: BLE001 - the history is best effort
        logger.exception("Could not record activity for %r", instance)

        return None


def _make_handler(config, created_verb=True):
    verbs = config.get("verbs", ("created", "updated", "deleted"))

    def on_save(sender, instance, created, raw=False, **kwargs):
        if raw:
            return

        verb = "created" if created else "updated"

        if verb in verbs:
            record(verb, instance, config)

    def on_delete(sender, instance, **kwargs):
        if "deleted" in verbs:
            record("deleted", instance, config)

    return on_save, on_delete


def connect():
    """Attach the handlers to every tracked model that is installed."""
    for label, config in TRACKED.items():
        try:
            model = apps.get_model(label)
        except LookupError:
            continue

        on_save, on_delete = _make_handler(config)

        post_save.connect(on_save, sender=model, weak=False, dispatch_uid=f"activity-save-{label}")
        post_delete.connect(on_delete, sender=model, weak=False, dispatch_uid=f"activity-delete-{label}")


# --- reading ------------------------------------------------------------------

ENTITY_GROUPS = [
    ("eln_entry", "ELN entry"),
    ("eln_file", "ELN file"),
    ("molecular_dna", "DNA record"),
    ("molecular_plasmid", "Plasmid record"),
    ("molecular_rna", "RNA record"),
    ("molecular_protein", "Protein record"),
    ("molecular_primer", "Primer record"),
    ("molecular_structure", "3D structure"),
    ("molecular_alignment", "Alignment"),
    ("molecular_secondary_structure", "Secondary structure"),
    ("tool_gel", "Gel"),
    ("tool_chemical", "Chemical"),
    ("sample", "Sample"),
    ("jupyter_notebook", "Jupyter notebook"),
    ("submission", "Data submission"),
    ("booking", "Booking"),
    ("storage_movement", "Storage movement"),
]
ENTITY_LABELS = dict(ENTITY_GROUPS)


def visible_to(user):
    from core.models.activity import ActivityLog

    qs = ActivityLog.objects.all()

    return qs if user.is_superuser else qs.filter(actor=user)
