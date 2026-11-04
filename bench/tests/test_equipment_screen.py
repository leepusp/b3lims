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
        self.assertNotContains(page, "New equipment")
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
