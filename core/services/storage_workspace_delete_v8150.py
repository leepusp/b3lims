"""Delete empty, personally owned Storage workspaces.

This operation never deletes physical locations or Samples.
"""

import json
import re

from django.contrib.admin.models import DELETION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import Collector

from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)
from core.permissions.storage_workspaces_v8 import (
    can_manage_storage_workspace,
)


@transaction.atomic
def delete_empty_personal_storage_workspace_v8150(
    *, actor, workspace_id, confirmation,
):
    if not (
        getattr(actor, "is_authenticated", False)
        and getattr(actor, "is_active", False)
    ):
        raise PermissionDenied("An active account is required.")

    raw_id = str(workspace_id or "").strip()

    if not re.fullmatch(r"[0-9]{1,20}", raw_id):
        raise ValidationError("Invalid Storage identifier.")

    workspace = (
        StorageWorkspace.objects
        .select_for_update()
        .filter(pk=int(raw_id))
        .first()
    )

    if workspace is None:
        raise ValidationError("Storage not found.")

    # Strict owner-only operation. Global administrator status
    # does not grant permission to delete another user's Storage.
    if not (
        workspace.scope == "personal"
        and workspace.owner_id == actor.pk
        and workspace.research_group_id is None
        and can_manage_storage_workspace(actor, workspace)
    ):
        raise PermissionDenied(
            "Only the owner may delete a personal Storage."
        )

    if str(confirmation or "") != workspace.name:
        raise ValidationError(
            "Type the exact Storage name to confirm deletion."
        )

    # Include inactive locations. Never cascade through inventory.
    if StorageLocation.objects.filter(
        workspace_id=workspace.pk
    ).exists():
        raise ValidationError(
            "This Storage still contains physical locations. "
            "Remove its locations before deleting the Storage."
        )

    # Reject any future model relationship that could introduce
    # a dependent deletion, even if CASCADE is added later.
    collector = Collector(
        using=workspace._state.db or "default"
    )
    collector.collect([workspace])

    if (
        collector.fast_deletes
        or any(
            model is not StorageWorkspace
            for model in collector.data
        )
        or sum(
            len(objects)
            for objects in collector.data.values()
        ) != 1
    ):
        raise ValidationError(
            "Storage has dependent records; deletion blocked."
        )

    workspace_pk = workspace.pk
    workspace_name = workspace.name

    deleted_count, deleted_models = workspace.delete()

    if (
        deleted_count != 1
        or deleted_models != {"core.StorageWorkspace": 1}
    ):
        raise ValidationError(
            "Unexpected dependent deletion; transaction reverted."
        )

    LogEntry.objects.create(
        user_id=actor.pk,
        content_type=ContentType.objects.get_for_model(
            StorageWorkspace
        ),
        object_id=str(workspace_pk),
        object_repr=workspace_name[:200],
        action_flag=DELETION,
        change_message=json.dumps({
            "operation": "delete_empty_personal_storage_v8150",
            "workspace_id": workspace_pk,
            "workspace_name": workspace_name,
            "scope": "personal",
            "deleted_locations": 0,
            "deleted_samples": 0,
        }),
    )

    return {
        "workspace_id": workspace_pk,
        "workspace_name": workspace_name,
    }
