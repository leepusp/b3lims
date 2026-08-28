from collections import Counter

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone

from core.models import Collection, ResourceAccessGrant
from core.permissions.collections import (
    can_manage_collection_permissions,
    visible_collections_for_user,
)


ACCESS_RANK = {
    ResourceAccessGrant.AccessLevel.VIEW: 1,
    ResourceAccessGrant.AccessLevel.EDIT: 2,
    ResourceAccessGrant.AccessLevel.MANAGE: 3,
}


def _collection_content_type():
    """
    Return the only ResourceAccessGrant target type exposed by
    the Profile access surface.

    Profile Access v1.1 deliberately does not dereference arbitrary
    GenericForeignKey targets.
    """
    return ContentType.objects.get_for_model(
        Collection,
        for_concrete_model=False,
    )


def _active_collection_grants():
    """
    Return active explicit grants whose target type is Collection.

    The active-state semantics mirror ResourceAccessGrant:
    non-revoked and either unexpired or without expiration.
    """
    now = timezone.now()

    return (
        ResourceAccessGrant.objects
        .filter(
            content_type=_collection_content_type(),
            revoked_at__isnull=True,
        )
        .filter(
            Q(expires_at__isnull=True)
            | Q(expires_at__gt=now)
        )
        .select_related(
            "user",
            "research_group",
            "granted_by",
        )
    )


def _grant_collection_id(
    grant,
):
    """
    Convert the allowlisted Collection object identifier safely.

    Malformed historical GenericForeignKey identifiers are ignored
    rather than dereferenced.
    """
    raw = str(
        grant.object_id
        or ""
    ).strip()

    if not raw:
        return None

    try:
        collection_id = int(
            raw
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    if collection_id <= 0:
        return None

    return collection_id


def received_collection_access_for_user(
    user,
):
    """
    Build active Collection access paths received by one user.

    One row represents one applicable explicit grant. A Collection can
    therefore appear more than once when the user has multiple active
    access paths, such as one direct grant and one ResearchGroup grant.
    """
    if (
        not user
        or not user.is_authenticated
    ):
        return []

    grants = list(
        _active_collection_grants()
        .filter(
            Q(user=user)
            | Q(
                research_group__coordinator=user
            )
            | Q(
                research_group__members=user
            )
        )
        .distinct()
        .order_by(
            "id"
        )
    )

    collection_ids = {
        collection_id
        for collection_id in (
            _grant_collection_id(
                grant
            )
            for grant in grants
        )
        if collection_id is not None
    }

    collections_by_id = (
        Collection.objects
        .filter(
            pk__in=collection_ids,
            is_active=True,
        )
        .select_related(
            "owner",
            "research_group",
        )
        .in_bulk()
    )

    entries = []

    for grant in grants:
        collection_id = (
            _grant_collection_id(
                grant
            )
        )

        collection = (
            collections_by_id
            .get(
                collection_id
            )
        )

        if collection is None:
            continue

        if grant.user_id == user.pk:
            source_type = "Direct"
            source_label = "Direct grant"

        else:
            source_type = "Research Group"
            source_label = (
                grant.research_group.name
                if grant.research_group_id
                else "Research Group"
            )

        entries.append(
            {
                "collection": collection,
                "grant": grant,
                "access_level":
                    grant.access_level,
                "access_label":
                    grant.get_access_level_display(),
                "source_type":
                    source_type,
                "source_label":
                    source_label,
                "expires_at":
                    grant.expires_at,
                "grantor":
                    grant.granted_by,
            }
        )

    entries.sort(
        key=lambda entry: (
            entry[
                "collection"
            ].name.casefold(),
            -ACCESS_RANK.get(
                entry[
                    "access_level"
                ],
                0,
            ),
            entry[
                "source_type"
            ].casefold(),
            entry[
                "grant"
            ].pk,
        )
    )

    return entries


def managed_collection_access_for_user(
    user,
):
    """
    Return active Collections whose sharing permissions the user may
    manage under the canonical Collection authorization policy.

    This intentionally does not use ResourceAccessGrant.granted_by as
    a management criterion.
    """
    if (
        not user
        or not user.is_authenticated
    ):
        return []

    visible_collections = list(
        visible_collections_for_user(
            user
        )
        .select_related(
            "owner",
            "research_group",
        )
        .order_by(
            "name",
            "pk",
        )
    )

    managed_collections = [
        collection
        for collection
        in visible_collections
        if can_manage_collection_permissions(
            user,
            collection,
        )
    ]

    if not managed_collections:
        return []

    managed_ids = {
        collection.pk
        for collection
        in managed_collections
    }

    grant_counts = Counter()

    for grant in (
        _active_collection_grants()
        .filter(
            object_id__in=[
                str(
                    collection_id
                )
                for collection_id
                in managed_ids
            ]
        )
    ):
        collection_id = (
            _grant_collection_id(
                grant
            )
        )

        if (
            collection_id
            in managed_ids
        ):
            grant_counts[
                collection_id
            ] += 1

    return [
        {
            "collection": collection,
            "active_grant_count":
                grant_counts.get(
                    collection.pk,
                    0,
                ),
        }
        for collection
        in managed_collections
    ]


def build_profile_collection_access_context(
    user,
):
    """
    Build the read-only Collection sharing context exposed in Profile.
    """
    return {
        "profile_access_received":
            received_collection_access_for_user(
                user
            ),
        "profile_access_managed":
            managed_collection_access_for_user(
                user
            ),
    }
