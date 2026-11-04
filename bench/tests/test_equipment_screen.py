from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from bench.models import BookableResource
from core.models import ResearchGroup


class EquipmentScreenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.coord = User.objects.create_user("eq-coord", password="x")
        cls.member = User.objects.create_user("eq-member", password="x")
        cls.other = User.objects.create_user("eq-other", password="x")
        cls.group = ResearchGroup.objects.create(name="Eq Group", coordinator=cls.coord)
        cls.group.members.add(cls.member)
        cls.foreign = ResearchGroup.objects.create(name="Foreign", coordinator=cls.other)
        cls.res = BookableResource.objects.create(name="Confocal", research_group=cls.group)

    def data(self, **extra):
        d = {"name": "qPCR", "research_group": self.group.pk, "color": "#112233", "max_minutes": 90,
             "max_slots": 0, "booking_window_days": 0, "cancel_minutes": 0, "is_bookable": "on", "is_cancellable": "on"}
        d.update(extra)
        return d

    def test_coordinator_creates(self):
        self.client.force_login(self.coord)
        r = self.client.post(reverse("bench:equipment_new"), self.data())
        self.assertRedirects(r, reverse("bench:equipment_list"))
        made = BookableResource.objects.get(name="qPCR")
        self.assertEqual((made.max_minutes, made.created_by), (90, self.coord))

    def test_cannot_use_foreign_group(self):
        self.client.force_login(self.coord)
        r = self.client.post(reverse("bench:equipment_new"), self.data(research_group=self.foreign.pk))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(BookableResource.objects.filter(name="qPCR").exists())

    def test_member_sees_but_cannot_edit(self):
        self.client.force_login(self.member)
        page = self.client.get(reverse("bench:equipment_list"))
        self.assertContains(page, "Confocal")
        self.assertNotContains(page, "New layer")
        self.assertEqual(self.client.get(reverse("bench:equipment_new")).status_code, 403)
        self.assertEqual(self.client.get(reverse("bench:equipment_edit", args=[self.res.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("bench:equipment_toggle", args=[self.res.pk])).status_code, 403)

    def test_outsider_does_not_see_it(self):
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("bench:equipment_list")), "Confocal")

    def test_edit_and_archive(self):
        self.client.force_login(self.coord)
        self.client.post(reverse("bench:equipment_edit", args=[self.res.pk]), self.data(name="Confocal 2"))
        self.res.refresh_from_db()
        self.assertEqual(self.res.name, "Confocal 2")
        self.client.post(reverse("bench:equipment_toggle", args=[self.res.pk]))
        self.res.refresh_from_db()
        self.assertFalse(self.res.is_active)

    def test_bad_colour(self):
        self.client.force_login(self.coord)
        r = self.client.post(reverse("bench:equipment_new"), self.data(color="red"))
        self.assertEqual(r.status_code, 200)


class LayerStyleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = get_user_model().objects.create_user("ls-ana", password="x")
        cls.bob = get_user_model().objects.create_user("ls-bob", password="x")

    def test_defaults_and_custom_style_per_person(self):
        from bench.services.layers import styles_for

        self.assertEqual(styles_for(self.ana)["steps"]["color"], "#7c3aed")
        self.client.force_login(self.ana)
        self.client.post(reverse("bench:layer_style", args=["steps"]),
                         {"label": "My deadlines", "color": "#ff0000", "description": "Things I owe"})
        mine = styles_for(self.ana)["steps"]
        self.assertEqual((mine["label"], mine["color"], mine["description"], mine["custom"]),
                         ("My deadlines", "#ff0000", "Things I owe", True))
        self.assertEqual(styles_for(self.bob)["steps"]["color"], "#7c3aed")

    def test_style_reaches_the_feed_and_reset_restores_it(self):
        from datetime import timedelta

        from django.utils import timezone

        from bench.services import calendar_feed
        from core.models import NotebookEntry, NotebookStep

        entry = NotebookEntry.objects.create(title="E", author=self.ana)
        when = timezone.now() + timedelta(days=1)
        NotebookStep.objects.create(entry=entry, body="x", deadline=when)
        self.client.force_login(self.ana)
        self.client.post(reverse("bench:layer_style", args=["steps"]), {"label": "L", "color": "#112233", "description": "d"})
        feed = calendar_feed.feed(self.ana, when - timedelta(hours=1), when + timedelta(hours=1), ["steps"])
        self.assertEqual(feed[0]["color"], "#112233")
        self.client.post(reverse("bench:layer_style", args=["steps"]), {"reset": "1"})
        feed = calendar_feed.feed(self.ana, when - timedelta(hours=1), when + timedelta(hours=1), ["steps"])
        self.assertEqual(feed[0]["color"], "#7c3aed")

    def test_bad_colour_and_unknown_key(self):
        from bench.services.layers import styles_for

        self.client.force_login(self.ana)
        self.client.post(reverse("bench:layer_style", args=["steps"]), {"color": "red"})
        self.assertFalse(styles_for(self.ana)["steps"]["custom"])
        self.assertEqual(self.client.post(reverse("bench:layer_style", args=["nope"]), {}).status_code, 404)

    def test_calendar_lists_builtin_layers(self):
        self.client.force_login(self.ana)
        data = self.client.get(reverse("bench:calendar_resources")).json()
        self.assertEqual([b["key"] for b in data["builtin"]], ["steps", "samples"])
