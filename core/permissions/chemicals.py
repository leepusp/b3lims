def _has_group_access(user, chemical):
    group = getattr(chemical, "research_group", None)

    if not group:
        return False

    if getattr(group, "coordinator_id", None) == getattr(user, "id", None):
        return True

    return group.members.filter(id=user.id).exists()


def can_view_chemical(user, chemical):
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    if getattr(chemical, "created_by_id", None) == getattr(user, "id", None):
        return True

    if getattr(chemical, "is_public", False):
        return True

    return _has_group_access(user, chemical)


def can_edit_chemical(user, chemical):
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    if getattr(chemical, "created_by_id", None) == getattr(user, "id", None):
        return True

    return _has_group_access(user, chemical)


def can_delete_chemical(user, chemical):
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    if getattr(chemical, "created_by_id", None) == getattr(user, "id", None):
        return True

    group = getattr(chemical, "research_group", None)
    return bool(group and getattr(group, "coordinator_id", None) == getattr(user, "id", None))


def visible_chemicals_for_user(user):
    from core.models.chemicals.chemical import Chemical

    qs = Chemical.objects.all().select_related(
        "created_by",
        "research_group",
    )

    if getattr(user, "is_superuser", False):
        return qs

    visible_ids = [
        chemical.pk
        for chemical in qs
        if can_view_chemical(user, chemical)
    ]

    return Chemical.objects.filter(pk__in=visible_ids).select_related(
        "created_by",
        "research_group",
    )
