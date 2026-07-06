from django.apps import apps
from django.db.models import Q


def _field_exists(model, field_name):
    return any(field.name == field_name for field in model._meta.get_fields())


def research_group_ids_for_user(user):
    """
    Resolve ResearchGroup membership for operational dashboards.

    Supports common ResearchGroup schemas and maps Django auth group names to
    ResearchGroup.name when explicit membership tables are not available.
    """
    if not user or not user.is_authenticated:
        return []

    try:
        ResearchGroup = apps.get_model("core", "ResearchGroup")
    except Exception:
        return []

    group_ids = set()

    many_to_many_candidates = [
        "members",
        "users",
        "researchers",
    ]

    direct_user_candidates = [
        "owner",
        "created_by",
        "principal_investigator",
        "pi",
        "coordinator",
    ]

    for field_name in many_to_many_candidates:
        if _field_exists(ResearchGroup, field_name):
            try:
                group_ids.update(
                    ResearchGroup.objects
                    .filter(**{field_name: user})
                    .values_list("id", flat=True)
                )
            except Exception:
                pass

    for field_name in direct_user_candidates:
        if _field_exists(ResearchGroup, field_name):
            try:
                group_ids.update(
                    ResearchGroup.objects
                    .filter(**{field_name: user})
                    .values_list("id", flat=True)
                )
            except Exception:
                pass

    try:
        auth_group_names = list(user.groups.values_list("name", flat=True))
        if auth_group_names and _field_exists(ResearchGroup, "name"):
            group_ids.update(
                ResearchGroup.objects
                .filter(name__in=auth_group_names)
                .values_list("id", flat=True)
            )
    except Exception:
        pass

    return list(group_ids)


def visible_workspace_samples_for_user(user):
    """
    Samples visible in operational workspace widgets.

    Staff/superusers can audit all active samples. Regular users only see active
    samples owned by them or assigned to their research groups. Public visibility
    alone is not used for operational activity/calendar widgets.
    """
    Sample = apps.get_model("core", "Sample")
    qs = Sample.objects.filter(is_active=True)

    if not user or not user.is_authenticated:
        return qs.none()

    if user.is_staff or user.is_superuser:
        return qs

    q = Q(owner=user)

    group_ids = research_group_ids_for_user(user)
    if group_ids:
        q |= Q(research_group_id__in=group_ids)

    return qs.filter(q).distinct()


def visible_workspace_collections_for_user(user):
    """
    Collections visible in operational workspace widgets.
    """
    Collection = apps.get_model("core", "Collection")
    qs = Collection.objects.filter(is_active=True)

    if not user or not user.is_authenticated:
        return qs.none()

    if user.is_staff or user.is_superuser:
        return qs

    q = Q(owner=user)

    group_ids = research_group_ids_for_user(user)
    if group_ids:
        q |= Q(research_group_id__in=group_ids)

    return qs.filter(q).distinct()


def visible_workspace_events_for_user(user):
    """
    Calendar/activity events visible to the current user.
    """
    Event = apps.get_model("core", "Event")
    sample_ids = visible_workspace_samples_for_user(user).values_list("id", flat=True)
    return Event.objects.filter(sample_id__in=sample_ids)
