from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import ResourceAccessGrant


ACCESS_RANK = {
    ResourceAccessGrant.AccessLevel.VIEW: 1,
    ResourceAccessGrant.AccessLevel.EDIT: 2,
    ResourceAccessGrant.AccessLevel.MANAGE: 3,
}


def _resource_identity(resource):
    if resource is None or resource.pk is None:
        raise ValidationError(
            "A saved resource is required."
        )

    return (
        ContentType.objects.get_for_model(
            resource,
            for_concrete_model=False,
        ),
        str(resource.pk),
    )


def active_resource_grants(resource):
    """Return non-revoked, non-expired explicit grants for a resource."""
    content_type, object_id = _resource_identity(
        resource,
    )
    now = timezone.now()

    return (
        ResourceAccessGrant.objects.filter(
            content_type=content_type,
            object_id=object_id,
            revoked_at__isnull=True,
        )
        .filter(
            Q(expires_at__isnull=True)
            | Q(expires_at__gt=now)
        )
    )


def resource_grants_for_user(user, resource):
    """Return active direct and Research Group grants for a user."""
    grants = active_resource_grants(
        resource,
    )

    if not user or not user.is_authenticated:
        return grants.none()

    return (
        grants.filter(
            Q(user=user)
            | Q(research_group__coordinator=user)
            | Q(research_group__members=user)
        )
        .distinct()
    )


def has_explicit_resource_access(
    user,
    resource,
    required_level=ResourceAccessGrant.AccessLevel.VIEW,
):
    """Evaluate explicit grants only; ownership stays resource-specific."""
    required_rank = ACCESS_RANK.get(
        required_level,
    )

    if required_rank is None:
        raise ValidationError(
            f"Unsupported access level: {required_level}"
        )

    if not user or not user.is_authenticated:
        return False

    return any(
        ACCESS_RANK[grant.access_level] >= required_rank
        for grant in resource_grants_for_user(
            user,
            resource,
        ).only("access_level")
    )


@transaction.atomic
def grant_resource_access(
    *,
    resource,
    access_level,
    granted_by,
    user=None,
    research_group=None,
    expires_at=None,
):
    """Create or update an active grant for one resource/principal."""
    if bool(user) == bool(research_group):
        raise ValidationError(
            "Select exactly one grant principal: user or research group."
        )

    if access_level not in ACCESS_RANK:
        raise ValidationError(
            f"Unsupported access level: {access_level}"
        )

    content_type, object_id = _resource_identity(
        resource,
    )

    if user is not None:
        principal_filter = {
            "user": user,
        }
    else:
        principal_filter = {
            "research_group": research_group,
        }

    grant = (
        ResourceAccessGrant.objects
        .select_for_update()
        .filter(
            content_type=content_type,
            object_id=object_id,
            revoked_at__isnull=True,
            **principal_filter,
        )
        .first()
    )

    if grant is None:
        grant = ResourceAccessGrant(
            content_type=content_type,
            object_id=object_id,
            user=user,
            research_group=research_group,
        )

    grant.access_level = access_level
    grant.granted_by = granted_by
    grant.expires_at = expires_at
    grant.revoked_at = None
    grant.revoked_by = None

    grant.full_clean()
    grant.save()

    return grant


@transaction.atomic
def revoke_resource_access(*, grant, revoked_by):
    """Idempotently revoke a grant while retaining its audit history."""
    locked = (
        ResourceAccessGrant.objects
        .select_for_update()
        .get(pk=grant.pk)
    )

    if locked.revoked_at is None:
        locked.revoked_at = timezone.now()
        locked.revoked_by = revoked_by

        locked.full_clean()

        locked.save(
            update_fields=(
                "revoked_at",
                "revoked_by",
                "updated_at",
            )
        )

    return locked
