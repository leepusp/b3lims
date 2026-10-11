"""Permission-scoped, read-only Storage movement history."""

from django.db.models import Exists, OuterRef, Q

from core.models.samples.storage import (
    StorageMovement,
    StorageMovementItem,
)
from core.permissions.samples import visible_samples_for_user
from core.permissions.storage import (
    can_manage_storage_infrastructure,
)


def visible_storage_movements(user, *, limit=20):
    """
    Return recent movement events safe to display to this user.

    A movement involving Samples is visible only when every
    historical item references a currently visible Sample.

    Events with missing/deleted Sample references are hidden.
    Empty infrastructure movements require management permission.
    """
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("History limit must be between 1 and 50.")

    if (
        user is None
        or not getattr(user, "is_authenticated", False)
    ):
        return StorageMovement.objects.none()

    visible_ids = (
        visible_samples_for_user(user)
        .filter(is_active=True)
        .values("pk")
    )

    items = StorageMovementItem.objects.filter(
        movement_id=OuterRef("pk")
    )

    inaccessible_items = items.filter(
        Q(sample_id__isnull=True)
        | ~Q(sample_id__in=visible_ids)
    )

    queryset = (
        StorageMovement.objects
        .annotate(
            _has_items=Exists(items),
            _has_inaccessible_items=Exists(inaccessible_items),
        )
        .filter(_has_inaccessible_items=False)
    )

    if can_manage_storage_infrastructure(user):
        queryset = queryset.filter(
            Q(_has_items=True)
            | Q(
                _has_items=False,
                affected_sample_count=0,
                affected_assignment_count=0,
            )
        )
    else:
        queryset = queryset.filter(_has_items=True)

    return queryset.order_by(
        "-created_at",
        "-pk",
    )[:limit]
