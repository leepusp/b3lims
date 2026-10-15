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

    workspace = StorageWorkspace(
        name=name,
        scope=scope,
        owner=actor,
        research_group=group,
    )

    workspace.full_clean()
    workspace.save()

    return workspace
