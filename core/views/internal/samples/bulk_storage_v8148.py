"""Preview, validate and confirm a selection of physical Sample assignments.

No storage writes happen during selection or preview. All confirmation writes
reuse existing audited registration/movement services under one transaction.
"""
import re
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models.samples.sample import Sample
from core.models.samples.storage import StorageLocation
from core.permissions.storage_workspaces_v8 import (
    can_operate_on_sample_storage,
    can_register_at_storage_location,
    can_view_storage_location,
    visible_storage_locations_for_user,
)
from core.services.storage_anchor_v8 import validate_storage_anchor_plan
from core.services.storage_registration_v8 import register_initial_physical_storage
from core.services.storage_sample_movement_preview import preview_sample_movements
from core.services.storage_sample_movements import move_samples_bulk

MAX_SELECTED = 50
SIGNING_SALT = "b3lims.sample_bulk_storage_v8148"
POSITION_PATTERN = re.compile(r"[A-Z]+[0-9]+\Z")


def _ids(values):
    if not 1 <= len(values) <= MAX_SELECTED:
        raise ValidationError("Select between 1 and 50 Samples.")
    if any(not str(v).isdigit() or len(str(v)) > 18 for v in values):
        raise ValidationError("Invalid Sample selection.")
    ids = [int(v) for v in values]
    if len(set(ids)) != len(ids) or any(i < 1 for i in ids):
        raise ValidationError("Each Sample must be selected once.")
    return ids


def _rows(actor, ids, *, lock=False):
    qs = Sample.objects.filter(pk__in=ids, is_active=True)
    if lock:
        qs = qs.select_for_update()
    samples = {s.pk: s for s in qs}
    if len(samples) != len(ids):
        raise ValidationError("One or more Samples are no longer available.")
    rows = []
    for pk in ids:
        sample = samples[pk]
        # Check before displaying physical assignments to prevent data leakage.
        if not can_operate_on_sample_storage(actor, sample):
            raise PermissionDenied("Storage operation is not authorized for the selection.")
        assignments = list(
            sample.storage_assignments.select_related("location")
            .filter(status="active").order_by("rank", "pk")
        )
        if assignments:
            primary = [a for a in assignments if a.is_primary]
            if len(primary) != 1:
                raise ValidationError(
                    "A selected Sample has an ambiguous primary storage assignment."
                )
            assignment = primary[0]
            if not can_view_storage_location(actor, assignment.location):
                raise PermissionDenied("Storage source is not accessible.")
            kind = "move"
            old_path = assignment.location.full_path
        else:
            if sample.storage_assignments.exists():
                raise ValidationError(
                    "A selected Sample has historical assignments requiring reconciliation."
                )
            if (sample.storage_location or "").strip():
                raise ValidationError(
                    "A historical text path must be reconciled before assignment."
                )
            assignment = None
            kind = "register"
            old_path = "Unassigned"
        rows.append({
            "sample": sample,
            "kind": kind,
            "assignment": assignment,
            "old_path": old_path,
            "snapshot": [
                sample.pk,
                assignment.pk if assignment else None,
                assignment.location_id if assignment else None,
                assignment.position if assignment else "",
                sample.storage_location or "",
            ],
        })
    return rows


def _destinations(actor):
    return [location for location in
        visible_storage_locations_for_user(actor).select_related("workspace", "parent")
        .filter(is_active=True, location_type__in=("box", "rack", "other"))
        .order_by("workspace_id", "name", "pk")
        if can_register_at_storage_location(actor, location)
    ]


def _review(actor, ids, dest_id, positions, *, lock=False):
    rows = _rows(actor, ids, lock=lock)
    if not str(dest_id).isdigit():
        raise ValidationError("Select a registered physical destination.")
    destination = get_object_or_404(StorageLocation, pk=int(dest_id))
    if not can_register_at_storage_location(actor, destination):
        raise PermissionDenied("The physical destination is not authorized.")
    if destination.location_type not in ("box", "rack", "other"):
        raise ValidationError("Select a Box, Rack or custom position host.")
    if len(positions) != len(rows):
        raise ValidationError("Provide one position per selected Sample.")
    positions = [str(p).strip().upper() for p in positions]
    if any(not POSITION_PATTERN.fullmatch(p) or len(p) > 100 for p in positions):
        raise ValidationError("Use unique positions such as A1 or P03.")
    if len(set(positions)) != len(positions):
        raise ValidationError("Duplicate destination positions are not allowed.")

    moves = []
    fresh = []
    for row, position in zip(rows, positions):
        row["position"] = position
        if row["kind"] == "move":
            moves.append({
                "assignment_id": row["assignment"].pk,
                "destination_id": destination.pk,
                "position": position,
            })
        else:
            fresh.append(position)

    # Preview services recheck authorization, occupancy, duplicate slots and
    # hierarchy integrity. Neither preview writes database records.
    move_preview = (
        preview_sample_movements(moves=moves, actor=actor)
        if moves else {"moves": []}
    )
    if fresh:
        validate_storage_anchor_plan(
            mode="physical", box_id=destination.pk,
            positions=fresh, expected_samples=len(fresh), actor=actor,
        )
    return rows, destination, move_preview


