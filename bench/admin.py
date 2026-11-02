from django.contrib import admin

from bench.models import BookableResource, Booking


@admin.register(BookableResource)
class BookableResourceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "research_group",
        "is_bookable",
        "is_active",
        "max_minutes",
        "max_slots",
        "can_overlap",
        "booking_window_days",
    )
    list_filter = ("is_bookable", "is_active", "can_overlap", "research_group")
    search_fields = ("name", "description")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("resource", "user", "start", "end", "title", "cancelled_at")
    list_filter = ("resource", "cancelled_at")
    search_fields = ("title", "note", "user__username", "resource__name")
    date_hierarchy = "start"
    raw_id_fields = ("notebook_entry",)
    readonly_fields = ("exclusive", "recurrence_id", "recurrence_index", "recurrence_rule", "created_at", "updated_at")
