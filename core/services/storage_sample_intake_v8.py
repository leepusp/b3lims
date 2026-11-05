"""Plan Sample storage registration without creating physical locations."""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError

from core.services.storage_anchor_v8 import (
    validate_storage_anchor_plan,
)


@dataclass(frozen=True)
class StorageSampleIntakePlan:
    mode: str
    initial_text: str
    target_id: int | None
    positions: tuple[str, ...]


def prepare_storage_sample_intake_v8(
    *,
    mode,
    storage_text,
    anchor_id,
    positions,
    expected_samples,
    actor,
    position_leaf_mode=False,
):
    if (
        isinstance(expected_samples, bool)
        or not isinstance(expected_samples, int)
        or expected_samples < 1
    ):
        raise ValidationError("Invalid number of Samples.")

    if not (
        getattr(actor, "is_authenticated", False)
        and getattr(actor, "is_active", False)
    ):
        raise PermissionDenied("Active authentication required.")

    storage_text = str(storage_text or "").strip()
    anchor_id = str(anchor_id or "").strip()
    positions = tuple(positions or ())
    mode = str(mode or "").strip().lower()

    if not mode:
        mode = "unverified" if storage_text else "unassigned"

    if mode == "unassigned":
        if storage_text or anchor_id or positions:
            raise ValidationError(
                "Unassigned Samples cannot contain a storage destination."
            )

        return StorageSampleIntakePlan(
            "unassigned", "", None, ()
        )

    if mode == "unverified":
        if anchor_id or positions:
            raise ValidationError(
                "Unverified storage cannot contain physical assignments."
            )

        if not storage_text:
            raise ValidationError(
                "Enter a storage path or choose no storage."
            )

        if len(storage_text) > 255:
            raise ValidationError(
                "Storage path exceeds 255 characters."
            )

        parts = [
            part.strip()
            for section in storage_text.split(";")
            for part in section.replace(",", ">").split(">")
        ]

        if (
            not parts
            or any(not part for part in parts)
            or any(len(part) > 150 for part in parts)
        ):
            raise ValidationError(
                "Storage path contains invalid levels."
            )

        return StorageSampleIntakePlan(
            "unverified",
            storage_text,
            None,
            (),
        )

    if mode != "physical":
        raise ValidationError("Invalid storage registration mode.")

    plan = validate_storage_anchor_plan(
        mode="physical",
        box_id=anchor_id,
        positions=positions,
        expected_samples=expected_samples,
        actor=actor,
    )

    # The ID is authoritative. Do not accept a substituted path.
    if position_leaf_mode:
        from core.services.storage_position_names_v8146c2 import (
            normalize_physical_position_v8146c2,
        )

        from core.models.samples.storage import StorageLocation
        from core.services.storage_layout_position import (
            position_for_layout,
        )

        prefix = f"{plan.box_path} > "
        valid_path = storage_text.startswith(prefix)

        if valid_path:
            try:
                valid_path = position_for_layout(
                    StorageLocation.objects.get(pk=plan.box_id),
                    normalize_physical_position_v8146c2(
                        storage_text[len(prefix):]
                    ),
                ) == plan.positions[0]
            except ValidationError:
                valid_path = False
    else:
        valid_path = storage_text == plan.box_path

    if not valid_path:
        raise ValidationError(
            "The selected storage path changed. "
            "Select the registered location again."
        )

    if any(
        len(plan.box_path) + 3 + len(position) > 255
        for position in plan.positions
    ):
        raise ValidationError(
            "Physical storage path exceeds 255 characters."
        )

    # A newly created Sample starts unassigned. The audited
    # registration service writes the canonical final path.
    return StorageSampleIntakePlan(
        "physical",
        "",
        plan.box_id,
        plan.positions,
    )
