from __future__ import annotations

from dataclasses import dataclass
import logging

from django.conf import settings

from core.services.resource_access import (
    has_explicit_resource_access,
)


logger = logging.getLogger(__name__)

SUPPORTED_LEVELS = {
    "view",
    "edit",
    "manage",
}


@dataclass(frozen=True)
class SampleAccessShadowObservation:
    required_level: str
    legacy_allowed: bool
    generic_allowed: bool | None
    equivalent: bool | None
    status: str


def sample_access_shadow_enabled():
    return bool(
        getattr(
            settings,
            "BIOBANK_SAMPLE_GRANT_SHADOW_MODE",
            False,
        )
    )


def _eligible_for_shadow(user, sample):
    return bool(
        user
        and getattr(
            user,
            "is_authenticated",
            False,
        )
        and getattr(
            sample,
            "pk",
            None,
        ) is not None
    )


def observe_sample_access_shadow(
    user,
    sample,
    *,
    required_level,
    legacy_allowed,
):
    """
    Compare generic explicit access without changing the legacy decision.

    Logs deliberately exclude usernames, object identifiers and field values.
    Evaluation failures are contained because shadow mode is non-authoritative.
    """
    if required_level not in SUPPORTED_LEVELS:
        raise ValueError(
            f"Unsupported shadow access level: {required_level}"
        )

    if not sample_access_shadow_enabled():
        return None

    if not _eligible_for_shadow(
        user,
        sample,
    ):
        return None

    legacy_allowed = bool(
        legacy_allowed
    )

    try:
        generic_allowed = (
            has_explicit_resource_access(
                user,
                sample,
                required_level=required_level,
            )
        )
    except Exception as error:
        logger.error(
            (
                "Sample access shadow evaluation failed: "
                "required_level=%s error_class=%s"
            ),
            required_level,
            type(error).__name__,
        )

        return SampleAccessShadowObservation(
            required_level=required_level,
            legacy_allowed=legacy_allowed,
            generic_allowed=None,
            equivalent=None,
            status="evaluation_error",
        )

    generic_allowed = bool(
        generic_allowed
    )

    equivalent = (
        legacy_allowed
        == generic_allowed
    )

    if equivalent:
        status = "match"
    elif legacy_allowed:
        status = (
            "legacy_allows_generic_denies"
        )
    else:
        status = (
            "generic_allows_legacy_denies"
        )

    observation = SampleAccessShadowObservation(
        required_level=required_level,
        legacy_allowed=legacy_allowed,
        generic_allowed=generic_allowed,
        equivalent=equivalent,
        status=status,
    )

    if not equivalent:
        logger.warning(
            (
                "Sample access shadow mismatch: "
                "required_level=%s legacy_allowed=%s "
                "generic_allowed=%s status=%s"
            ),
            required_level,
            legacy_allowed,
            generic_allowed,
            status,
        )

    return observation
