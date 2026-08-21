from django.contrib.auth.models import User
from django.db.models import Q


def _is_authenticated(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
    )


def _is_admin(user):
    return bool(
        _is_authenticated(user)
        and (
            getattr(user, "is_superuser", False)
            or getattr(user, "is_staff", False)
        )
    )


def _is_owner(user, sample):
    return bool(
        _is_authenticated(user)
        and getattr(sample, "owner_id", None) == user.id
    )


def _has_group_access(user, obj):
    """
    Return whether the user is a member or coordinator of the
    object's associated Research Group.
    """
    if not _is_authenticated(user):
        return False

    group = getattr(obj, "research_group", None)

    if not group:
        return False

    return bool(
        group.coordinator_id == user.id
        or group.members.filter(pk=user.pk).exists()
    )


def _has_collection_group_access(user, sample):
    if not _is_authenticated(user):
        return False

    for collection in sample.collections.all():
        if _has_group_access(user, collection):
            return True

    return False


def is_sample_publicly_accessible(sample):
    """
    Return whether a Sample may be exposed without internal authorization.

    Embargo and lifecycle state override the public flag.
    """
    return bool(
        getattr(sample, "is_active", False)
        and getattr(sample, "is_public", False)
        and not getattr(sample, "is_embargoed", False)
        and getattr(
            sample,
            "deletion_requested_at",
            None,
        ) is None
    )


def can_view_sample(user, sample):
    """
    Sample viewing policy.

    Internal authorization takes precedence over lifecycle state so owners,
    administrators and authorized groups can inspect deactivated or trashed
    records. Public access is permitted only for active, non-embargoed Samples.
    """
    if _is_admin(user):
        return True

    if _is_owner(user, sample):
        return True

    if _has_group_access(user, sample):
        return True

    if _has_collection_group_access(user, sample):
        return True

    return is_sample_publicly_accessible(sample)


def can_edit_sample(user, sample):
    """
    Metadata editing policy.

    A Sample in Trash is immutable through the normal Edit workflow.
    Restoration is handled by the dedicated lifecycle action.
    """
    if getattr(
        sample,
        "deletion_requested_at",
        None,
    ) is not None:
        return False

    if _is_admin(user):
        return True

    if _is_owner(user, sample):
        return True

    if _has_group_access(user, sample):
        return True

    if _has_collection_group_access(user, sample):
        return True

    return False


def can_delete_sample(user, sample):
    """
    Return whether the user may move a Sample to Trash or purge it.

    Ordinary Research Group members may edit Samples but may not delete them.
    """
    if _is_admin(user):
        return True

    if _is_owner(user, sample):
        return True

    group = getattr(sample, "research_group", None)

    if (
        _is_authenticated(user)
        and group
        and group.coordinator_id == user.id
    ):
        return True

    if _is_authenticated(user):
        for collection in sample.collections.all():
            collection_group = getattr(
                collection,
                "research_group",
                None,
            )

            if (
                collection_group
                and collection_group.coordinator_id
                == user.id
            ):
                return True

    return False


def visible_samples_for_user(user):
    """
    Return active, non-trash Samples visible to a user.
    """
    from core.models.samples.sample import Sample

    qs = (
        Sample.objects
        .filter(
            is_active=True,
            deletion_requested_at__isnull=True,
        )
        .select_related(
            "biobank",
            "owner",
            "research_group",
        )
        .prefetch_related(
            "collections",
            "collections__research_group",
        )
    )

    if _is_admin(user):
        return qs

    visible_ids = [
        sample.pk
        for sample in qs
        if can_view_sample(
            user,
            sample,
        )
    ]

    return Sample.objects.filter(
        pk__in=visible_ids,
        is_active=True,
        deletion_requested_at__isnull=True,
    )


def sample_research_groups_for_user(user):
    """
    Research Groups that may be assigned to a Sample by this user.
    """
    from core.models.research_groups.model import ResearchGroup

    qs = ResearchGroup.objects.all().order_by("name")

    if not _is_authenticated(user):
        return qs.none()

    if _is_admin(user):
        return qs

    return (
        qs.filter(
            Q(coordinator=user)
            | Q(members=user)
        )
        .distinct()
    )


def assignable_sample_owners_for_user(user):
    """
    Users that may be selected as Sample owner.

    Non-administrators may assign Samples only to active users sharing one
    of their Research Groups, plus themselves.
    """
    if not _is_authenticated(user):
        return User.objects.none()

    qs = User.objects.filter(
        is_active=True,
    ).order_by(
        "username",
    )

    if _is_admin(user):
        return qs

    group_ids = list(
        sample_research_groups_for_user(
            user
        ).values_list(
            "pk",
            flat=True,
        )
    )

    return (
        qs.filter(
            Q(pk=user.pk)
            | Q(
                research_groups__pk__in=group_ids
            )
            | Q(
                coordinated_research_groups__pk__in=group_ids
            )
        )
        .distinct()
    )


def editable_sample_collections_for_user(user):
    """
    Active Collections to which the user may add a Sample.
    """
    from core.models.collections.collection import Collection
    from core.permissions.collections import can_edit_collection

    qs = (
        Collection.objects
        .filter(
            is_active=True,
        )
        .select_related(
            "owner",
            "research_group",
        )
        .order_by(
            "name",
        )
    )

    if not _is_authenticated(user):
        return qs.none()

    if _is_admin(user):
        return qs

    editable_ids = [
        collection.pk
        for collection in qs
        if can_edit_collection(
            user,
            collection,
        )
    ]

    return qs.filter(
        pk__in=editable_ids,
    )
