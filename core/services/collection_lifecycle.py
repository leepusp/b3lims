from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.db import transaction

from core.models import (
    Collection,
    CollectionLifecycleEvent,
)
from core.permissions.collections import (
    can_delete_collection,
)


def _validate_collection(
    collection,
):
    """
    Enforce the Collection-specific lifecycle boundary.
    """
    if not isinstance(
        collection,
        Collection,
    ):
        raise ValidationError(
            "Collection lifecycle operations require a Collection."
        )

    if collection.pk is None:
        raise ValidationError(
            "A saved Collection is required."
        )


@transaction.atomic
def deactivate_collection(
    *,
    collection,
    actor,
):
    """
    Deactivate one Collection and append its audit event atomically.

    Repeated deactivation is idempotent: an already inactive
    Collection is returned without appending another event.
    """
    _validate_collection(
        collection
    )

    locked_collection = (
        Collection.objects
        .select_for_update()
        .select_related(
            "owner",
            "research_group",
        )
        .get(
            pk=collection.pk,
        )
    )

    if not can_delete_collection(
        actor,
        locked_collection,
    ):
        raise PermissionDenied(
            "You do not have permission to deactivate this Collection."
        )

    if not locked_collection.is_active:
        return locked_collection

    locked_collection.is_active = False

    locked_collection.save(
        update_fields=[
            "is_active",
            "updated_at",
        ]
    )

    CollectionLifecycleEvent.objects.create(
        collection=locked_collection,
        event_type=(
            CollectionLifecycleEvent
            .EventType
            .DEACTIVATED
        ),
        actor=actor,
        notes="Collection deactivated.",
    )

    return locked_collection
