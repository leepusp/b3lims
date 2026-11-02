"""Access policy for the experimental ELN interface."""

from django.conf import settings


ELN_EVALUATOR_GROUP = "b3_eln_evaluators"


def is_eln_experimental_enabled():
    return getattr(
        settings,
        "B3_ELN_EXPERIMENTAL_ENABLED",
        False,
    ) is True


def can_access_eln_experimental(user):
    if not is_eln_experimental_enabled():
        return False

    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    return user.groups.filter(
        name=ELN_EVALUATOR_GROUP,
    ).exists()
