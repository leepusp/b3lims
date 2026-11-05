"""Internal physical Inventory Storage workspace."""

from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
)
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.db.models import Count, Q
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from core.context import base_context
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
)
from core.permissions.samples import (
    can_edit_sample,
    visible_samples_for_user,
)
from core.permissions.storage import (
    can_manage_storage_infrastructure,
)
from core.services.storage_assignment_reconcile import (
    reconcile_sample_storage_from_text,
)
from core.services.storage_sample_movements import move_sample
from core.services.storage_sample_movement_preview import (
    preview_sample_movements,
)
from core.services.storage_movement_preview import (
    preview_storage_container_move,
)
from core.services.storage_movement_history import (
    visible_storage_movements,
)

from core.services.storage_locations import (
    create_storage_location,
    set_storage_location_active,
    update_storage_location,
)


def _flatten_storage_locations(
    locations,
):
    children = defaultdict(
        list
    )

    by_id = {
        location.pk: location
        for location in locations
    }

    for location in locations:
        children[
            location.parent_id
        ].append(
            location
        )

    rows = []

    visited = set()

    def walk(
        parent_id,
        depth,
    ):
        for location in children[
            parent_id
        ]:
            if location.pk in visited:
                continue

            visited.add(
                location.pk
            )

            rows.append(
                {
                    "location": location,
                    "depth": depth,
                    "prefix": "— " * depth,
                }
            )

            walk(
                location.pk,
                depth + 1,
            )

    walk(
        None,
        0,
    )

    # Defensive fallback for malformed/orphaned hierarchies.
    for location in locations:
        if location.pk in visited:
            continue

        rows.append(
            {
                "location": location,
                "depth": 0,
                "prefix": "",
            }
        )

    return rows


