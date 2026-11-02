from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from bench.models import BookableResource, Booking
from bench.services.booking_rules import (
    BookingRuleError,
    cancel_booking,
    create_booking,
    expand_recurrence,
    move_booking,
    validate_booking,
)
from core.models import ResearchGroup, ResourceAccessGrant
from core.services.resource_access import grant_resource_access


TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 11, 2, 8, 0, tzinfo=TZ)  # a Monday


def at(day, hour, minute=0):
    """Datetime on 2 Nov 2026 + day offset, local time."""
    return datetime(2026, 11, 2, hour, minute, tzinfo=TZ) + timedelta(days=day)


def codes(violations):
    return [v.code for v in violations]


@override_settings(TIME_ZONE="America/Sao_Paulo", USE_TZ=True)
class BookingRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.coordinator = User.objects.create_user("bench-coord", password="x")
        cls.member = User.objects.create_user("bench-member", password="x")
        cls.member2 = User.objects.create_user("bench-member2", password="x")
        cls.outsider = User.objects.create_user("bench-outsider", password="x")
        cls.admin = User.objects.create_superuser("bench-admin", password="x")
        cls.group = ResearchGroup.objects.create(name="Phage Lab (bench tests)", coordinator=cls.coordinator)
        cls.group.members.add(cls.member, cls.member2)
        cls.resource = BookableResource.objects.create(
            name="Biosafety cabinet BSC-02",
            research_group=cls.group,
            max_minutes=180,
            max_slots=4,
            booking_window_days=14,
            cancel_minutes=120,
        )

    def validate(self, user, start, end, **kwargs):
        return validate_booking(self.resource, user, start, end, now=NOW, **kwargs)

    # --- permission ---------------------------------------------------------

    def test_group_members_and_coordinator_can_book(self):
        for user in (self.member, self.coordinator, self.admin):
            self.assertEqual(self.validate(user, at(1, 9), at(1, 10)), [])

    def test_outsider_cannot_book_without_a_grant(self):
        self.assertIn("permission", codes(self.validate(self.outsider, at(1, 9), at(1, 10))))

    def test_explicit_edit_grant_allows_booking(self):
        grant_resource_access(
            resource=self.resource,
            access_level=ResourceAccessGrant.AccessLevel.EDIT,
            granted_by=self.coordinator,
            user=self.outsider,
        )
        self.assertEqual(self.validate(self.outsider, at(1, 9), at(1, 10)), [])

    def test_view_grant_is_not_enough(self):
        grant_resource_access(
            resource=self.resource,
            access_level=ResourceAccessGrant.AccessLevel.VIEW,
            granted_by=self.coordinator,
            user=self.outsider,
        )
        self.assertIn("permission", codes(self.validate(self.outsider, at(1, 9), at(1, 10))))

    def test_inactive_resource_cannot_be_booked(self):
        self.resource.is_bookable = False
        self.resource.save()
        self.assertIn("permission", codes(self.validate(self.member, at(1, 9), at(1, 10))))

    # --- single rules -------------------------------------------------------

    def test_end_must_be_after_start(self):
        self.assertEqual(codes(self.validate(self.member, at(1, 10), at(1, 9))), ["end_before_start"])

    def test_past_start_is_refused_unless_allowed(self):
        self.assertIn("in_past", codes(self.validate(self.member, at(-1, 9), at(-1, 10))))
        self.resource.users_can_book_in_past = True
        self.resource.save()
        self.assertNotIn("in_past", codes(self.validate(self.member, at(-1, 9), at(-1, 10))))

    def test_note_required(self):
        self.resource.requires_note = True
        self.resource.save()
        self.assertIn("note_required", codes(self.validate(self.member, at(1, 9), at(1, 10))))
        self.assertEqual(self.validate(self.member, at(1, 9), at(1, 10), note="Plaque assay"), [])

    def test_maximum_length(self):
        self.assertIn("too_long", codes(self.validate(self.member, at(1, 9), at(1, 13))))

    def test_booking_window(self):
        self.assertIn("outside_window", codes(self.validate(self.member, at(20, 9), at(20, 10))))

    def test_open_bookings_per_user(self):
        for day in (1, 2, 3):
            create_booking(self.resource, self.member, at(day, 9), at(day, 10), now=NOW)
        self.assertEqual(self.validate(self.member, at(4, 9), at(4, 10)), [])
        self.assertIn(
            "too_many_bookings",
            codes(self.validate(self.member, at(4, 9), at(4, 10), new_bookings=2)),
        )
        # Another member has their own quota.
        self.assertEqual(self.validate(self.member2, at(4, 11), at(4, 12)), [])

    def test_overlap_is_refused_but_touching_is_fine(self):
        create_booking(self.resource, self.member, at(1, 9), at(1, 11), now=NOW)
        self.assertIn("overlap", codes(self.validate(self.member2, at(1, 10), at(1, 12))))
        self.assertEqual(self.validate(self.member2, at(1, 11), at(1, 12)), [])

    def test_overlap_allowed_when_resource_permits_it(self):
        self.resource.can_overlap = True
        self.resource.save()
        create_booking(self.resource, self.member, at(1, 9), at(1, 11), now=NOW)
        self.assertEqual(self.validate(self.member2, at(1, 10), at(1, 12)), [])

    def test_cancelled_bookings_do_not_block(self):
        booking = create_booking(self.resource, self.member, at(1, 9), at(1, 11), now=NOW)[0]
        cancel_booking(booking, self.member, now=NOW)
        self.assertEqual(self.validate(self.member2, at(1, 10), at(1, 11)), [])

    def test_every_broken_rule_is_reported(self):
        create_booking(self.resource, self.member, at(16, 9), at(16, 10), now=NOW + timedelta(days=10))
        result = codes(self.validate(self.outsider, at(16, 8), at(16, 12)))
        self.assertEqual(result, ["permission", "too_long", "outside_window", "overlap"])

    # --- recurrence ---------------------------------------------------------

    def test_daily_recurrence_with_count(self):
        occurrences = expand_recurrence(at(1, 9), at(1, 10), {"frequency": "daily", "interval": 2, "count": 3})
        self.assertEqual([s for s, _ in occurrences], [at(1, 9), at(3, 9), at(5, 9)])

    def test_weekly_recurrence_on_weekdays_until_date(self):
        occurrences = expand_recurrence(
            at(0, 14),
            at(0, 15),
            {"frequency": "weekly", "interval": 1, "weekdays": [0, 3], "until": "2026-11-12"},
        )
        self.assertEqual([s.date().isoformat() for s, _ in occurrences], ["2026-11-02", "2026-11-05", "2026-11-09", "2026-11-12"])
        self.assertTrue(all(e - s == timedelta(hours=1) for s, e in occurrences))

    def test_invalid_recurrence_is_rejected(self):
        for rule in (
            {"frequency": "monthly", "count": 2},
            {"frequency": "daily"},
            {"frequency": "daily", "count": 2, "until": "2026-12-01"},
            {"frequency": "weekly", "weekdays": [9], "count": 2},
            {"frequency": "daily", "count": 500},
        ):
            with self.subTest(rule=rule), self.assertRaises(ValidationError):
                expand_recurrence(at(1, 9), at(1, 10), rule)

    def test_series_is_saved_with_one_recurrence_id(self):
        bookings = create_booking(
            self.resource,
            self.member,
            at(1, 9),
            at(1, 10),
            recurrence={"frequency": "weekly", "count": 2},
            now=NOW,
        )
        self.assertEqual(len(bookings), 2)
        self.assertEqual(len({b.recurrence_id for b in bookings}), 1)
        self.assertEqual([b.recurrence_index for b in bookings], [1, 2])

    def test_series_with_a_conflict_saves_nothing(self):
        create_booking(self.resource, self.member2, at(2, 9), at(2, 10), now=NOW)
        with self.assertRaises(BookingRuleError) as raised:
            create_booking(
                self.resource,
                self.member,
                at(1, 9),
                at(1, 10),
                recurrence={"frequency": "daily", "count": 3},
                now=NOW,
            )
        overlap = [v for v in raised.exception.violations if v.code == "overlap"]
        self.assertEqual([v.occurrence for v in overlap], [1])
        self.assertEqual(Booking.objects.filter(user=self.member).count(), 0)

    def test_series_counts_against_open_booking_limit(self):
        with self.assertRaises(BookingRuleError) as raised:
            create_booking(
                self.resource,
                self.member,
                at(1, 9),
                at(1, 10),
                recurrence={"frequency": "daily", "count": 5},
                now=NOW,
            )
        self.assertIn("too_many_bookings", codes(raised.exception.violations))

    # --- move and cancel ----------------------------------------------------

    def test_move_rechecks_rules_and_ignores_itself(self):
        booking = create_booking(self.resource, self.member, at(1, 9), at(1, 10), now=NOW)[0]
        move_booking(booking, self.member, at(1, 9, 30), at(1, 10, 30), now=NOW)
        booking.refresh_from_db()
        self.assertEqual(booking.start, at(1, 9, 30))
        with self.assertRaises(BookingRuleError):
            move_booking(booking, self.member, at(1, 9), at(1, 14), now=NOW)

    def test_only_owner_or_manager_can_cancel(self):
        booking = create_booking(self.resource, self.member, at(1, 9), at(1, 10), now=NOW)[0]
        with self.assertRaises(BookingRuleError):
            cancel_booking(booking, self.member2, now=NOW)
        cancel_booking(booking, self.coordinator, now=NOW)
        booking.refresh_from_db()
        self.assertIsNotNone(booking.cancelled_at)
        self.assertEqual(booking.cancelled_by, self.coordinator)

    def test_cancellation_notice(self):
        booking = create_booking(self.resource, self.member, at(0, 9), at(0, 10), now=NOW)[0]
        with self.assertRaises(BookingRuleError) as raised:
            cancel_booking(booking, self.member, now=NOW)  # 60 min before, 120 required
        self.assertEqual(codes(raised.exception.violations), ["too_late_to_cancel"])

    def test_not_cancellable_resource(self):
        self.resource.is_cancellable = False
        self.resource.save()
        booking = create_booking(self.resource, self.member, at(3, 9), at(3, 10), now=NOW)[0]
        with self.assertRaises(BookingRuleError):
            cancel_booking(booking, self.member, now=NOW)

    def test_cancel_rest_of_series(self):
        bookings = create_booking(
            self.resource,
            self.member,
            at(1, 9),
            at(1, 10),
            recurrence={"frequency": "daily", "count": 3},
            now=NOW,
        )
        cancel_booking(bookings[1], self.member, now=NOW, whole_series=True)
        states = [Booking.objects.get(pk=b.pk).is_cancelled for b in bookings]
        self.assertEqual(states, [False, True, True])
