from django.urls import path

from bench.views import calendar_api, equipment, home


app_name = "bench"

urlpatterns = [
    path("", home.bench_home, name="home"),
    path("equipment/", equipment.equipment_list, name="equipment_list"),
    path("equipment/new/", equipment.equipment_form, name="equipment_new"),
    path("equipment/<int:resource_id>/", equipment.equipment_form, name="equipment_edit"),
    path("equipment/<int:resource_id>/toggle/", equipment.equipment_toggle, name="equipment_toggle"),
    path("calendar/events/", calendar_api.events, name="calendar_events"),
    path("calendar/resources/", calendar_api.resources, name="calendar_resources"),
    path("calendar/export.ics", calendar_api.view_ics, name="calendar_ics"),
    path("calendar/bookings/", calendar_api.booking_create, name="booking_create"),
    path("calendar/bookings/<int:booking_id>/event.ics", calendar_api.booking_ics, name="booking_ics"),
    path("calendar/bookings/<int:booking_id>/move/", calendar_api.booking_move, name="booking_move"),
    path("calendar/bookings/<int:booking_id>/cancel/", calendar_api.booking_cancel, name="booking_cancel"),
]
