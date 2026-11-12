"""Workspace-scoped authorization for physical storage movements."""

from django.core.exceptions import PermissionDenied, ValidationError

from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
)
from core.permissions.storage_workspaces_v8 import (
    can_manage_storage_workspace,
    can_operate_on_sample_storage,
    can_register_at_storage_location,
    can_register_in_storage_workspace,
    can_view_storage_location,
    is_storage_global_admin,
)


def authorize_sample_storage_move_v8(
    *,
    actor,
    assignment,
    destination,
):
    """
    Authorize a Sample movement before preview or execution.

    The source only needs to be visible: an inactive source
    must not prevent an authorized Sample from being removed.

    The destination must be an active, authorized physical location.
    Occupancy and lifecycle checks remain responsibilities
    of the movement service.
    """
    if assignment is None or destination is None:
        raise PermissionDenied(
            "Storage movement is not authorized."
        )

    if not can_operate_on_sample_storage(
        actor,
        assignment.sample,
    ):
        raise PermissionDenied(
            "You cannot move this Sample."
        )

    if not can_view_storage_location(
        actor,
        assignment.location,
    ):
        raise PermissionDenied(
            "The source storage location is not accessible."
        )

    # Do not expose destination state before authorization.
    if not can_view_storage_location(actor, destination):
        raise PermissionDenied(
            "The destination storage location is not accessible."
        )

    if destination.location_type not in {"box", "rack", "other"}:
        raise PermissionDenied(
            "This location is not authorized to receive Samples."
        )

    if not is_storage_global_admin(actor):
        if (
            destination.workspace_id is None
            or not can_register_in_storage_workspace(
                actor, destination.workspace
            )
        ):
            raise PermissionDenied(
                "The destination storage location is not accessible."
            )

    # A visible, authorized but inactive destination is a
    # domain validation error rather than an access denial.
    visited = set()
    node = destination

    while node is not None:
        if node.pk in visited:
            raise ValidationError(
                "Cyclic storage hierarchy."
            )

        visited.add(node.pk)

        if node.workspace_id != destination.workspace_id:
            raise PermissionDenied(
                "Mixed-workspace storage hierarchy."
            )

        if not node.is_active:
            raise ValidationError(
                "The destination storage hierarchy is inactive."
            )

        node = node.parent

    if not can_register_at_storage_location(
        actor, destination
    ):
        raise PermissionDenied(
            "The destination storage location is not accessible."
        )

    if destination.workspace_id is not None:
        from core.services.storage_biobank_transfer import (
            require_destination_biobank,
        )

        require_destination_biobank(
            actor, destination.workspace, [assignment.sample]
        )

    return True


def authorize_storage_container_move_v8(
    *,
    actor,
    container,
    destination,
):
    """
    Authorize a physical container move inside one workspace.

    A container may go to another workspace when the actor manages
    both; the whole subtree changes workspace with it.
    """
    if container is None or destination is None:
        raise PermissionDenied(
            "Container movement is not authorized."
        )

    if not (
        can_view_storage_location(actor, container)
        and can_view_storage_location(actor, destination)
    ):
        raise PermissionDenied(
            "Container movement is not authorized."
        )

    workspace_id = container.workspace_id
    destination_workspace_id = destination.workspace_id

    for scoped_id, scoped in (
        (workspace_id, container.workspace),
        (destination_workspace_id, destination.workspace),
    ):
        if scoped_id is None:
            if not is_storage_global_admin(actor):
                raise PermissionDenied(
                    "Legacy unscoped infrastructure is administrator-only."
                )
        elif not can_manage_storage_workspace(actor, scoped):
            raise PermissionDenied(
                "You cannot manage this storage workspace."
            )

    # Verify both ancestor chains. In particular, the global
    # administrator must not bypass structural consistency.
    for starting_node, expected in (
        (container, workspace_id),
        (destination, destination_workspace_id),
    ):
        seen = set()
        node = starting_node

        while node is not None:
            if node.pk in seen:
                raise PermissionDenied(
                    "Cyclic storage hierarchy."
                )

            seen.add(node.pk)

            if node.workspace_id != expected:
                raise PermissionDenied(
                    "Mixed-workspace hierarchy."
                )

            node = node.parent

    # A container movement affects all its descendants.
    # Never move a mixed-ownership subtree.
    seen = set()
    frontier = [container.pk]

    while frontier:
        if any(pk in seen for pk in frontier):
            raise PermissionDenied(
                "Cyclic storage hierarchy."
            )

        seen.update(frontier)

        children = list(
            StorageLocation.objects
            .filter(parent_id__in=frontier)
            .values("pk", "workspace_id")
        )

        if any(
            child["workspace_id"] != workspace_id
            for child in children
        ):
            raise PermissionDenied(
                "The container has foreign-workspace descendants."
            )

        frontier = [
            child["pk"]
            for child in children
        ]

    # Moving a container changes the physical path of every
    # Sample inside it. Infrastructure permission is insufficient.
    assignments = (
        SampleStorageAssignment.objects
        .filter(location_id__in=seen, status="active")
        .select_related("sample")
    )

    for assignment in assignments:
        if not can_operate_on_sample_storage(
            actor, assignment.sample
        ):
            raise PermissionDenied(
                "The container contains Samples outside "
                "your authorized scope."
            )

    return True
