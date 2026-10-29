"""Tests for individual Biobank dashboards."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models.biobanks.biobank import Biobank
from core.models.biobanks.biobank_user_role import BiobankUserRole
from core.models.collections.collection import Collection
from core.models.samples.sample import Sample


class BiobankProfileDashboardTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="bb_dashboard_owner",
            first_name="Principal",
            last_name="Investigator",
        )

        cls.member = User.objects.create_user(
            username="bb_dashboard_member",
            first_name="Research",
            last_name="Member",
        )

        cls.outsider = User.objects.create_user(
            username="bb_dashboard_outsider",
        )

        cls.bank = Biobank.objects.create(
            name="Dashboard Test Biobank",
            owner=cls.owner,
            is_active=True,
            is_public=False,
        )

        BiobankUserRole.objects.create(
            user=cls.member,
            biobank=cls.bank,
            role=BiobankUserRole.VIEWER,
        )

    def url(self, bank=None):
        return reverse(
            "biobank_profile",
            args=[(bank or self.bank).pk],
        )

    def test_anonymous_redirected(self):
        self.assertEqual(
            self.client.get(self.url()).status_code,
            302,
        )

    def test_outsider_denied(self):
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(self.url()).status_code,
            403,
        )

    def test_owner_sees_member_names(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Principal Investigator")
        self.assertContains(response, "Research Member")
        self.assertEqual(response.context["member_total"], 2)

    def test_member_can_view(self):
        self.client.force_login(self.member)
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["internal_access"])

    def test_sample_collection_aggregation(self):
        collection = Collection.objects.create(
            name="Test Collection",
            owner=self.owner,
        )

        sample = Sample.objects.create(
            sample_id="BB_PROFILE_SAMPLE_001",
            owner=self.owner,
            biobank=self.bank,
            sample_type="Plasmid",
        )

        sample.collections.add(collection)

        self.client.force_login(self.owner)
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sample_total"], 1)
        self.assertEqual(response.context["collection_total"], 1)
        self.assertEqual(
            response.context["collection_stats"][0].linked_samples,
            1,
        )

    def test_public_only_access_hides_private_counts(self):
        public_bank = Biobank.objects.create(
            name="Public Dashboard Test",
            owner=self.owner,
            is_public=True,
            is_active=True,
        )

        Sample.objects.create(
            sample_id="BB_PROFILE_PRIVATE_001",
            owner=self.owner,
            biobank=public_bank,
            sample_type="Sensitive Sample",
            is_embargoed=True,
        )

        self.client.force_login(self.outsider)
        response = self.client.get(self.url(public_bank))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["internal_access"])
        self.assertIsNone(response.context["sample_total"])
        self.assertNotContains(response, "Sensitive Sample")

    def test_biobank_listing_contains_profile_link(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("biobanks_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{self.url()}"')