def _page(request, *, rows, destinations=None, stage="choose", error="",
          destination=None, confirm_token="", selection_ids=None):
    return render(request, "internal/samples/bulk_storage_v8148.html", {
        "bulk_rows": rows,
        "bulk_destinations": destinations if destinations is not None else [],
        "bulk_stage": stage,
        "bulk_error": error,
        "bulk_destination": destination,
        "bulk_token": confirm_token,
        "bulk_ids": selection_ids or [r["sample"].pk for r in rows],
    }, status=400 if error else 200)


@login_required
@require_POST
def sample_bulk_storage_view(request):
    action = request.POST.get("action", "choose")
    if action not in ("choose", "preview", "confirm"):
        return HttpResponseBadRequest("Invalid bulk storage action.")

    if action == "confirm":
        try:
            payload = signing.loads(
                request.POST.get("confirm_token", ""),
                salt=SIGNING_SALT, max_age=900,
            )
            ids = _ids(payload["sample_ids"])
            positions = payload["positions"]
            dest_id = payload["destination_id"]
            snapshot = payload["snapshot"]
            reason = request.POST.get("reason", "").strip()
            if not 1 <= len(reason) <= 2000:
                raise ValidationError("Provide a movement or registration reason.")
            with transaction.atomic():
                rows, dest, move_preview = _review(
                    request.user, ids, dest_id, positions, lock=True,
                )
                if [r["snapshot"] for r in rows] != snapshot:
                    raise ValidationError("Storage changed since preview. Review again.")
                # Existing service handles all active assignment moves in one
                # audited, atomic batch; initial registrations are audited
                # individually and share this outer atomic transaction.
                if move_preview["moves"]:
                    move_samples_bulk(
                        moves=[{
                            "assignment_id": item["assignment_id"],
                            "destination_id": item["destination_id"],
                            "position": item["position_after"],
                            "expected_location_id": item["expected_location_id"],
                            "expected_position": item["expected_position"],
                            "expected_source_path": item["expected_source_path"],
                            "expected_destination_path": item["expected_destination_path"],
                        } for item in move_preview["moves"]],
                        actor=request.user, reason=reason,
                    )
                for row in rows:
                    if row["kind"] == "register":
                        register_initial_physical_storage(
                            sample=row["sample"], box=dest,
                            position=row["position"], actor=request.user,
                            mode="new", expected_legacy_path="", reason=reason,
                        )
            messages.success(
                request,
                f"Physical storage updated for {len(ids)} selected Sample(s).",
            )
            return redirect("samples_list")
        except signing.BadSignature:
            return HttpResponseBadRequest("Selection confirmation expired or is invalid.")
        except IntegrityError:
            return HttpResponseBadRequest("Storage confirmation rejected: state changed or a slot is occupied.")
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return HttpResponseBadRequest("Storage confirmation rejected: " + str(exc))

    try:
        ids = _ids(request.POST.getlist("sample_ids"))
        if action == "choose":
            rows = _rows(request.user, ids)
            return _page(
                request, rows=rows, destinations=_destinations(request.user),
            )
        positions = [
            request.POST.get("position_" + str(pk), "") for pk in ids
        ]
        rows, dest, move_preview = _review(
            request.user, ids,
            request.POST.get("destination_id", ""), positions,
        )
        token = signing.dumps({
            "sample_ids": ids, "positions": [r["position"] for r in rows],
            "destination_id": dest.pk,
            "snapshot": [r["snapshot"] for r in rows],
        }, salt=SIGNING_SALT)
        return _page(
            request, rows=rows, stage="confirm", destination=dest,
            confirm_token=token,
        )
    except (ValidationError, ValueError, TypeError) as exc:
        return HttpResponseBadRequest("Bulk storage selection rejected: " + str(exc))
