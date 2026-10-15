"""User and Research Group authorization for physical storage."""

from django.db.models import Q

from core.models.research_groups.model import ResearchGroup
from core.models.samples.storage import (
    StorageLocation,
    StorageWorkspace,
)


def _active_user(user):
    return bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
    )


def is_storage_global_admin(user):
    """
    Only the designated institutional administrator may
    inspect all workspaces, including unscoped legacy nodes.

    Django staff status alone never grants global storage access.
    """
    return bool(
        _active_user(user)
        and user.get_username().casefold() == "ccalomeno"
        and (
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
        )
    )


def research_group_ids_for_storage_user(user):
    if not _active_user(user):
        return set()

    return set(
        ResearchGroup.objects.filter(
            Q(coordinator_id=user.pk)
            | Q(members__pk=user.pk)
        )
        .distinct()
        .values_list("pk", flat=True)
    )


def visible_storage_workspaces_for_user(user):
    qs = StorageWorkspace.objects.all()

    if not _active_user(user):
        return qs.none()

    if is_storage_global_admin(user):
        return qs

    group_ids = research_group_ids_for_storage_user(user)

    return qs.filter(
        Q(scope="personal", owner_id=user.pk)
        | Q(
            scope="group",
            research_group_id__in=group_ids,
        )
    ).distinct()


def can_view_storage_workspace(user, workspace):
    if not _active_user(user) or workspace is None:
        return False

    if is_storage_global_admin(user):
        return True

    if workspace.scope == "personal":
        return workspace.owner_id == user.pk

    if workspace.scope == "group":
        return (
            workspace.research_group_id
            in research_group_ids_for_storage_user(user)
        )

    return False


def can_register_in_storage_workspace(user, workspace):
    """Workspace access only; Sample edit permission is also required."""
    return can_view_storage_workspace(user, workspace)


def can_manage_storage_workspace(user, workspace):
    if not can_view_storage_workspace(user, workspace):
        return False

    if is_storage_global_admin(user):
        return True

    if workspace.scope == "personal":
        return workspace.owner_id == user.pk

    if workspace.scope == "group":
        return bool(
            workspace.research_group_id
            and ResearchGroup.objects.filter(
                pk=workspace.research_group_id,
                coordinator_id=user.pk,
            ).exists()
        )

    return False


def can_view_storage_location(user, location):
    if not _active_user(user) or location is None:
        return False

    if is_storage_global_admin(user):
        return True

    workspace_id = location.workspace_id

    if workspace_id is None:
        return False

    if not can_view_storage_workspace(
        user,
        location.workspace,
    ):
        return False

    seen = set()
    node = location

    while node is not None:
        if node.pk in seen:
            return False

        seen.add(node.pk)

        # Prevent access through incorrectly mixed ownership trees.
        if node.workspace_id != workspace_id:
            return False

        node = node.parent

    return True


def visible_storage_locations_for_user(user):
    qs = StorageLocation.objects.all()

    if not _active_user(user):
        return qs.none()

    if is_storage_global_admin(user):
        return qs

    workspace_ids = list(
        visible_storage_workspaces_for_user(user)
        .values_list("pk", flat=True)
    )

    if not workspace_ids:
        return qs.none()

    candidates = (
        qs.filter(workspace_id__in=workspace_ids)
        .select_related("workspace", "parent")
    )

    authorized_ids = [
        location.pk
        for location in candidates
        if can_view_storage_location(user, location)
    ]

    return qs.filter(pk__in=authorized_ids)


def can_operate_on_sample_storage(user, sample):
    """
    Authorize physical storage edits independently of Django staff.

    Public Sample visibility never grants storage modification.
    Existing direct Sample edit grants remain supported.
    """
    if not _active_user(user) or sample is None:
        return False

    if getattr(sample, "deletion_requested_at", None) is not None:
        return False

    if is_storage_global_admin(user):
        return True

    if sample.owner_id == user.pk:
        return True

    groups = research_group_ids_for_storage_user(user)

    if (
        sample.research_group_id is not None
        and sample.research_group_id in groups
    ):
        return True

    if groups and sample.collections.filter(
        research_group_id__in=groups
    ).exists():
        return True

    from core.permissions.samples import (
        _has_direct_sample_access,
    )

    return bool(
        _has_direct_sample_access(user, sample, edit=True)
    )


def can_register_at_storage_location(user, location):
    """
    Position host access: physical Box or Rack in an
    authorized workspace, with all ancestors active.

    Unscoped legacy storage remains admin-only.
    """
    if (
        not _active_user(user)
        or location is None
        or location.location_type not in {"box", "rack"}
        or not can_view_storage_location(user, location)
    ):
        return False

    visited = set()
    node = location

    while node is not None:
        if node.pk in visited or not node.is_active:
            return False

        visited.add(node.pk)
        node = node.parent

    if is_storage_global_admin(user):
        return True

    return (
        location.workspace_id is not None
        and can_register_in_storage_workspace(
            user,
            location.workspace,
        )
    )
