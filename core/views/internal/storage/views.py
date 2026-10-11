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
    can_manage = (
        can_manage_storage_infrastructure(
            request.user
        )
    )

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

            elif action == "create_location":
                if not can_manage:
                    raise PermissionDenied(
                        (
                            "You cannot manage the "
                            "physical storage infrastructure."
                        )
                    )

                parent_id = (
                    request.POST.get(
                        "parent_id",
                        "",
                    )
                    .strip()
                )

                parent = None

                if parent_id:
                    parent = get_object_or_404(
                        StorageLocation,
                        pk=parent_id,
                    )

                location = create_storage_location(
                    name=request.POST.get(
                        "name",
                        "",
                    ),
                    parent=parent,
                    location_type=(
                        request.POST.get(
                            "location_type",
                            "other",
                        )
                    ),
                    rank=request.POST.get(
                        "rank",
                        "1",
                    ),
                    notes=request.POST.get(
                        "notes",
                        "",
                    ),
                )

                messages.success(
                    request,
                    (
                        "Storage location created: "
                        f"{location.full_path}"
                    ),
                )

            elif action == "update_location":
                if not can_manage:
                    raise PermissionDenied(
                        (
                            "You cannot manage the "
                            "physical storage infrastructure."
                        )
                    )

                location = get_object_or_404(
                    StorageLocation,
                    pk=request.POST.get(
                        "location_id"
                    ),
                )

                update_storage_location(
                    location,
                    name=request.POST.get(
                        "name",
                        "",
                    ),
                    location_type=(
                        request.POST.get(
                            "location_type",
                            "other",
                        )
                    ),
                    rank=request.POST.get(
                        "rank",
                        "1",
                    ),
                    notes=request.POST.get(
                        "notes",
                        "",
                    ),
                )

                messages.success(
                    request,
                    "Storage location updated.",
                )

            elif action in {
                "deactivate_location",
                "reactivate_location",
            }:
                if not can_manage:
                    raise PermissionDenied(
                        (
                            "You cannot manage the "
                            "physical storage infrastructure."
                        )
                    )

                location = get_object_or_404(
                    StorageLocation,
                    pk=request.POST.get(
                        "location_id"
                    ),
                )

                set_storage_location_active(
                    location,
                    is_active=(
                        action
                        == "reactivate_location"
                    ),
                )

                messages.success(
                    request,
                    (
                        "Storage location "
                        + (
                            "reactivated."
                            if location.is_active
                            else "deactivated."
                        )
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

                if not can_edit_sample(
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

                active_assignments = list(
                    sample.storage_assignments
                    .select_related("location")
                    .filter(status="active")
                    .order_by("rank", "id")
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
        if not can_manage:
            raise PermissionDenied(
                "Only infrastructure managers may preview "
                "container-wide movements."
            )

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
            1 <= len(raw_assignments) <= 5
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
            )[:5]

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

    locations = list(
        StorageLocation.objects
        .select_related(
            "parent"
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
        )
        .order_by(
            "sample__sample_id",
            "rank",
            "id",
        )
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

    return render(
        request,
        "internal/storage/index.html",
        ctx,
    )
