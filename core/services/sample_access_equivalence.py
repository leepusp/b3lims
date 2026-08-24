from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from core.models import ResourceAccessGrant
from core.models.samples.access import SampleAccessGrant
from core.services.resource_access import (
    resource_grants_for_user,
)


LEGACY_ACCESS_RANK = {
    None: 0,
    SampleAccessGrant.ACCESS_VIEW: 1,
    SampleAccessGrant.ACCESS_EDIT: 2,
}

GENERIC_ACCESS_RANK = {
    None: 0,
    ResourceAccessGrant.AccessLevel.VIEW: 1,
    ResourceAccessGrant.AccessLevel.EDIT: 2,
    ResourceAccessGrant.AccessLevel.MANAGE: 3,
}


@dataclass(frozen=True)
class SampleAccessEquivalence:
    """
    Side-by-side comparison without changing active Sample authorization.
    """

    legacy_level: str | None
    generic_level: str | None
    legacy_view: bool
    legacy_edit: bool
    generic_view: bool
    generic_edit: bool
    generic_manage: bool
    applicable_group_grant: bool
    behavior_equivalent: bool
    migration_equivalent: bool
    mismatch_reasons: tuple[str, ...]


def _is_authenticated(user):
    return bool(
        user
        and getattr(
            user,
            "is_authenticated",
            False,
        )
    )


def _highest_level(
    grants,
    ranks,
):
    level = None
    rank = 0

    for grant in grants:
        candidate = grant.access_level
        candidate_rank = ranks.get(
            candidate
        )

        if candidate_rank is None:
            raise ValueError(
                f"Unsupported access level: {candidate}"
            )

        if candidate_rank > rank:
            level = candidate
            rank = candidate_rank

    return level


def legacy_sample_access_level(
    user,
    sample,
):
    """
    Return the active direct SampleAccessGrant level for one user.
    """
    if not _is_authenticated(user):
        return None

    now = timezone.now()

    grants = (
        SampleAccessGrant.objects
        .filter(
            sample=sample,
            user=user,
        )
        .filter(
            Q(
                expires_at__isnull=True
            )
            | Q(
                expires_at__gt=now
            )
        )
        .only(
            "access_level"
        )
    )

    return _highest_level(
        grants,
        LEGACY_ACCESS_RANK,
    )


def generic_sample_access_level(
    user,
    sample,
):
    """
    Return the strongest active generic user or group grant level.
    """
    if not _is_authenticated(user):
        return None

    grants = (
        resource_grants_for_user(
            user,
            sample,
        )
        .only(
            "access_level"
        )
    )

    return _highest_level(
        grants,
        GENERIC_ACCESS_RANK,
    )


def _has_applicable_generic_group_grant(
    user,
    sample,
):
    if not _is_authenticated(user):
        return False

    return (
        resource_grants_for_user(
            user,
            sample,
        )
        .filter(
            research_group__isnull=False,
        )
        .exists()
    )


def evaluate_sample_access_equivalence(
    user,
    sample,
):
    """
    Compare legacy and generic explicit Sample access without authorizing it.

    Ownership, administrator, Research Group, Collection and public access
    remain outside this comparison and continue to use the existing policy.
    """
    legacy_level = (
        legacy_sample_access_level(
            user,
            sample,
        )
    )

    generic_level = (
        generic_sample_access_level(
            user,
            sample,
        )
    )

    legacy_rank = (
        LEGACY_ACCESS_RANK[
            legacy_level
        ]
    )

    generic_rank = (
        GENERIC_ACCESS_RANK[
            generic_level
        ]
    )

    legacy_view = (
        legacy_rank >= 1
    )
    legacy_edit = (
        legacy_rank >= 2
    )

    generic_view = (
        generic_rank >= 1
    )
    generic_edit = (
        generic_rank >= 2
    )
    generic_manage = (
        generic_rank >= 3
    )

    applicable_group_grant = (
        _has_applicable_generic_group_grant(
            user,
            sample,
        )
    )

    reasons = []

    if legacy_view != generic_view:
        reasons.append(
            "view_behavior_mismatch"
        )

    if legacy_edit != generic_edit:
        reasons.append(
            "edit_behavior_mismatch"
        )

    behavior_equivalent = (
        not reasons
    )

    if generic_manage:
        reasons.append(
            "generic_manage_not_representable"
        )

    if applicable_group_grant:
        reasons.append(
            "generic_group_principal_not_representable"
        )

    migration_equivalent = (
        not reasons
    )

    return SampleAccessEquivalence(
        legacy_level=legacy_level,
        generic_level=generic_level,
        legacy_view=legacy_view,
        legacy_edit=legacy_edit,
        generic_view=generic_view,
        generic_edit=generic_edit,
        generic_manage=generic_manage,
        applicable_group_grant=(
            applicable_group_grant
        ),
        behavior_equivalent=(
            behavior_equivalent
        ),
        migration_equivalent=(
            migration_equivalent
        ),
        mismatch_reasons=tuple(
            reasons
        ),
    )
