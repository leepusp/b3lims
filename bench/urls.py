from django.urls import path

from bench.views import calendar_api, home


app_name = "bench"

urlpatterns = [
    path("", home.bench_home, name="home"),
    path("calendar/events/", calendar_api.events, name="calendar_events"),
    path("calendar/resources/", calendar_api.resources, name="calendar_resources"),
    path("calendar/bookings/", calendar_api.booking_create, name="booking_create"),
    path("calendar/bookings/<int:booking_id>/move/", calendar_api.booking_move, name="booking_move"),
    path("calendar/bookings/<int:booking_id>/cancel/", calendar_api.booking_cancel, name="booking_cancel"),
]
