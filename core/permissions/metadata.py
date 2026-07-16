from django.core.exceptions import PermissionDenied


def can_manage_metadata_vocabulary(user):
    """Return whether a user may manage global tags and keywords."""
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.is_superuser
    )


def require_metadata_manager(user):
    """Require global metadata vocabulary administration permission."""
    if not can_manage_metadata_vocabulary(user):
        raise PermissionDenied
