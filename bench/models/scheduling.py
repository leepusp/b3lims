"""Lab Calendar: bookable equipment and bookings (roadmap step 2.1)."""

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class BookableResource(models.Model):
    """A piece of equipment (or room) that people book in the Lab Calendar.

    Every limit set to 0 means "no limit".
    """

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    research_group = models.ForeignKey(
        "core.ResearchGroup",
        on_delete=models.SET_NULL,
        related_name="bookable_resources",
        null=True,
        blank=True,
        help_text="Members and the coordinator of this group can book it.",
    )
    location = models.ForeignKey(
        "core.StorageLocation",
        on_delete=models.SET_NULL,
        related_name="bookable_resources",
        null=True,
        blank=True,
    )
    color = models.CharField(max_length=7, default="#0b66b2")

    is_bookable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)
    max_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Longest booking allowed, in minutes (0 = no limit).",
    )
    max_slots = models.PositiveIntegerField(
        default=0,
        help_text="Open future bookings one user may hold (0 = no limit).",
    )
    can_overlap = models.BooleanField(
        default=False,
        help_text="Allow bookings that overlap in time.",
    )
    users_can_book_in_past = models.BooleanField(default=False)
    is_cancellable = models.BooleanField(default=True)
    cancel_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Minimum notice to cancel, in minutes before the start (0 = any time).",
    )
    booking_window_days = models.PositiveIntegerField(
        default=0,
        help_text="How many days ahead people can book (0 = no limit).",
    )
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="BRL")
    requires_note = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="bench_created_resources",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Bookable resource"
        verbose_name_plural = "Bookable resources"

    def __str__(self):
        return self.name


class BookingQuerySet(models.QuerySet):
    def active(self):
        return self.filter(cancelled_at__isnull=True)

    def overlapping(self, start, end):
        return self.filter(start__lt=end, end__gt=start)


class Booking(models.Model):
    """One reserved time slot. A recurring series is several rows sharing
    ``recurrence_id``."""

    resource = models.ForeignKey(
        BookableResource,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bench_bookings",
    )
    research_group = models.ForeignKey(
        "core.ResearchGroup",
        on_delete=models.SET_NULL,
        related_name="bench_bookings",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField()
    notebook_entry = models.ForeignKey(
        "core.NotebookEntry",
        on_delete=models.SET_NULL,
        related_name="bench_bookings",
        null=True,
        blank=True,
    )

    exclusive = models.BooleanField(
        default=True,
        editable=False,
        help_text="Copied from the resource (not can_overlap) when the booking is created; "
        "PostgreSQL rejects overlapping exclusive bookings.",
    )

    recurrence_id = models.UUIDField(null=True, blank=True, db_index=True)
    recurrence_index = models.PositiveIntegerField(null=True, blank=True)
    recurrence_rule = models.JSONField(null=True, blank=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="bench_cancelled_bookings",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BookingQuerySet.as_manager()

    class Meta:
        ordering = ("start", "id")
        indexes = (
            models.Index(fields=("resource", "start"), name="bench_booking_res_start_idx"),
        )
        constraints = (
            models.CheckConstraint(
                condition=Q(end__gt=F("start")),
                name="bench_booking_end_after_start",
            ),
        )

    def __str__(self):
        return f"{self.resource} · {self.start:%Y-%m-%d %H:%M}"

    @property
    def is_cancelled(self):
        return self.cancelled_at is not None
