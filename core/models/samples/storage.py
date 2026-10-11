from django.conf import settings
from django.db import models


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
            )
        ]

    def __str__(self):
        return f"{self.sample} → {self.location.full_path}"

    @property
    def full_path(self):
        return self.location.full_path


class StorageMovement(models.Model):
    """One auditable physical storage operation."""

    MOVEMENT_TYPES = [
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