@login_required
def storage_workspace_view(
    request,
):
    from core.permissions.storage_workspaces_v8 import (
        can_operate_on_sample_storage,
        can_view_storage_location,
    )

    can_manage = (
        can_manage_storage_infrastructure(
            request.user
        )
    )

    from core.models.research_groups.model import ResearchGroup
    from core.permissions.storage_workspaces_v8 import (
        can_manage_storage_workspace,
        is_storage_global_admin,
        visible_storage_locations_for_user,
        visible_storage_workspaces_for_user,
    )

    storage_visible_workspaces_v8 = list(
        visible_storage_workspaces_for_user(
            request.user
        ).select_related("owner", "research_group")
    )

    storage_manageable_workspaces_v8 = [
        workspace
        for workspace in storage_visible_workspaces_v8
        if can_manage_storage_workspace(
            request.user, workspace
        )
    ]

    requested_storage_token = str(
        request.GET.get("storage", "")
    ).strip()

    b3s_selected_storage_pk_v8147 = next(
        (
            item.pk
            for item in storage_visible_workspaces_v8
            if str(item.pk) == requested_storage_token
        ),
        None,
    )

    manageable_workspace_ids_v8 = [
        workspace.pk
        for workspace in storage_manageable_workspaces_v8
    ]

    storage_parent_choices_v8 = list(
        visible_storage_locations_for_user(request.user)
        .filter(
            workspace_id__in=manageable_workspace_ids_v8,
            is_active=True,
        )
        .order_by("name", "pk")
    )

    if is_storage_global_admin(request.user):
        storage_group_choices_v8 = (
            ResearchGroup.objects.all().order_by("name")
        )
    else:
        storage_group_choices_v8 = (
            ResearchGroup.objects.filter(
                coordinator=request.user
            ).order_by("name")
        )


    if (
        request.method == "GET"
        and request.GET.get("b3s_delete_preview")
    ):
        from django.http import JsonResponse
        from core.services.storage_subtree_unassign_v8149 import (
            preview_storage_subtree_unassign_v8149,
        )

        try:
            result = preview_storage_subtree_unassign_v8149(
                actor=request.user,
                location_id=request.GET.get(
                    "b3s_delete_preview"
                ),
            )
        except PermissionDenied:
            return JsonResponse(
                {"error": "Permission denied."},
                status=403,
            )
        except ValidationError as exc:
            return JsonResponse(
                {"error": "; ".join(exc.messages)},
                status=400,
            )

        return JsonResponse(result)

    if request.method == "POST":
        action = (
            request.POST.get(
                "action",
                "",
            )
            .strip()
        )

        try:
            if action in {
                "confirm_sample_move",
                "confirm_bulk_sample_move",
                "confirm_container_move",
            }:
                from core.services.storage_workspace_confirmation import (
                    confirm_storage_workspace_transfer,
                )
                movement = confirm_storage_workspace_transfer(
                    action=action,
                    data=request.POST,
                    actor=request.user,
                )
                messages.success(
                    request,
                    f"Storage transfer completed. Movement #{movement.pk}.",
                )

            elif action == "save_scene_configuration_v8":
                from django.urls import reverse
                from core.models.samples.storage import (
                    StorageSceneConfiguration,
                )
                from core.services.storage_scene_configuration_v8 import (
                    save_storage_scene_configuration,
                )

                operation = request.POST.get(
                    "save_operation",
                    "",
                )

                if operation not in {"create", "update"}:
                    raise ValidationError(
                        "Invalid scene save operation."
                    )

                configuration_id = None

                if operation == "update":
                    raw_id = request.POST.get(
                        "scene_configuration_id",
                        "",
                    )

                    if not raw_id.isascii() or not raw_id.isdigit():
                        raise ValidationError(
                            "Select a saved scene to update."
                        )

                    configuration_id = int(raw_id)

                    existing = (
                        StorageSceneConfiguration.objects
                        .filter(
                            pk=configuration_id,
                            owner=request.user,
                        )
                        .first()
                    )

                    if existing is None:
                        raise PermissionDenied(
                            "Scene configuration is not accessible."
                        )

                    if existing.profile_overrides:
                        raise ValidationError(
                            "This scene has nested geometry overrides. "
                            "The simplified editor cannot modify it "
                            "without losing those settings."
                        )

                configuration = save_storage_scene_configuration(
                    actor=request.user,
                    name=request.POST.get("name", ""),
                    root_id=request.POST.get(
                        "root_location_id",
                        "",
                    ),
                    root_profile=request.POST.get(
                        "root_profile",
                        "auto",
                    ),
                    profile_overrides={},
                    configuration_id=configuration_id,
                )

                messages.success(
                    request,
                    "Spatial view configuration saved.",
                )

                return redirect(
                    f"{reverse('storage_workspace')}"
                    f"?legacy=1&scene={configuration.pk}"
                    "#storage-scene-controls-v8"
                )

            elif action == "create_storage_workspace_v8":
                from core.services.storage_workspaces_v8 import (
                    create_storage_workspace_v8,
                )

                workspace = create_storage_workspace_v8(
                    actor=request.user,
                    name=request.POST.get("workspace_name", ""),
                    scope=request.POST.get("workspace_scope", "personal"),
                    research_group_id=request.POST.get(
                        "research_group_id", ""
                    ),
                )

                messages.success(
                    request,
                    f"Storage workspace created: {workspace.name}.",
                )


                if (
                    request.POST.get(
                        "b3s_select_created_storage"
                    ) == "1"
                ):
                    response = redirect("storage_workspace")
                    response["Location"] += f"?storage={workspace.pk}"
                    return response

            elif action == "delete_empty_personal_storage_v8150":
                from core.services.storage_workspace_delete_v8150 import (
                    delete_empty_personal_storage_workspace_v8150,
                )

                removed = delete_empty_personal_storage_workspace_v8150(
                    actor=request.user,
                    workspace_id=request.POST.get("workspace_id"),
                    confirmation=request.POST.get(
                        "confirm_workspace_name", ""
                    ),
                )

                messages.success(
                    request,
                    (
                        "Storage deleted: "
                        f"{removed['workspace_name']}. "
                        "No Samples or physical locations were deleted."
                    ),
                )

            elif action == "delete_subtree_and_unassign":
                from core.services.storage_subtree_unassign_v8149 import (
                    delete_storage_subtree_unassign_v8149,
                )

                removed = delete_storage_subtree_unassign_v8149(
                    actor=request.user,
                    location_id=request.POST.get("location_id"),
                    confirmation=request.POST.get("confirm", ""),
                    preview_token=request.POST.get(
                        "preview_token", ""
                    ),
                    reason=request.POST.get("reason", ""),
                )

                messages.success(
                    request,
                    (
                        f"Removed {removed['location_count']} "
                        "storage location(s). "
                        f"Released {removed['assignment_count']} "
                        "assignment(s) from "
                        f"{removed['sample_count']} Sample(s)."
                    ),
                )

            elif action == "delete_empty_subtree":
                from core.services.storage_subtree_delete_v8145 import (
                    delete_empty_storage_subtree,
                )

                removed = delete_empty_storage_subtree(
                    actor=request.user,
                    location_id=request.POST.get("location_id"),
                    confirmation=request.POST.get("confirm", ""),
                )

                messages.success(
                    request,
                    (
                        f"Removed {removed['location_count']} "
                        "empty storage location(s)."
                    ),
                )

            elif action == "create_location":
                from core.services.storage_workspace_infrastructure_v8 import (
                    create_storage_location_in_workspace_v8,
                )

                location = create_storage_location_in_workspace_v8(
                    actor=request.user,
                    workspace_id=request.POST.get("workspace_id"),
                    parent_id=request.POST.get("parent_id", ""),
                    name=request.POST.get("name", ""),
                    location_type=request.POST.get(
                        "location_type", "other"
                    ),
                    rank=request.POST.get("rank", "1"),
                    notes=request.POST.get("notes", ""),
                )

                messages.success(
                    request,
                    f"Storage location created: {location.full_path}",
                )

            elif action == "update_location":
                from core.services.storage_workspace_infrastructure_v8 import (
                    update_storage_location_in_workspace_v8,
                )

                update_storage_location_in_workspace_v8(
                    actor=request.user,
                    location_id=request.POST.get("location_id"),
                    name=request.POST.get("name", ""),
                    location_type=request.POST.get(
                        "location_type", "other"
                    ),
                    rank=request.POST.get("rank", "1"),
                    notes=request.POST.get("notes", ""),
                )

                messages.success(
                    request,
                    "Storage location updated.",
                )

            elif action in {
                "deactivate_location",
                "reactivate_location",
            }:
                from core.services.storage_workspace_infrastructure_v8 import (
                    set_storage_location_active_in_workspace_v8,
                )

                location = set_storage_location_active_in_workspace_v8(
                    actor=request.user,
                    location_id=request.POST.get("location_id"),
                    is_active=(action == "reactivate_location"),
                )

                messages.success(
                    request,
                    (
                        "Storage location reactivated."
                        if location.is_active
                        else "Storage location deactivated."
                    ),
                )

            elif action == "assign_sample":
                sample = get_object_or_404(
                    visible_samples_for_user(
                        request.user
                    ),
                    pk=request.POST.get(
                        "sample_id"
                    ),
                )

                if not can_operate_on_sample_storage(
                    request.user,
                    sample,
                ):
                    raise PermissionDenied(
                        (
                            "You cannot modify this "
                            "Sample's physical storage."
                        )
                    )

                location = get_object_or_404(
                    StorageLocation,
                    pk=request.POST.get(
                        "location_id"
                    ),
                    is_active=True,
                )

                if not can_view_storage_location(
                    request.user, location
                ):
                    raise PermissionDenied(
                        "Physical destination is not accessible."
                    )

                active_assignments = list(
                    sample.storage_assignments
                    .select_related("location")
                    .filter(status="active")
                    .order_by("rank", "id")
                )

                if any(
                    not can_view_storage_location(
                        request.user, item.location
                    )
                    for item in active_assignments
                ):
                    raise PermissionDenied(
                        "Existing Sample storage is not accessible."
                    )

                # A primary destination cannot duplicate an
                # existing secondary physical assignment.
                if any(
                    item.location_id == location.pk
                    for item in active_assignments[1:]
                ):
                    raise ValidationError(
                        "This location is already assigned as "
                        "an additional Sample location. "
                        "Use the Sample editor to reorganize "
                        "multiple locations."
                    )

                if active_assignments:
                    primary = active_assignments[0]

                    if primary.location_id != location.pk:
                        # Move only the current primary row.
                        # A slot from the old container must
                        # not be reused automatically.
                        move_sample(
                            assignment_id=primary.pk,
                            destination_id=location.pk,
                            position="",
                            expected_location_id=primary.location_id,
                            expected_position=primary.position,
                            expected_source_path=(
                                primary.location.full_path
                            ),
                            expected_destination_path=(
                                location.full_path
                            ),
                            actor=request.user,
                            reason=(
                                "Primary location changed through "
                                "Storage Workspace."
                            ),
                        )
                else:
                    # First assignment: preserve the existing
                    # Sample creation / compatibility behavior.
                    reconcile_sample_storage_from_text(
                        sample=sample,
                        storage_location_text=location.full_path,
                        actor=request.user,
                        reason=(
                            "Initial storage assignment through "
                            "Storage Workspace."
                        ),
                    )

                messages.success(
                    request,
                    (
                        f"{sample.sample_id} assigned to "
                        f"{location.full_path}."
                    ),
                )

            else:
                messages.error(
                    request,
                    "Unknown storage action.",
                )

        except ValidationError as exc:
            messages.error(
                request,
                "; ".join(
                    exc.messages
                ),
            )

        if request.GET.get("legacy") == "1":
            response = redirect("storage_workspace")
            response["Location"] += "?legacy=1"
            return response

        return redirect(
            "storage_workspace"
        )

    container_preview = None
    container_preview_error = ""
    preview_container_id = None
    preview_destination_id = None

    if request.method == "GET" and request.GET.get(
        "preview_container"
    ) == "1":
        container_text = request.GET.get(
            "container_id", ""
        ).strip()
        destination_text = request.GET.get(
            "destination_id", ""
        ).strip()

        def valid_location_id(value):
            return (
                1 <= len(value) <= 18
                and value.isascii()
                and value.isdecimal()
                and int(value) > 0
            )

        if not (
            valid_location_id(container_text)
            and valid_location_id(destination_text)
        ):
            container_preview_error = (
                "Select a valid container and destination."
            )
        else:
            preview_container_id = int(container_text)
            preview_destination_id = int(destination_text)

            try:
                preview_container = StorageLocation.objects.get(
                    pk=preview_container_id
                )
                preview_destination = StorageLocation.objects.get(
                    pk=preview_destination_id
                )

                from core.permissions.storage_movements_v8 import (
                    authorize_storage_container_move_v8,
                )

                authorize_storage_container_move_v8(
                    actor=request.user,
                    container=preview_container,
                    destination=preview_destination,
                )

                container_preview = preview_storage_container_move(
                    container=preview_container,
                    destination=preview_destination,
                )
            except StorageLocation.DoesNotExist:
                container_preview_error = (
                    "The selected location no longer exists."
                )
            except ValidationError as exc:
                container_preview_error = "; ".join(
                    exc.messages
                )

    sample_preview = None
    sample_preview_error = ""
    sample_preview_assignment_id = None
    sample_preview_destination_id = None
    sample_preview_position = ""

    if (
        request.method == "GET"
        and request.GET.get("preview_sample") == "1"
    ):
        raw_assignment = request.GET.get("assignment_id", "").strip()
        raw_destination = request.GET.get("destination_id", "").strip()
        sample_preview_position = request.GET.get("position", "").strip()

        def valid_sample_preview_id(value):
            return (
                1 <= len(value) <= 18
                and value.isascii()
                and value.isdecimal()
                and int(value) > 0
            )

        if (
            not valid_sample_preview_id(raw_assignment)
            or not valid_sample_preview_id(raw_destination)
            or len(sample_preview_position) > 100
        ):
            sample_preview_error = "Invalid Sample transfer selection."
            sample_preview_position = ""
        else:
            sample_preview_assignment_id = int(raw_assignment)
            sample_preview_destination_id = int(raw_destination)

            try:
                sample_preview = preview_sample_movements(
                    moves=[{
                        "assignment_id": sample_preview_assignment_id,
                        "destination_id": sample_preview_destination_id,
                        "position": sample_preview_position,
                    }],
                    actor=request.user,
                )
            except ValidationError as exc:
                sample_preview_error = "; ".join(exc.messages)


    # D3B: read-only, all-or-nothing bulk preview.
    bulk_preview = None
    bulk_preview_error = ""
    empty_bulk_row = {
        "assignment_id": None,
        "destination_id": None,
        "position": "",
    }
    bulk_rows = [dict(empty_bulk_row) for _ in range(5)]

    if (
        request.method == "GET"
        and request.GET.get("preview_bulk_samples") == "1"
    ):
        raw_assignments = request.GET.getlist(
            "bulk_assignment_id"
        )
        raw_destinations = request.GET.getlist(
            "bulk_destination_id"
        )
        raw_positions = request.GET.getlist(
            "bulk_position"
        )

        if not (
            1 <= len(raw_assignments) <= 50
            and len(raw_assignments) == len(raw_destinations)
            and len(raw_assignments) == len(raw_positions)
        ):
            bulk_preview_error = "Invalid bulk preview fields."
        else:
            requested_moves = []
            display_rows = []
            invalid = False

            def valid_bulk_id(value):
                return (
                    1 <= len(value) <= 18
                    and value.isascii()
                    and value.isdecimal()
                    and int(value) > 0
                )

            for raw_aid, raw_did, raw_position in zip(
                raw_assignments,
                raw_destinations,
                raw_positions,
            ):
                aid = raw_aid.strip()
                did = raw_did.strip()
                position = raw_position.strip()

                if not aid and not did and not position:
                    display_rows.append(dict(empty_bulk_row))
                    continue

                if not (
                    valid_bulk_id(aid)
                    and valid_bulk_id(did)
                    and len(position) <= 100
                ):
                    invalid = True
                    display_rows.append(dict(empty_bulk_row))
                    continue

                assignment_id = int(aid)
                destination_id = int(did)

                display_rows.append({
                    "assignment_id": assignment_id,
                    "destination_id": destination_id,
                    "position": position,
                })

                requested_moves.append({
                    "assignment_id": assignment_id,
                    "destination_id": destination_id,
                    "position": position,
                })

            bulk_rows = (
                display_rows
                + [dict(empty_bulk_row) for _ in range(5)]
            )[:max(5, len(display_rows))]

            if invalid:
                bulk_preview_error = (
                    "Each selected row needs a valid assignment, "
                    "destination and position of at most 100 characters."
                )
            elif not requested_moves:
                bulk_preview_error = (
                    "Select at least one Sample assignment."
                )
            else:
                try:
                    bulk_preview = preview_sample_movements(
                        moves=requested_moves,
                        actor=request.user,
                    )
                except ValidationError as exc:
                    bulk_preview_error = "; ".join(exc.messages)

    from core.permissions.storage_workspaces_v8 import (
        visible_storage_locations_for_user,
    )

    locations = list(
        visible_storage_locations_for_user(request.user)
        .select_related(
            "parent",
            "layout_v8146c3",
        )
        .annotate(
            active_sample_count=Count(
                "sample_assignments__sample_id",
                filter=Q(
                    sample_assignments__status="active",
                    sample_assignments__sample_id__in=(
                        visible_samples_for_user(request.user)
                        .filter(is_active=True)
                        .values("pk")
                    ),
                ),
                distinct=True,
            )
        )
        .order_by(
            "parent_id",
            "rank",
            "name",
            "pk",
        )
    )

    location_rows = (
        _flatten_storage_locations(
            locations
        )
    )

    # Match the V8 infrastructure service authorization.
    # A user may manage one workspace while viewing another.
    storage_admin_v8 = is_storage_global_admin(request.user)
    manageable_ids_v8 = set(manageable_workspace_ids_v8)
    storage_nodes_by_id_v8 = {
        location.pk: location
        for location in locations
    }

    for row in location_rows:
        location = row["location"]

        allowed = (
            storage_admin_v8
            or (
                location.workspace_id is not None
                and location.workspace_id in manageable_ids_v8
            )
        )

        # Mixed-workspace or cyclic ancestry is never editable.
        ancestor_id = location.pk
        visited_ids = set()

        while allowed and ancestor_id is not None:
            if ancestor_id in visited_ids:
                allowed = False
                break

            visited_ids.add(ancestor_id)
            ancestor = storage_nodes_by_id_v8.get(ancestor_id)

            if (
                ancestor is None
                or ancestor.workspace_id != location.workspace_id
            ):
                allowed = False
                break

            ancestor_id = ancestor.parent_id

        row["can_manage_location_v8"] = allowed


    active_locations = [
        location
        for location in locations
        if location.is_active
    ]

    visible_samples = (
        visible_samples_for_user(
            request.user
        )
        .filter(
            is_active=True
        )
        .order_by(
            "sample_id"
        )
    )

    # Physical storage details require Storage-specific access.
    # General Sample visibility, including is_public=True, is
    # not permission to inspect freezer, box or position.
    from core.permissions.storage_workspaces_v8 import (
        can_operate_on_sample_storage,
    )

    storage_authorized_sample_ids = [
        sample.pk
        for sample in visible_samples
        if can_operate_on_sample_storage(
            request.user, sample
        )
    ]

    visible_samples = visible_samples.filter(
        pk__in=storage_authorized_sample_ids
    )

    editable_samples = [
        sample
        for sample in visible_samples
        if can_edit_sample(
            request.user,
            sample,
        )
    ]

    visible_sample_ids = [
        sample.pk
        for sample in visible_samples
    ]

    assignments = (
        SampleStorageAssignment.objects
        .select_related(
            "sample",
            "location",
        )
        .filter(
            sample_id__in=(
                visible_sample_ids
            ),
            status="active",
            location_id__in=[
                location.pk for location in locations
            ],
        )
        .order_by(
            "sample__sample_id",
            "rank",
            "id",
        )
    )

    # Read-only compatibility projection. Do not create physical
    # locations or assignments from historical free-text paths.
    from core.services.storage_legacy_projection import (
        build_legacy_storage_projection,
    )

    historical_records = (
        visible_samples
        .exclude(storage_location__isnull=True)
        .exclude(storage_location__exact="")
        .exclude(
            pk__in=assignments.values("sample_id")
        )
        .values_list("pk", "sample_id", "storage_location")
    )

    storage_legacy_projection = (
        build_legacy_storage_projection(historical_records)
    )
    from django.urls import reverse
    for sample in storage_legacy_projection["samples"]:
        if sample.get("id") is not None:
            sample["url"] = reverse(
                "sample_detail", args=[sample["id"]]
            )

    ctx = base_context(
        request
    )

    ctx.update(
        {
            "storage_location_rows": (
                location_rows
            ),
            "storage_locations": (
                locations
            ),
            "active_storage_locations": (
                active_locations
            ),
            "storage_assignments": (
                assignments
            ),
            "storage_legacy_projection": storage_legacy_projection,
            "storage_sample_bulk_preview": bulk_preview,
            "storage_sample_bulk_preview_error": bulk_preview_error,
            "storage_sample_bulk_rows": bulk_rows,
            "storage_sample_preview": sample_preview,
            "storage_sample_preview_error": sample_preview_error,
            "storage_preview_assignment_id": sample_preview_assignment_id,
            "storage_preview_sample_destination_id": sample_preview_destination_id,
            "storage_preview_sample_position": sample_preview_position,
            "storage_preview_editable_assignments": (
                assignments.filter(
                    sample_id__in=[
                        sample.pk for sample in editable_samples
                    ]
                )
            ),
            "storage_container_preview": container_preview,
            "storage_container_preview_error": container_preview_error,
            "storage_preview_container_id": preview_container_id,
            "storage_preview_destination_id": preview_destination_id,
            "storage_movements": (
                visible_storage_movements(
                    request.user,
                    limit=20,
                ).prefetch_related("items")
            ),
            "editable_storage_samples": (
                editable_samples
            ),
            "storage_visible_workspaces_v8": storage_visible_workspaces_v8,
            "b3s_selected_storage_pk_v8147": b3s_selected_storage_pk_v8147,
            "storage_manageable_workspaces_v8": storage_manageable_workspaces_v8,
            "storage_parent_choices_v8": storage_parent_choices_v8,
            "storage_group_choices_v8": storage_group_choices_v8,
            "can_manage_location_storage_v8": bool(storage_manageable_workspaces_v8),
            "storage_is_global_admin_v8": is_storage_global_admin(
                request.user
            ),
            "can_manage_storage": (
                can_manage
            ),
            "storage_location_types": (
                StorageLocation
                .LOCATION_TYPE_CHOICES
            ),
            "storage_total": len(
                locations
            ),
            "storage_active_total": len(
                active_locations
            ),
            "storage_assignment_total": (
                assignments.count()
            ),
        }
    )

    # V8 scene configuration is private to the requesting user.
    # It does not mutate inventory or supply Sample occupancy.
    from core.models.samples.storage import (
        StorageSceneConfiguration,
    )
    from core.services.storage_scene_configuration_v8 import (
        get_storage_scene_projection,
    )

    scene_configs = (
        StorageSceneConfiguration.objects
        .filter(owner=request.user)
        .select_related("root_location")
        .order_by("name", "pk")
    )

    requested_scene_id = (
        request.GET.get("scene", "") or ""
    ).strip()

    selected_scene = None
    scene_projection = None
    scene_error = ""

    if (
        requested_scene_id.isascii()
        and requested_scene_id.isdigit()
        and len(requested_scene_id) <= 18
    ):
        selected_scene = (
            scene_configs
            .filter(pk=int(requested_scene_id))
            .first()
        )

        if selected_scene is not None:
            try:
                scene_projection = get_storage_scene_projection(
                    actor=request.user,
                    configuration_id=selected_scene.pk,
                )
            except ValidationError as exc:
                scene_error = "; ".join(exc.messages)
            except PermissionDenied:
                scene_error = (
                    "This saved scene is no longer accessible."
                )

    def eligible_scene_root(location):
        visited = set()
        node = location

        while node is not None:
            if node.pk in visited or not node.is_active:
                return False

            visited.add(node.pk)
            node = node.parent

        return True

    scene_roots = [
        location for location in active_locations
        if eligible_scene_root(location)
    ]

    ctx.update({
        "storage_scene_configs_v8": scene_configs,
        "storage_scene_selected_v8": selected_scene,
        "storage_scene_projection_v8": scene_projection,
        "storage_scene_error_v8": scene_error,
        "storage_scene_roots_v8": scene_roots,
        "storage_scene_profiles_v8": (
            StorageSceneConfiguration.PROFILE_CHOICES
        ),
    })

    # V8.14 is the canonical Storage interface.
    # Historical records remain read-only projections.
    # The old interface is retained only as a
    # temporary compatibility route for workflows
    # that have not yet been migrated.
    if request.GET.get("legacy") == "1":
        return render(
            request,
            "internal/storage/index.html",
            ctx,
        )

    visible_location_ids_v814 = [
        location.pk for location in locations
    ]

    ctx["storage_v814_assignments"] = assignments.filter(
        location_id__in=visible_location_ids_v814
    )

    return render(
        request,
        "internal/storage/index_v814.html",
        ctx,
    )
