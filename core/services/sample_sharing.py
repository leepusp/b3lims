from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.db import transaction

from core.models.samples.access import (
    SampleAccessGrant,
)
from core.permissions.samples import (
    can_manage_sample_sharing,
)


User = get_user_model()


@dataclass(frozen=True)
class BulkGrantResult:
    created: int
    updated: int
    skipped_owner: int


def _validate_target_user(user):
    if user is None or not getattr(
        user,
        "pk",
        None,
    ):
        raise ValidationError(
            "A valid target user is required."
        )

    if not user.is_active:
        raise ValidationError(
            "Sample access can be granted only to an active user."
        )


def _validate_access_level(access_level):
    valid = {
        choice[0]
        for choice in SampleAccessGrant.ACCESS_LEVELS
    }

    if access_level not in valid:
        raise ValidationError(
            "Invalid Sample access level."
        )


@transaction.atomic
def grant_sample_access(
    *,
    sample,
    user,
    access_level,
    granted_by,
    expires_at=None,
):
    """
    Create or update direct access for one Sample.

    No ownership, Research Group, Collection, Biobank or filesystem
    state is changed by this operation.
    """
    if not can_manage_sample_sharing(
        granted_by,
        sample,
    ):
        raise PermissionDenied(
            "You do not have permission to manage Sample sharing."
        )

    _validate_target_user(
        user
    )

    _validate_access_level(
        access_level
    )

    if sample.owner_id == user.pk:
        raise ValidationError(
            "The Sample owner already has full access and cannot "
            "receive a direct access grant."
        )

    grant, created = (
        SampleAccessGrant.objects.update_or_create(
            sample=sample,
            user=user,
            defaults={
                "access_level": access_level,
                "granted_by": granted_by,
                "expires_at": expires_at,
            },
        )
    )

    return grant, created


@transaction.atomic
def revoke_sample_access(
    *,
    sample,
    user,
    revoked_by,
):
    if not can_manage_sample_sharing(
        revoked_by,
        sample,
    ):
        raise PermissionDenied(
            "You do not have permission to manage Sample sharing."
        )

    deleted, _ = (
        SampleAccessGrant.objects.filter(
            sample=sample,
            user=user,
        ).delete()
    )

    return deleted


@transaction.atomic
def bulk_grant_sample_access(
    *,
    samples,
    user,
    access_level,
    granted_by,
    expires_at=None,
):
    """
    Grant direct access to several Samples atomically.

    Samples already owned by the target user are skipped because
    ownership already provides full access.
    """
    _validate_target_user(
        user
    )

    _validate_access_level(
        access_level
    )

    samples = list(
        samples
    )

    for sample in samples:
        if not can_manage_sample_sharing(
            granted_by,
            sample,
        ):
            raise PermissionDenied(
                "You do not have permission to manage sharing for "
                f"Sample {sample.sample_id}."
            )

    created = 0
    updated = 0
    skipped_owner = 0

    for sample in samples:
        if sample.owner_id == user.pk:
            skipped_owner += 1
            continue

        _, was_created = (
            SampleAccessGrant.objects.update_or_create(
                sample=sample,
                user=user,
                defaults={
                    "access_level": access_level,
                    "granted_by": granted_by,
                    "expires_at": expires_at,
                },
            )
        )

        if was_created:
            created += 1
        else:
            updated += 1

    return BulkGrantResult(
        created=created,
        updated=updated,
        skipped_owner=skipped_owner,
    )
