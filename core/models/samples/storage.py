from django.conf import settings
from django.db import models



class StorageWorkspace(models.Model):
    """Ownership boundary for physical storage inventory."""

    SCOPE_CHOICES = [
        ("personal", "Personal"),
        ("group", "Research Group"),
    ]

    name = models.CharField(max_length=120)

    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default="personal",
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_storage_workspaces",
    )

    research_group = models.ForeignKey(
        "core.ResearchGroup",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="storage_workspaces",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="unique_storage_ws_owner_name_v8",
            ),
            models.UniqueConstraint(
                fields=["research_group", "name"],
                condition=models.Q(scope="group"),
                name="unique_storage_ws_group_name_v8",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        scope="personal",
                        research_group__isnull=True,
                    )
                    | models.Q(
                        scope="group",
                        research_group__isnull=False,
                    )
                ),
                name="valid_storage_ws_scope_v8",
            ),
        ]

    def __str__(self):
        return self.name


class StorageLocation(models.Model):
    LOCATION_TYPE_CHOICES = [
        ("room", "Room"),
        ("freezer", "Freezer"),
        ("shelf", "Shelf"),
        ("rack", "Rack"),
        ("box", "Box"),
        ("position", "Position"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=255)

    workspace = models.ForeignKey(
        StorageWorkspace,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="locations",
        help_text=(
            "Null means legacy unscoped inventory; "
            "global administrator review required."
        ),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    location_type = models.CharField(
        max_length=50,
        choices=LOCATION_TYPE_CHOICES,
        default="other",
        blank=True,
    )
    rank = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["parent_id", "rank", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "name"],
                name="unique_storage_location_name_per_parent",
            )
        ]

    def __str__(self):
        return self.full_path

    @property
    def full_path_parts(self):
        parts = []
        node = self

        while node is not None:
            parts.append(node.name)
            node = node.parent

        return list(reversed(parts))

    @property
    def full_path(self):
        return " > ".join(self.full_path_parts)


class SampleStorageAssignment(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("moved", "Moved"),
        ("depleted", "Depleted"),
    ]

    sample = models.ForeignKey(
        "core.Sample",
        on_delete=models.CASCADE,
        related_name="storage_assignments",
    )
    location = models.ForeignKey(
        StorageLocation,
        on_delete=models.PROTECT,
        related_name="sample_assignments",
    )

    rank = models.PositiveIntegerField(default=1)
    is_primary = models.BooleanField(default=False)

    position = models.CharField(max_length=100, blank=True)
    container_type = models.CharField(max_length=100, blank=True)
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
    )
    quantity_unit = models.CharField(max_length=50, blank=True)

    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default="active",
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sample", "rank", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["sample", "rank"],
                name="unique_sample_storage_assignment_rank",
            ),
            models.UniqueConstraint(
                models.functions.Lower("position"),
                "location",
                condition=(
                    models.Q(status="active")
                    & ~models.Q(position="")
                ),
                name="unique_active_storage_slot_v8",
            ),
        ]

    def __str__(self):
        return f"{self.sample} → {self.location.full_path}"

    @property
    def full_path(self):
        return self.location.full_path


class StorageMovement(models.Model):
    """One auditable physical storage operation."""

    MOVEMENT_TYPES = [
        ("registration", "Initial Physical Registration"),
        ("sample", "Individual Sample"),
        ("sample_bulk", "Selected Samples"),
        ("container", "Storage Container"),
    ]

    movement_type = models.CharField(
        max_length=30,
        choices=MOVEMENT_TYPES,
    )

    moved_location = models.ForeignKey(
        StorageLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movement_history",
    )

    origin_location = models.ForeignKey(
        StorageLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements_from",
    )

    destination_location = models.ForeignKey(
        StorageLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements_to",
    )

    origin_path = models.TextField(blank=True)
    destination_path = models.TextField(blank=True)

    affected_location_count = models.PositiveIntegerField(
        default=0
    )
    affected_sample_count = models.PositiveIntegerField(
        default=0
    )
    affected_assignment_count = models.PositiveIntegerField(
        default=0
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="storage_movements",
    )

    actor_label = models.CharField(
        max_length=255,
        blank=True,
    )

    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]


class StorageMovementItem(models.Model):
    """Historical snapshot of an affected Sample assignment."""

    movement = models.ForeignKey(
        StorageMovement,
        on_delete=models.CASCADE,
        related_name="items",
    )

    sample = models.ForeignKey(
        "core.Sample",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="storage_movement_items",
    )

    sample_identifier = models.CharField(
        max_length=255,
    )

    assignment_id_snapshot = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    location_id_snapshot = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    # Immutable physical destination recorded when the
    # movement occurred. Null on historical legacy records.
    destination_location_id_snapshot = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    position_before = models.CharField(
        max_length=100,
        blank=True,
    )
    position_after = models.CharField(
        max_length=100,
        blank=True,
    )

    path_before = models.TextField(blank=True)
    path_after = models.TextField(blank=True)

    class Meta:
        ordering = ["pk"]


class StorageSceneConfiguration(models.Model):
    """User-owned visual configuration, separate from physical inventory."""

    PROFILE_CHOICES = [
        ("auto", "Automatic"),
        ("space", "Space"),
        ("cabinet", "Cabinet"),
        ("shelves", "Shelves"),
        ("rack", "Rack"),
        ("grid", "Grid"),
        ("generic", "Generic"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="storage_scene_configurations",
    )

    root_location = models.ForeignKey(
        StorageLocation,
        on_delete=models.CASCADE,
        related_name="scene_configurations",
    )

    name = models.CharField(max_length=120)

    root_profile = models.CharField(
        max_length=20,
        choices=PROFILE_CHOICES,
        default="auto",
    )

    profile_overrides = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="unique_storage_scene_owner_name_v8",
            )
        ]

    def __str__(self):
        return self.name


class StorageLocationLayoutV8146C3(models.Model):
    """Optional organization and capacity for a real storage location."""

    ORGANIZATION_CHOICES = (
        ("free", "Free organization"),
        ("grid", "Position grid"),
    )

    location = models.OneToOneField(
        StorageLocation,
        on_delete=models.CASCADE,
        related_name="layout_v8146c3",
    )

    organization = models.CharField(
        max_length=10,
        choices=ORGANIZATION_CHOICES,
        default="free",
    )

    rows = models.PositiveSmallIntegerField(default=0)
    columns = models.PositiveSmallIntegerField(default=0)

    type_label = models.CharField(
        max_length=80,
        blank=True,
    )

    temperature_label = models.CharField(
        max_length=60,
        blank=True,
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        organization="free",
                        rows=0,
                        columns=0,
                    )
                    | models.Q(
                        organization="grid",
                        rows__gte=1,
                        rows__lte=26,
                        columns__gte=1,
                        columns__lte=24,
                    )
                ),
                name="valid_storage_layout_v8146c3",
            ),
        ]

    @property
    def capacity(self):
        if self.organization != "grid":
            return None
        return self.rows * self.columns

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()

        if self.organization == "free":
            if self.rows != 0 or self.columns != 0:
                raise ValidationError(
                    "Free organization must not define grid dimensions."
                )
            return

        if self.organization == "grid":
            if not (
                1 <= self.rows <= 26
                and 1 <= self.columns <= 24
            ):
                raise ValidationError(
                    "Grid dimensions must contain 1 to 26 rows "
                    "and 1 to 24 columns."
                )
            return

        raise ValidationError("Invalid storage organization.")

    def __str__(self):
        return (
            f"{self.location_id}: {self.rows}x{self.columns}"
            if self.organization == "grid"
            else f"{self.location_id}: free"
        )
