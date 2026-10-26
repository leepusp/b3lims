"""Explicit audited physical movement from Edit Sample."""

import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from core.models.samples.sample import Sample
from core.models.samples.storage import SampleStorageAssignment
from core.permissions.samples import can_edit_sample
from core.services.storage_sample_movements import move_sample


def _positive_id(value):
    value = str(value or "").strip()

    if (
        not value
        or len(value) > 18
        or not value.isascii()
        or not value.isdecimal()
        or int(value) <= 0
    ):
        raise ValidationError("Invalid physical storage identifier.")

    return int(value)


@login_required
@require_POST
def sample_storage_move_v8146(request, sample_id):
    """
    Move exactly one existing physical assignment.

    Ignore all biological metadata submitted by the surrounding
    Edit Sample form. The movement service owns locking, occupancy,
    legacy synchronization and physical audit.
    """
    sample = get_object_or_404(Sample, pk=sample_id)

    if not (
        request.user.is_superuser
        or can_edit_sample(request.user, sample)
    ):
        raise PermissionDenied(
            "You cannot edit this Sample."
        )

    try:
        assignment_id = _positive_id(
            request.POST.get("storage_move_assignment_v8146")
        )

        destination_id = _positive_id(
            request.POST.get("storage_move_destination_v8146")
        )

        expected_location_id = _positive_id(
            request.POST.get("storage_move_expected_location_v8146")
        )

        assignment = get_object_or_404(
            SampleStorageAssignment,
            pk=assignment_id,
            sample_id=sample.pk,
            status="active",
        )

        position = str(
            request.POST.get("storage_move_position_v8146") or ""
        ).strip().upper()

        if re.fullmatch(r"[A-Z]+[0-9]+", position) is None:
            raise ValidationError(
                "Enter a physical position such as A1 or B5."
            )

        reason = str(
            request.POST.get("storage_move_reason_v8146") or ""
        ).strip()

        if not reason:
            raise ValidationError(
                "A reason is required for physical movement."
            )

        move_sample(
            assignment_id=assignment.pk,
            destination_id=destination_id,
            position=position,
            expected_location_id=expected_location_id,
            expected_position=request.POST.get(
                "storage_move_expected_position_v8146", ""
            ),
            expected_source_path=request.POST.get(
                "storage_move_expected_source_path_v8146", ""
            ),
            expected_destination_path=request.POST.get(
                "storage_move_expected_destination_path_v8146", ""
            ),
            actor=request.user,
            reason=reason,
        )

    except ValidationError as exc:
        messages.error(
            request,
            " ".join(exc.messages),
        )
        return redirect("sample_edit", sample_id=sample.pk)

    messages.success(
        request,
        "Physical Sample location updated with movement audit.",
    )

    return redirect("sample_edit", sample_id=sample.pk)
