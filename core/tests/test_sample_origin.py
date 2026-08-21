from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models.samples.origin import SampleOrigin
from core.models.samples.sample import Sample
from core.services.sample_origin import (
    save_sample_origin,
)


class SampleOriginTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.user = (
            user_model.objects.create_user(
                username="originowner",
                password="test-password",
            )
        )

        self.sample = Sample.objects.create(
            sample_id="ORIGIN-001",
            sample_type="Other",
            organism_name=(
                "Marine environmental Sample"
            ),
            owner=self.user,
            status="available",
            is_public=False,
            is_active=True,
        )

    @staticmethod
    def client_path(url):
        prefix = str(
            getattr(
                settings,
                "FORCE_SCRIPT_NAME",
                "",
            )
            or ""
        )

        if (
            prefix
            and url.startswith(prefix)
        ):
            return (
                url[len(prefix):]
                or "/"
            )

        return url

    def test_ocean_coordinates_are_valid(self):
        origin = SampleOrigin(
            sample=self.sample,
            collection_site_name=(
                "South Atlantic Station 01"
            ),
            country_or_ocean=(
                "South Atlantic Ocean"
            ),
            latitude=Decimal(
                "-28.224100"
            ),
            longitude=Decimal(
                "-39.887200"
            ),
            depth_m=Decimal(
                "1120.000"
            ),
            environmental_medium=(
                "Ocean water"
            ),
        )

        origin.full_clean()
        origin.save()

        self.assertTrue(
            origin.has_coordinates
        )

        self.assertEqual(
            origin.coordinate_text,
            "-28.224100, -39.887200",
        )

    def test_coordinates_must_be_a_pair(self):
        origin = SampleOrigin(
            sample=self.sample,
            latitude=Decimal(
                "-23.000000"
            ),
        )

        with self.assertRaises(
            ValidationError
        ):
            origin.full_clean()

    def test_coordinate_ranges_are_validated(self):
        origin = SampleOrigin(
            sample=self.sample,
            latitude=Decimal(
                "91.000000"
            ),
            longitude=Decimal(
                "181.000000"
            ),
        )

        with self.assertRaises(
            ValidationError
        ):
            origin.full_clean()

    def test_blank_origin_removes_existing_origin(self):
        SampleOrigin.objects.create(
            sample=self.sample,
            country_or_ocean=(
                "Atlantic Ocean"
            ),
            latitude=Decimal(
                "-20.000000"
            ),
            longitude=Decimal(
                "-30.000000"
            ),
        )

        save_sample_origin(
            self.sample,
            {
                "collection_site_name": "",
                "collection_date": None,
                "geo_loc_name": "",
                "country_or_ocean": "",
                "latitude": None,
                "longitude": None,
                "depth_m": None,
                "elevation_m": None,
                "habitat": "",
                "environmental_medium": "",
                "env_broad_scale": "",
                "env_local_scale": "",
                "collection_method": "",
                "notes": "",
                "location_visibility": (
                    "internal"
                ),
            },
        )

        self.assertFalse(
            SampleOrigin.objects.filter(
                sample=self.sample
            ).exists()
        )

    def test_create_without_origin_remains_valid(self):
        self.client.force_login(
            self.user
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_add"
                )
            ),
            {
                "action": "add_sample",
                "sample_id": (
                    "ORIGIN-NONE-001"
                ),
                "sample_type": "Other",
                "custom_organism_name": (
                    "Sample without provenance"
                ),
                "biosafety_level": "",
                "aliquot_count": "1",
                "owner": str(
                    self.user.pk
                ),
                "research_group": "",
                "storage_location": "",
                "scientific_notes": "",
                "collaborator": "",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        sample = Sample.objects.get(
            sample_id="ORIGIN-NONE-001"
        )

        self.assertFalse(
            SampleOrigin.objects.filter(
                sample=sample
            ).exists()
        )

    def test_create_persists_marine_origin(self):
        self.client.force_login(
            self.user
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_add"
                )
            ),
            {
                "action": "add_sample",
                "sample_id": (
                    "ORIGIN-MARINE-001"
                ),
                "sample_type": "Other",
                "custom_organism_name": (
                    "Ocean Sample"
                ),
                "biosafety_level": "",
                "aliquot_count": "1",
                "owner": str(
                    self.user.pk
                ),
                "research_group": "",
                "storage_location": "",
                "scientific_notes": "",
                "collaborator": "",

                "origin-collection_site_name": (
                    "Oceanographic Station A"
                ),
                "origin-collection_date": (
                    "2026-08-01"
                ),
                "origin-geo_loc_name": (
                    "South Atlantic Ocean"
                ),
                "origin-country_or_ocean": (
                    "Atlantic Ocean"
                ),
                "origin-latitude": (
                    "-28.224100"
                ),
                "origin-longitude": (
                    "-39.887200"
                ),
                "origin-depth_m": (
                    "1120.000"
                ),
                "origin-elevation_m": "",
                "origin-habitat": (
                    "Pelagic marine environment"
                ),
                "origin-environmental_medium": (
                    "Ocean water"
                ),
                "origin-env_broad_scale": (
                    "Marine biome"
                ),
                "origin-env_local_scale": (
                    "Open ocean water column"
                ),
                "origin-collection_method": (
                    "Oceanographic water sampler"
                ),
                "origin-notes": (
                    "Collected offshore."
                ),
                "origin-location_visibility": (
                    "internal"
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        sample = Sample.objects.get(
            sample_id="ORIGIN-MARINE-001"
        )

        origin = sample.origin

        self.assertEqual(
            origin.country_or_ocean,
            "Atlantic Ocean",
        )

        self.assertEqual(
            origin.latitude,
            Decimal(
                "-28.224100"
            ),
        )

        self.assertEqual(
            origin.longitude,
            Decimal(
                "-39.887200"
            ),
        )

        self.assertEqual(
            origin.depth_m,
            Decimal(
                "1120.000"
            ),
        )

        self.assertEqual(
            origin.location_visibility,
            "internal",
        )

    def test_edit_updates_origin(self):
        origin = SampleOrigin.objects.create(
            sample=self.sample,
            country_or_ocean=(
                "Atlantic Ocean"
            ),
            latitude=Decimal(
                "-20.000000"
            ),
            longitude=Decimal(
                "-30.000000"
            ),
        )

        self.client.force_login(
            self.user
        )

        url = reverse(
            "sample_edit",
            args=[
                self.sample.pk
            ],
        )

        response = self.client.post(
            self.client_path(url),
            {
                "sample_id": (
                    self.sample.sample_id
                ),
                "sample_type": (
                    self.sample.sample_type
                ),
                "organism_name": (
                    self.sample.organism_name
                ),
                "biosafety_level": "",
                "status": "available",
                "aliquot_count": "1",
                "owner": str(
                    self.user.pk
                ),
                "research_group": "",
                "biobank": "",
                "collections": [],
                "storage_location": "",
                "scientific_notes": "",
                "collaborator": "",

                "origin-collection_site_name": (
                    "Deep Station B"
                ),
                "origin-collection_date": "",
                "origin-geo_loc_name": (
                    "Central South Atlantic"
                ),
                "origin-country_or_ocean": (
                    "South Atlantic Ocean"
                ),
                "origin-latitude": (
                    "-25.123456"
                ),
                "origin-longitude": (
                    "-35.654321"
                ),
                "origin-depth_m": (
                    "2500.000"
                ),
                "origin-elevation_m": "",
                "origin-habitat": (
                    "Deep ocean"
                ),
                "origin-environmental_medium": (
                    "Ocean water"
                ),
                "origin-env_broad_scale": "",
                "origin-env_local_scale": "",
                "origin-collection_method": "",
                "origin-notes": "",
                "origin-location_visibility": (
                    "internal"
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        origin.refresh_from_db()

        self.assertEqual(
            origin.collection_site_name,
            "Deep Station B",
        )

        self.assertEqual(
            origin.latitude,
            Decimal(
                "-25.123456"
            ),
        )

        self.assertEqual(
            origin.longitude,
            Decimal(
                "-35.654321"
            ),
        )

        self.assertEqual(
            origin.depth_m,
            Decimal(
                "2500.000"
            ),
        )
