"""Biobank change that goes with moving Samples into the storage of another Biobank."""

from django.core.exceptions import PermissionDenied

from core.permissions.biobanks import can_edit_biobank


def require_destination_biobank(actor, workspace, samples):
    """Refuse the move unless the actor may write to the destination Biobank, when Samples would change Biobank."""
    biobank = getattr(workspace, "biobank", None)

    if biobank is None:
        return False

    changing = [s for s in samples if s.biobank_id != biobank.pk]

    if changing and not can_edit_biobank(actor, biobank):
        raise PermissionDenied(
            f"Moving Samples to the storage of {biobank.name} requires "
            "owner, manager or editor access to that Biobank."
        )

    return bool(changing)


def apply_destination_biobank(actor, workspace, samples):
    """Set the Biobank of the moved Samples to the one linked to the destination storage."""
    if not require_destination_biobank(actor, workspace, samples):
        return 0

    changed = 0

    for sample in samples:
        if sample.biobank_id != workspace.biobank_id:
            sample.biobank = workspace.biobank
            sample.save(update_fields=["biobank"])
            changed += 1

    return changed
