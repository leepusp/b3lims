from django.db.models import Q

from core.models import Shipment


def _field_exists(model, field_name):
    return any(field.name == field_name for field in model._meta.get_fields())


def _research_group_ids_for_user(user):
    """
    Resolve ResearchGroup memberships without assuming a single schema.

    The project has a ResearchGroup model, but deployments may represent
    membership through different fields. This helper supports common patterns
    and also matches Django auth group names to ResearchGroup names.
    """
    try:
        from core.models import ResearchGroup
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


def visible_shipments_for_user(user):
    """
    Return shipments visible to the current internal user.

    Staff/superusers can audit all shipments. Regular users only see shipments
    explicitly assigned to them or linked to samples owned by them or belonging
    to one of their research groups.

    Public sample visibility is intentionally not enough to expose transport
    records, because shipment data includes custody, documentation and routing.
    """
    base_qs = Shipment.objects.all()

    if not user or not user.is_authenticated:
        return base_qs.none()

    if user.is_superuser or user.is_staff:
        return base_qs

    q = (
        Q(requested_by=user)
        | Q(reviewed_by=user)
        | Q(authorized_by=user)
        | Q(items__sample__owner=user)
    )

    research_group_ids = _research_group_ids_for_user(user)
    if research_group_ids:
        q |= Q(items__sample__research_group_id__in=research_group_ids)

    return base_qs.filter(q).distinct()
