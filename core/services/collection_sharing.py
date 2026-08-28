from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from core.models import Collection
from core.permissions.collections import (
    can_manage_collection_permissions,
)
from core.services.resource_access import (
    active_resource_grants,
    grant_resource_access,
    revoke_resource_access,
)


def _validate_collection(
    collection,
):
    """
    Enforce the Collection-specific resource boundary.

    Callers cannot substitute an arbitrary GenericForeignKey target.
    """
    if not isinstance(
        collection,
        Collection,
    ):
        raise ValidationError(
            "Collection sharing requires a Collection resource."
        )

    if collection.pk is None:
        raise ValidationError(
            "A saved Collection is required."
        )


def active_collection_access_grants(
    collection,
):
    """
    Return active explicit grants for one Collection.
    """
    _validate_collection(
        collection
    )

    return active_resource_grants(
        collection
    )


def grant_collection_access(
    *,
    collection,
    access_level,
    granted_by,
    user=None,
    research_group=None,
    expires_at=None,
):
    """
    Grant or update explicit access to one Collection.

    The resource target is fixed by the backend Collection object.
    """
    _validate_collection(
        collection
    )

    if not collection.is_active:
        raise ValidationError(
            "Access cannot be granted to an inactive Collection."
        )

    if not can_manage_collection_permissions(
        granted_by,
        collection,
    ):
        raise PermissionDenied(
            "You do not have permission to manage this Collection's access."
        )

    if (
        user is not None
        and not user.is_active
    ):
        raise ValidationError(
            "Access cannot be granted to an inactive user."
        )

    if (
        user is not None
        and user.pk == collection.owner_id
    ):
        raise ValidationError(
            "The Collection owner already has full access."
        )

    if (
        expires_at is not None
        and expires_at <= timezone.now()
    ):
        raise ValidationError(
            "Access expiration must be in the future."
        )

    return grant_resource_access(
        resource=collection,
        access_level=access_level,
        granted_by=granted_by,
        user=user,
        research_group=research_group,
        expires_at=expires_at,
    )


def revoke_collection_access(
    *,
    collection,
    grant,
    revoked_by,
):
    """
    Revoke one Collection grant while preserving its audit record.
    """
    _validate_collection(
        collection
    )

    if not can_manage_collection_permissions(
        revoked_by,
        collection,
    ):
        raise PermissionDenied(
            "You do not have permission to manage this Collection's access."
        )

    expected_content_type = (
        ContentType.objects
        .get_for_model(
            Collection,
            for_concrete_model=False,
        )
    )

    if (
        grant.content_type_id
        != expected_content_type.pk
        or str(
            grant.object_id
        )
        != str(
            collection.pk
        )
    ):
        raise ValidationError(
            "The selected access grant does not belong to this Collection."
        )

    return revoke_resource_access(
        grant=grant,
        revoked_by=revoked_by,
    )
