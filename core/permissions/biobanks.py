from django.db.models import Q

from core.models.biobanks.biobank import Biobank
from core.models.biobanks.biobank_user_role import BiobankUserRole


EDIT_ROLES = {
    BiobankUserRole.OWNER,
    BiobankUserRole.MANAGER,
    BiobankUserRole.EDITOR,
}

VIEW_ROLES = {
    BiobankUserRole.OWNER,
    BiobankUserRole.MANAGER,
    BiobankUserRole.EDITOR,
    BiobankUserRole.VIEWER,
    BiobankUserRole.MEMBER,
}


def user_research_group_ids(user):
    if not user or not user.is_authenticated:
        return []

    return list(user.research_groups.values_list("id", flat=True))


def user_is_biobank_owner(user, biobank):
    return bool(
        user
        and user.is_authenticated
        and getattr(biobank, "owner_id", None) == user.id
    )


def user_has_biobank_role(user, biobank, roles=None):
    if not user or not user.is_authenticated:
        return False

    qs = BiobankUserRole.objects.filter(user=user, biobank=biobank)

    if roles is not None:
        qs = qs.filter(role__in=roles)

    return qs.exists()


def user_is_biobank_group_member(user, biobank):
    if not user or not user.is_authenticated:
        return False

    if not getattr(biobank, "research_group_id", None):
        return False

    return user.research_groups.filter(id=biobank.research_group_id).exists()


def can_view_biobank(user, biobank):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if not biobank.is_active:
        return False

    if user_is_biobank_owner(user, biobank):
        return True

    if user_is_biobank_group_member(user, biobank):
        return True

    if user_has_biobank_role(user, biobank, VIEW_ROLES):
        return True

    if biobank.is_public:
        return True

    return False


def can_edit_biobank(user, biobank):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if not biobank.is_active:
        return False

    if user_is_biobank_owner(user, biobank):
        return True

    if user_has_biobank_role(user, biobank, EDIT_ROLES):
        return True

    return False


def can_manage_biobank_permissions(user, biobank):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if user_is_biobank_owner(user, biobank):
        return True

    if user_has_biobank_role(
        user,
        biobank,
        {BiobankUserRole.OWNER, BiobankUserRole.MANAGER},
    ):
        return True

    return False


def visible_biobanks_for_user(user):
    qs = Biobank.objects.filter(is_active=True).select_related(
        "owner",
        "research_group",
    )

    if not user or not user.is_authenticated:
        return qs.none()

    if user.is_superuser:
        return qs

    group_ids = user_research_group_ids(user)

    return qs.filter(
        Q(owner=user)
        | Q(research_group_id__in=group_ids)
        | Q(user_roles__user=user, user_roles__role__in=VIEW_ROLES)
        | Q(is_public=True)
    ).distinct()


def editable_biobanks_for_user(user):
    qs = Biobank.objects.filter(is_active=True).select_related(
        "owner",
        "research_group",
    )

    if not user or not user.is_authenticated:
        return qs.none()

    if user.is_superuser:
        return qs

    return qs.filter(
        Q(owner=user)
        | Q(user_roles__user=user, user_roles__role__in=EDIT_ROLES)
    ).distinct()
