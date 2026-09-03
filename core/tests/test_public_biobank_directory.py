from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Biobank
from core.services.public_catalog import (
    public_biobank_records,
    public_biobanks_queryset,
)


class PublicBiobankDirectoryTests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.owner = User.objects.create_user(
            username=(
                "PRIVATE-BIOBANK-OWNER-SENTINEL"
            ),
            first_name="Private",
            last_name="Owner Sentinel",
        )

        cls.public_biobank = (
            Biobank.objects.create(
                name=(
                    "PUBLIC-BIOBANK-SENTINEL"
                ),
                description=(
                    "Publication-approved institutional "
                    "Biobank description."
                ),
                location_label=(
                    "PUBLIC-LOCATION-SENTINEL"
                ),
                latitude="-23.561684",
                longitude="-46.730428",
                owner=cls.owner,
                is_public=True,
                is_active=True,
            )
        )

        cls.private_biobank = (
            Biobank.objects.create(
                name=(
                    "PRIVATE-BIOBANK-SENTINEL"
                ),
                description=(
                    "PRIVATE-DESCRIPTION-SENTINEL"
                ),
                location_label=(
                    "PRIVATE-LOCATION-SENTINEL"
                ),
                latitude="-22.000000",
                longitude="-45.000000",
                owner=cls.owner,
                is_public=False,
                is_active=True,
            )
        )

        cls.inactive_biobank = (
            Biobank.objects.create(
                name=(
                    "INACTIVE-BIOBANK-SENTINEL"
                ),
                description=(
                    "INACTIVE-DESCRIPTION-SENTINEL"
                ),
                location_label=(
                    "INACTIVE-LOCATION-SENTINEL"
                ),
                latitude="-21.000000",
                longitude="-44.000000",
                owner=cls.owner,
                is_public=True,
                is_active=False,
            )
        )


    def test_public_projection_contains_only_active_public_biobank(
        self,
    ):
        public_ids = set(
            public_biobanks_queryset()
            .values_list(
                "pk",
                flat=True,
            )
        )

        self.assertEqual(
            public_ids,
            {
                self.public_biobank.pk,
            },
        )


    def test_public_record_exposes_only_explicit_public_contract(
        self,
    ):
        records = (
            public_biobank_records()
        )

        self.assertEqual(
            len(records),
            1,
        )

        record = records[0]

        self.assertEqual(
            set(record),
            {
                "id",
                "name",
                "description",
                "location",
                "latitude",
                "longitude",
                "mapped",
            },
        )

        self.assertEqual(
            record["name"],
            self.public_biobank.name,
        )

        self.assertEqual(
            record["location"],
            self.public_biobank.location_label,
        )

        self.assertTrue(
            record["mapped"]
        )


    def test_public_directory_renders_only_public_active_biobank(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_biobanks"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            self.public_biobank.name,
        )

        self.assertContains(
            response,
            self.public_biobank.location_label,
        )

        self.assertNotContains(
            response,
            self.private_biobank.name,
        )

        self.assertNotContains(
            response,
            self.private_biobank.location_label,
        )

        self.assertNotContains(
            response,
            self.inactive_biobank.name,
        )

        self.assertContains(
            response,
            "public-biobank-map-data",
        )


    def test_public_directory_does_not_disclose_internal_owner_metadata(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_biobanks"
            )
        )

        self.assertNotContains(
            response,
            self.owner.username,
        )

        self.assertNotContains(
            response,
            self.owner.first_name,
        )

        self.assertNotContains(
            response,
            self.owner.last_name,
        )


    def test_public_detail_renders_public_biobank(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_biobank_detail",
                args=[
                    self.public_biobank.pk,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            self.public_biobank.name,
        )

        self.assertContains(
            response,
            self.public_biobank.description,
        )

        self.assertContains(
            response,
            self.public_biobank.location_label,
        )

        self.assertNotContains(
            response,
            self.owner.username,
        )


    def test_private_biobank_detail_is_not_found(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_biobank_detail",
                args=[
                    self.private_biobank.pk,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )


    def test_inactive_biobank_detail_is_not_found(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_biobank_detail",
                args=[
                    self.inactive_biobank.pk,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )


    def test_public_home_links_and_features_public_biobank_only(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_home"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            reverse(
                "public_biobanks"
            ),
        )

        self.assertContains(
            response,
            "Browse Biobanks",
        )

        self.assertContains(
            response,
            self.public_biobank.name,
        )

        self.assertNotContains(
            response,
            self.private_biobank.name,
        )

        self.assertNotContains(
            response,
            self.inactive_biobank.name,
        )


    def test_directory_payload_contains_no_private_biobank_sentinels(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_biobanks"
            )
        )

        body = response.content.decode(
            "utf-8"
        )

        for sentinel in (
            "PRIVATE-BIOBANK-SENTINEL",
            "PRIVATE-DESCRIPTION-SENTINEL",
            "PRIVATE-LOCATION-SENTINEL",
            "INACTIVE-BIOBANK-SENTINEL",
            "INACTIVE-DESCRIPTION-SENTINEL",
            "INACTIVE-LOCATION-SENTINEL",
            "PRIVATE-BIOBANK-OWNER-SENTINEL",
        ):
            self.assertNotIn(
                sentinel,
                body,
            )
