from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models.samples.enrichment import (
    SampleTaxonomyAssignment,
    SampleTaxonomyReview,
)


HUMAN_REVIEW_STATUSES = {
    SampleTaxonomyAssignment.STATUS_VERIFIED,
    SampleTaxonomyAssignment.STATUS_CONFLICT,
}


def review_taxonomy_assignment(
    *,
    assignment,
    reviewer,
    new_status,
    note="",
):
    """
    Record one human taxonomy decision and update the assignment's
    latest review state atomically.

    Conflict decisions require an explanatory note.
    Repeating the current status is rejected rather than generating
    a meaningless duplicate audit event.
    """

    status = str(
        new_status or ""
    ).strip().lower()

    cleaned_note = str(
        note or ""
    ).strip()

    if status not in HUMAN_REVIEW_STATUSES:
        raise ValidationError(
            "Taxonomy review status must be "
            "Verified or Conflict."
        )

    if (
        status
        == SampleTaxonomyAssignment
        .STATUS_CONFLICT
        and not cleaned_note
    ):
        raise ValidationError(
            "A review note is required when "
            "marking taxonomy as Conflict."
        )

    with transaction.atomic():
        locked = (
            SampleTaxonomyAssignment
            .objects
            .select_for_update()
            .get(
                pk=assignment.pk
            )
        )

        previous_status = (
            locked.match_status
        )

        if previous_status == status:
            raise ValidationError(
                "The taxonomy assignment already "
                f"has status "
                f"{locked.get_match_status_display()}."
            )

        review = (
            SampleTaxonomyReview
            .objects
            .create(
                assignment=locked,
                previous_status=previous_status,
                new_status=status,
                reviewer=reviewer,
                note=cleaned_note,
            )
        )

        locked.match_status = status
        locked.reviewed_by = reviewer
        locked.reviewed_at = (
            review.reviewed_at
            or timezone.now()
        )

        locked.save(
            update_fields=[
                "match_status",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

    return review
