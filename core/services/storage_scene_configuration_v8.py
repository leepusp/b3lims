"""Manage private spatial views without modifying physical inventory."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.models.samples.storage import StorageSceneConfiguration
from core.services.storage_scene_projection_v8 import (
    SCENE_PROFILES,
    build_storage_scene_projection,
)


def _require_user(actor):
    if (
        actor is None
        or not getattr(actor, "is_authenticated", False)
        or not getattr(actor, "is_active", False)
    ):
        raise PermissionDenied("An active user is required.")


def _validate_name(name):
    name = str(name or "").strip()

    if not name or len(name) > 120:
        raise ValidationError(
            "Scene name must contain 1 to 120 characters."
        )

    if any(ord(char) < 32 for char in name):
        raise ValidationError("Invalid scene name.")

    return name


def _validate_overrides(value):
    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValidationError(
            "Profile overrides must be a mapping."
        )

    result = {}

    for raw_id, profile in value.items():
        if isinstance(raw_id, bool):
            raise ValidationError("Invalid location ID.")

        try:
            pk = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Invalid location ID."
            ) from exc

        if pk < 1 or profile not in SCENE_PROFILES:
            raise ValidationError(
                "Invalid location or geometry profile."
            )

        key = str(pk)

        if key in result:
            raise ValidationError(
                "Duplicate geometry override."
            )

        result[key] = profile

    return result



def _require_scene_location_access(*, actor, projection):
    """
    A personal scene may only project physical locations
    visible to its owner, including every descendant.
    """
    from core.permissions.storage_workspaces_v8 import (
        visible_storage_locations_for_user,
    )

    projected_ids = {
        int(node["id"])
        for node in projection["nodes"]
    }

    permitted_ids = set(
        visible_storage_locations_for_user(actor)
        .filter(pk__in=projected_ids)
        .values_list("pk", flat=True)
    )

    if not projected_ids or projected_ids != permitted_ids:
        raise PermissionDenied(
            "The scene contains storage locations "
            "outside your authorized workspace."
        )


@transaction.atomic
def save_storage_scene_configuration(
    *,
    actor,
    name,
    root_id,
    root_profile="auto",
    profile_overrides=None,
    configuration_id=None,
):
    """Create or update one user-owned visualization."""
    _require_user(actor)

    name = _validate_name(name)

    if root_profile not in SCENE_PROFILES | {"auto"}:
        raise ValidationError("Invalid root geometry profile.")

    overrides = _validate_overrides(profile_overrides)

    try:
        root_pk = int(root_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid root location.") from exc

    if root_pk <= 0:
        raise ValidationError("Invalid root location.")

    if str(root_pk) in overrides:
        raise ValidationError(
            "Configure root geometry with root_profile."
        )

    resolved = dict(overrides)

    if root_profile != "auto":
        resolved[str(root_pk)] = root_profile

    projection = build_storage_scene_projection(
        root_id=root_pk,
        profile_overrides=resolved,
    )

    _require_scene_location_access(
        actor=actor,
        projection=projection,
    )

    valid_ids = {
        node["id"] for node in projection["nodes"]
    }

    for raw_id in overrides:
        if int(raw_id) not in valid_ids:
            raise ValidationError(
                "A geometry override is outside the selected scene "
                "or belongs to an inactive location."
            )

    qs = StorageSceneConfiguration.objects.filter(
        owner=actor,
    )

    if configuration_id is None:
        configuration = StorageSceneConfiguration(
            owner=actor,
        )
    else:
        configuration = (
            qs.select_for_update()
            .filter(pk=configuration_id)
            .first()
        )

        if configuration is None:
            raise PermissionDenied(
                "Scene configuration is not accessible."
            )

    if qs.filter(name=name).exclude(
        pk=configuration.pk
    ).exists():
        raise ValidationError(
            "You already have a scene with this name."
        )

    configuration.name = name
    configuration.root_location_id = root_pk
    configuration.root_profile = root_profile
    configuration.profile_overrides = overrides

    configuration.full_clean()
    configuration.save()

    return configuration


def get_storage_scene_projection(*, actor, configuration_id):
    """Return only a scene owned by the requesting user."""
    _require_user(actor)

    configuration = (
        StorageSceneConfiguration.objects
        .filter(
            pk=configuration_id,
            owner=actor,
        )
        .first()
    )

    if configuration is None:
        raise PermissionDenied(
            "Scene configuration is not accessible."
        )

    overrides = dict(configuration.profile_overrides)

    if configuration.root_profile != "auto":
        overrides[str(configuration.root_location_id)] = (
            configuration.root_profile
        )

    projection = build_storage_scene_projection(
        root_id=configuration.root_location_id,
        profile_overrides=overrides,
    )

    _require_scene_location_access(
        actor=actor,
        projection=projection,
    )

    return projection
