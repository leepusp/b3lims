from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    ResourceAccessGrant,
    Sample,
    SampleOrigin,
    SampleTaxonomyAssignment,
)
from core.services.resource_access import (
    grant_resource_access,
)


class CollectionExplorerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="collection-owner",
            password="test-password",
        )

        cls.outsider = User.objects.create_user(
            username="collection-outsider",
            password="test-password",
        )

        cls.collection = Collection.objects.create(
            name="Interactive Collection",
            description="Collection Explorer test dataset.",
            owner=cls.owner,
            is_active=True,
            is_public=False,
        )

        cls.private_sample = Sample.objects.create(
            sample_id="COL-PRIVATE-001",
            sample_type="Bacteria",
            organism_name="Private organism",
            owner=cls.owner,
            is_public=False,
            is_active=True,
        )
        cls.private_sample.collections.add(
            cls.collection
        )

        cls.public_sample = Sample.objects.create(
            sample_id="COL-PUBLIC-001",
            sample_type="Phage",
            organism_name="Public organism",
            owner=cls.owner,
            is_public=True,
            is_active=True,
        )
        cls.public_sample.collections.add(
            cls.collection
        )

        cls.inactive_sample = Sample.objects.create(
            sample_id="COL-INACTIVE-001",
            sample_type="Bacteria",
            organism_name="Inactive organism",
            owner=cls.owner,
            is_public=True,
            is_active=False,
        )
        cls.inactive_sample.collections.add(
            cls.collection
        )

        SampleOrigin.objects.create(
            sample=cls.private_sample,
            collection_site_name="São Paulo isolate site",
            country_or_ocean="Brazil",
            latitude=Decimal("-23.550520"),
            longitude=Decimal("-46.633308"),
            location_visibility="internal",
        )

        SampleOrigin.objects.create(
            sample=cls.public_sample,
            collection_site_name="Public isolate site",
            country_or_ocean="United States",
            latitude=Decimal("38.907200"),
            longitude=Decimal("-77.036900"),
            location_visibility="internal",
        )

        SampleTaxonomyAssignment.objects.create(
            sample=cls.private_sample,
            source="ncbi",
            taxon_id="287",
            scientific_name="Pseudomonas aeruginosa",
            rank="species",
            domain_or_realm="Bacteria",
            phylum="Pseudomonadota",
            family="Pseudomonadaceae",
            genus="Pseudomonas",
            species="Pseudomonas aeruginosa",
            match_status=(
                SampleTaxonomyAssignment
                .STATUS_CANDIDATE
            ),
            is_current=True,
        )

        SampleTaxonomyAssignment.objects.create(
            sample=cls.public_sample,
            source="ncbi",
            taxon_id="562",
            scientific_name="Escherichia coli",
            rank="species",
            domain_or_realm="Bacteria",
            phylum="Pseudomonadota",
            family="Enterobacteriaceae",
            genus="Escherichia",
            species="Escherichia coli",
            match_status=(
                SampleTaxonomyAssignment
                .STATUS_VERIFIED
            ),
            is_current=True,
        )

    def detail_url(self):
        return reverse(
            "collection_detail",
            args=[
                self.collection.pk,
            ],
        )

    def test_owner_can_open_collection_explorer(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.detail_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            "Collection Explorer",
        )
        self.assertContains(
            response,
            "COL-PRIVATE-001",
        )
        self.assertContains(
            response,
            "COL-PUBLIC-001",
        )
        self.assertNotContains(
            response,
            "COL-INACTIVE-001",
        )

    def test_unauthorized_user_cannot_open_private_collection(self):
        self.client.force_login(
            self.outsider
        )

        response = self.client.get(
            self.detail_url()
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_collection_view_grant_does_not_leak_private_sample(self):
        grant_resource_access(
            resource=self.collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.outsider,
        )

        self.client.force_login(
            self.outsider
        )

        response = self.client.get(
            self.detail_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        # Collection-level sharing permits the Explorer itself.
        self.assertContains(
            response,
            "Interactive Collection",
        )

        # Public Sample remains independently visible.
        self.assertContains(
            response,
            "COL-PUBLIC-001",
        )

        # Collection access must not silently grant access to a
        # private Sample owned by another principal.
        self.assertNotContains(
            response,
            "COL-PRIVATE-001",
        )

    def test_owner_explorer_builds_taxonomy_and_geography(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.detail_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Taxonomic Composition",
        )
        self.assertContains(
            response,
            "Geographic Distribution",
        )
        self.assertContains(
            response,
            "data-sample-origin-dashboard",
        )

        taxonomy_labels = {
            row["label"]
            for section in response.context[
                "taxonomy_sections"
            ]
            for row in section["rows"]
        }

        self.assertIn(
            "Pseudomonas",
            taxonomy_labels,
        )
        self.assertIn(
            "Escherichia",
            taxonomy_labels,
        )

        points = response.context[
            "sample_origin_points"
        ]

        self.assertEqual(
            {
                point["sample_id"]
                for point in points
            },
            {
                "COL-PRIVATE-001",
                "COL-PUBLIC-001",
            },
        )

        self.assertEqual(
            response.context[
                "sample_origin_map_stats"
            ][
                "with_coordinates"
            ],
            2,
        )

        countries = {
            row["label"]
            for row in response.context[
                "country_distribution"
            ]
        }

        self.assertEqual(
            countries,
            {
                "Brazil",
                "United States",
            },
        )

    def test_collection_grant_does_not_leak_scientific_aggregates(self):
        grant_resource_access(
            resource=self.collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.outsider,
        )

        self.client.force_login(
            self.outsider
        )

        response = self.client.get(
            self.detail_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        points = response.context[
            "sample_origin_points"
        ]

        self.assertEqual(
            [
                point["sample_id"]
                for point in points
            ],
            [
                "COL-PUBLIC-001",
            ],
        )

        taxonomy_labels = {
            row["label"]
            for section in response.context[
                "taxonomy_sections"
            ]
            for row in section["rows"]
        }

        self.assertIn(
            "Escherichia",
            taxonomy_labels,
        )

        self.assertNotIn(
            "Pseudomonas",
            taxonomy_labels,
        )

        countries = {
            row["label"]
            for row in response.context[
                "country_distribution"
            ]
        }

        self.assertEqual(
            countries,
            {
                "United States",
            },
        )

        self.assertNotContains(
            response,
            "São Paulo isolate site",
        )

    def test_inactive_collection_is_not_available_in_explorer(self):
        self.collection.is_active = False
        self.collection.save(
            update_fields=[
                "is_active",
            ]
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.detail_url()
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_collection_list_links_to_explorer(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            reverse(
                "collections_list"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            self.detail_url(),
        )
