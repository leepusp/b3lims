from core.models.access_grants import (
    ResourceAccessGrant,
)
from core.permissions.generic import (
    can_delete_object,
    can_edit_object,
    can_view_object,
)
from core.services.resource_access import (
    has_explicit_resource_access,
)


def _is_authenticated(user):
    return bool(
        user
        and getattr(
            user,
            "is_authenticated",
            False,
        )
    )


def _is_admin(user):
    return bool(
        _is_authenticated(
            user
        )
        and (
            getattr(
                user,
                "is_superuser",
                False,
            )
            or getattr(
                user,
                "is_staff",
                False,
            )
        )
    )


def _is_owner(
    user,
    collection,
):
    return bool(
        _is_authenticated(
            user
        )
        and getattr(
            collection,
            "owner_id",
            None,
        )
        == getattr(
            user,
            "id",
            None,
        )
    )


def _research_group(
    collection,
):
    return getattr(
        collection,
        "research_group",
        None,
    )


def _is_group_coordinator(
    user,
    collection,
):
    if not _is_authenticated(
        user
    ):
        return False

    group = _research_group(
        collection
    )

    return bool(
        group
        and getattr(
            group,
            "coordinator_id",
            None,
        )
        == getattr(
            user,
            "id",
            None,
        )
    )


def _has_group_access(
    user,
    collection,
):
    if not _is_authenticated(
        user
    ):
        return False

    group = _research_group(
        collection
    )

    if group is None:
        return False

    if _is_group_coordinator(
        user,
        collection,
    ):
        return True

    return group.members.filter(
        pk=user.pk
    ).exists()


def _has_explicit_access(
    user,
    collection,
    access_level,
):
    if not _is_authenticated(
        user
    ):
        return False

    return has_explicit_resource_access(
        user,
        collection,
        required_level=access_level,
    )


def can_view_collection(
    user,
    collection,
):
    """
    Return whether the user may view Collection metadata.

    Existing ownership, administrator, public, and Research Group
    behavior is preserved. Explicit ResourceAccessGrant records add
    cross-group access without changing Research Group membership.
    """
    if can_view_object(
        user,
        collection,
    ):
        return True

    if _has_group_access(
        user,
        collection,
    ):
        return True

    return _has_explicit_access(
        user,
        collection,
        ResourceAccessGrant.AccessLevel.VIEW,
    )


def can_edit_collection(
    user,
    collection,
):
    """
    Return whether the user may edit Collection metadata.

    Research Group members retain their existing edit capability.
    Explicit EDIT or MANAGE grants also provide edit access.
    """
    if can_edit_object(
        user,
        collection,
    ):
        return True

    if _has_group_access(
        user,
        collection,
    ):
        return True

    return _has_explicit_access(
        user,
        collection,
        ResourceAccessGrant.AccessLevel.EDIT,
    )


def can_delete_collection(
    user,
    collection,
):
    """
    Return whether the user may deactivate or delete a Collection.

    Destructive lifecycle authority is intentionally narrower than
    explicit sharing authority. A MANAGE grant does not imply DELETE.
    """
    if can_delete_object(
        user,
        collection,
    ):
        return True

    return _is_group_coordinator(
        user,
        collection,
    )


def can_manage_collection_permissions(
    user,
    collection,
):
    """
    Return whether the user may delegate Collection access.

    Management belongs to administrators, the Collection owner,
    the Research Group coordinator, or a principal holding an
    explicit MANAGE ResourceAccessGrant.

    Ordinary Research Group membership does not itself delegate
    permission-management authority.
    """
    if not _is_authenticated(
        user
    ):
        return False

    if _is_admin(
        user
    ):
        return True

    if _is_owner(
        user,
        collection,
    ):
        return True

    if _is_group_coordinator(
        user,
        collection,
    ):
        return True

    return _has_explicit_access(
        user,
        collection,
        ResourceAccessGrant.AccessLevel.MANAGE,
    )


def visible_collections_for_user(
    user,
):
    """
    Return active Collections visible to a user.

    Lifecycle filtering is applied before permission evaluation so
    inactive Collections are not returned by normal internal lists
    or selectors.
    """
    from core.models import (
        Collection,
    )

    qs = (
        Collection.objects
        .filter(
            is_active=True,
        )
        .select_related(
            "owner",
            "research_group",
        )
    )

    if _is_admin(
        user
    ):
        return qs

    visible_ids = [
        collection.pk
        for collection in qs
        if can_view_collection(
            user,
            collection,
        )
    ]

    return Collection.objects.filter(
        pk__in=visible_ids,
        is_active=True,
    )
