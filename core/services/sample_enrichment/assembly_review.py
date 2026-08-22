from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models.samples.enrichment import (
    SampleGenomeAssemblyAssignment,
    SampleGenomeAssemblyReview,
)


ASSEMBLY_HUMAN_REVIEW_STATUSES = {
    SampleGenomeAssemblyAssignment.STATUS_VERIFIED,
    SampleGenomeAssemblyAssignment.STATUS_CONFLICT,
}


def review_genome_assembly_assignment(
    *,
    assignment,
    reviewer,
    new_status,
    note="",
):
    """
    Record one human Genome Assembly decision atomically.

    Conflict decisions require an explanatory note. Repeating the
    current status is rejected rather than generating a duplicate
    review-history event.
    """

    status = str(
        new_status or ""
    ).strip().lower()

    cleaned_note = str(
        note or ""
    ).strip()

    if (
        status
        not in ASSEMBLY_HUMAN_REVIEW_STATUSES
    ):
        raise ValidationError(
            "Genome Assembly review status must be "
            "Verified or Conflict."
        )

    if (
        status
        == SampleGenomeAssemblyAssignment
        .STATUS_CONFLICT
        and not cleaned_note
    ):
        raise ValidationError(
            "A review note is required when marking "
            "a Genome Assembly as Conflict."
        )

    with transaction.atomic():
        locked = (
            SampleGenomeAssemblyAssignment
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
                "The Genome Assembly assignment already "
                f"has status "
                f"{locked.get_match_status_display()}."
            )

        review = (
            SampleGenomeAssemblyReview
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
