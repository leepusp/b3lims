"""Validate and execute confirmed Storage Workspace transfers."""

from django.core.exceptions import ValidationError

from core.models.samples.storage import StorageLocation, SampleStorageAssignment
from core.services.storage_container_movements import move_storage_container
from core.services.storage_sample_movements import move_sample, move_samples_bulk


def _positive_id(raw, name):
    if (
        not isinstance(raw, str)
        or not (1 <= len(raw) <= 18)
        or not raw.isascii()
        or not raw.isdecimal()
        or int(raw) < 1
    ):
        raise ValidationError(f"Invalid {name}.")
    return int(raw)


def _text(raw, name, *, max_length, allow_blank=False):
    if not isinstance(raw, str) or len(raw) > max_length:
        raise ValidationError(f"Invalid {name}.")
    if not allow_blank and not raw.strip():
        raise ValidationError(f"{name} is required.")
    return raw


def _movement_fields(data, prefix=""):
    """Read one complete optimistic movement payload from POST fields."""
    return {
        "assignment_id": _positive_id(data.get(prefix + "assignment_id"), "assignment ID"),
        "destination_id": _positive_id(data.get(prefix + "destination_id"), "destination ID"),
        "position": _text(data.get(prefix + "position"), "position", max_length=100, allow_blank=True).strip(),
        "expected_location_id": _positive_id(data.get(prefix + "expected_location_id"), "source location ID"),
        "expected_position": _text(data.get(prefix + "expected_position"), "original position", max_length=100, allow_blank=True),
        "expected_source_path": _text(data.get(prefix + "expected_source_path"), "source path", max_length=16384),
        "expected_destination_path": _text(data.get(prefix + "expected_destination_path"), "destination path", max_length=16384),
    }


def confirm_storage_workspace_transfer(*, action, data, actor):
    """Execute a transfer; domain services recheck permissions and stale data."""
    reason = _text(data.get("reason"), "Movement reason", max_length=2000).strip()

    try:
        if action == "confirm_sample_move":
            fields = _movement_fields(data)
            return move_sample(actor=actor, reason=reason, **fields)

        if action == "confirm_bulk_sample_move":
            names = (
                "assignment_id", "destination_id", "position",
                "expected_location_id", "expected_position",
                "expected_source_path", "expected_destination_path",
            )
            columns = {name: data.getlist("bulk_" + name) for name in names}
            counts = {len(values) for values in columns.values()}
            if len(counts) != 1 or not (1 <= counts.pop() <= 5):
                raise ValidationError("Select between one and five complete transfers.")

            moves = []
            for i in range(len(columns["assignment_id"])):
                row = {name: values[i] for name, values in columns.items()}
                moves.append(_movement_fields(row))
            return move_samples_bulk(moves=moves, actor=actor, reason=reason)

        if action == "confirm_container_move":
            container_id = _positive_id(data.get("container_id"), "container ID")
            destination_id = _positive_id(data.get("destination_id"), "destination ID")
            original_parent = data.get("expected_parent_id", "")
            parent_id = (
                _positive_id(original_parent, "original parent ID")
                if original_parent else None
            )
            old_path = _text(data.get("expected_origin_path"), "original container path", max_length=16384)
            new_path = _text(data.get("expected_destination_path"), "proposed container path", max_length=16384)
            container = StorageLocation.objects.get(pk=container_id)
            destination = StorageLocation.objects.get(pk=destination_id)
            return move_storage_container(
                container=container, destination=destination, actor=actor,
                expected_parent_id=parent_id, reason=reason,
                expected_origin_path=old_path,
                expected_destination_path=new_path,
            )
    except (StorageLocation.DoesNotExist, SampleStorageAssignment.DoesNotExist) as exc:
        raise ValidationError("The selected Storage record no longer exists.") from exc

    raise ValidationError("Unknown Storage transfer action.")
