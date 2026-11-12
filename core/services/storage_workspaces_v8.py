"""Explicit creation of personal or group storage workspaces."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.models.research_groups.model import ResearchGroup
from core.models.samples.storage import StorageWorkspace
from core.permissions.storage_workspaces_v8 import (
    is_storage_global_admin,
)


@transaction.atomic
def create_storage_workspace_v8(
    *,
    actor,
    name,
    scope,
    research_group_id=None,
    biobank_id=None,
):
    if not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Authentication required.")

    if not getattr(actor, "is_active", False):
        raise PermissionDenied("Active account required.")

    name = str(name or "").strip()

    if not name or len(name) > 120:
        raise ValidationError("Invalid workspace name.")

    if scope not in {"personal", "group"}:
        raise ValidationError("Invalid workspace scope.")

    group = None

    if scope == "personal":
        if research_group_id not in (None, ""):
            raise ValidationError(
                "Personal storage cannot belong to a group."
            )
    else:
        try:
            pk = int(research_group_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Select a Research Group."
            ) from exc

        group = ResearchGroup.objects.filter(pk=pk).first()

        if group is None:
            raise ValidationError("Research Group not found.")

        if not (
            is_storage_global_admin(actor)
            or group.coordinator_id == actor.pk
        ):
            raise PermissionDenied(
                "Only the group coordinator or global "
                "administrator can create a group workspace."
            )

    biobank = None

    if biobank_id not in (None, ""):
        from core.models.biobanks.biobank import Biobank
        from core.permissions.biobanks import can_edit_biobank

        biobank = Biobank.objects.filter(pk=biobank_id).first() if str(biobank_id).isdigit() else None

        if biobank is None or not can_edit_biobank(actor, biobank):
            raise PermissionDenied("You cannot link this Biobank to a storage.")

    workspace = StorageWorkspace(
        name=name,
        scope=scope,
        owner=actor,
        research_group=group,
        biobank=biobank,
    )

    workspace.full_clean()
    workspace.save()

    return workspace


@transaction.atomic
def set_storage_workspace_biobank_v8(*, actor, workspace_id, biobank_id):
    """Link a workspace to a Biobank (or unlink it with an empty value)."""
    from core.models.biobanks.biobank import Biobank
    from core.permissions.biobanks import can_edit_biobank
    from core.permissions.storage_workspaces_v8 import can_link_storage_workspace_biobank

    workspace = StorageWorkspace.objects.select_for_update().filter(pk=workspace_id).first()

    if workspace is None or not can_link_storage_workspace_biobank(actor, workspace):
        raise PermissionDenied("You cannot change this storage.")

    biobank = None

    if str(biobank_id or "").strip():
        biobank = Biobank.objects.filter(pk=biobank_id).first() if str(biobank_id).isdigit() else None

        if biobank is None or not can_edit_biobank(actor, biobank):
            raise PermissionDenied("You cannot link this Biobank to a storage.")

    workspace.biobank = biobank
    workspace.save(update_fields=["biobank", "updated_at"])

    return workspace
