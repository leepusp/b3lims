"""Authorization policy for shared physical storage infrastructure."""

from django.conf import settings


def can_manage_storage_infrastructure(user):
    """
    Return whether a user may mutate the shared StorageLocation tree.

    Standalone installations are currently personal/local-first, so an
    authenticated local user may manage the physical hierarchy.

    Institutional/B3 installations keep infrastructure mutation limited
    to Django staff/superusers until StorageLocation receives explicit
    organizational ownership/scoping.
    """

    if (
        user is None
        or not getattr(
            user,
            "is_authenticated",
            False,
        )
    ):
        return False

    if (
        getattr(
            settings,
            "BIOBANK_RUNTIME_PROFILE",
            None,
        )
        == "standalone"
    ):
        return True

    from core.permissions.storage_workspaces_v8 import (
        is_storage_global_admin,
    )

    return is_storage_global_admin(user)
