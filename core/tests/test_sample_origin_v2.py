from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.forms import SampleOriginForm
from core.models import Sample
from core.models.samples.origin import SampleOrigin
from core.services.sample_origin import (
    ORIGIN_VALUE_FIELDS,
    origin_data_has_content,
    save_sample_origin,
)


class SampleOriginV2Tests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="originv2owner",
            password="test-password",
        )

        self.sample = Sample.objects.create(
            sample_id="ORIGIN-V2-001",
            sample_type="Bacterium (Host)",
            organism_name="Origin V2 organism",
            owner=self.owner,
            status="available",
            is_public=False,
            is_active=True,
        )

        self.client.force_login(
            self.owner
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

    def test_v2_fields_are_part_of_origin_value_contract(self):
        expected = {
            "culture_status",
            "acquisition_source",
            "source_collection_name",
            "source_collection_accession",
            "ecosystem",
            "ecosystem_category",
            "ecosystem_type",
            "ecosystem_subtype",
            "specific_ecosystem",
            "coordinate_source",
            "coordinate_uncertainty_m",
        }

        self.assertTrue(
            expected.issubset(
                set(
                    ORIGIN_VALUE_FIELDS
                )
            )
        )

    def test_blank_extended_metadata_does_not_create_origin(self):
        form = SampleOriginForm(
            data={
                "culture_status": "",
                "acquisition_source": "",
                "source_collection_name": "",
                "source_collection_accession": "",
                "collection_site_name": "",
                "collection_date": "",
                "geo_loc_name": "",
                "country_or_ocean": "",
                "latitude": "",
                "longitude": "",
                "coordinate_source": "",
                "coordinate_uncertainty_m": "",
                "depth_m": "",
                "elevation_m": "",
                "habitat": "",
                "environmental_medium": "",
                "env_broad_scale": "",
                "env_local_scale": "",
                "ecosystem": "",
                "ecosystem_category": "",
                "ecosystem_type": "",
                "ecosystem_subtype": "",
                "specific_ecosystem": "",
                "collection_method": "",
                "notes": "",
                "location_visibility": "internal",
            }
        )

        self.assertTrue(
            form.is_valid(),
            form.errors,
        )

        self.assertFalse(
            origin_data_has_content(
                form.cleaned_data
            )
        )

        result = save_sample_origin(
            self.sample,
            form.cleaned_data,
        )

        self.assertIsNone(
            result
        )

        self.assertFalse(
            SampleOrigin.objects.filter(
                sample=self.sample
            ).exists()
        )

    def test_extended_origin_metadata_is_persisted(self):
        form = SampleOriginForm(
            data={
                "culture_status": "cultured",
                "acquisition_source": "culture_collection",
                "source_collection_name": "DSMZ",
                "source_collection_accession": "DSM 12345",
                "collection_site_name": "Source station",
                "collection_date": "2026-08-20",
                "geo_loc_name": "São Paulo",
                "country_or_ocean": "Brazil",
                "latitude": "-23.550520",
                "longitude": "-46.633308",
                "coordinate_source": "gps",
                "coordinate_uncertainty_m": "12.500",
                "depth_m": "",
                "elevation_m": "760",
                "habitat": "Host-associated",
                "environmental_medium": "Host tissue",
                "env_broad_scale": "Host-associated biome",
                "env_local_scale": "Laboratory isolate",
                "ecosystem": "Host-associated",
                "ecosystem_category": "Animal",
                "ecosystem_type": "Mammal",
                "ecosystem_subtype": "Human",
                "specific_ecosystem": "Clinical isolate",
                "collection_method": "Sterile collection",
                "notes": "Imported provenance example.",
                "location_visibility": "internal",
            }
        )

        self.assertTrue(
            form.is_valid(),
            form.errors,
        )

        origin = save_sample_origin(
            self.sample,
            form.cleaned_data,
        )

        origin.refresh_from_db()

        self.assertEqual(
            origin.culture_status,
            "cultured",
        )

        self.assertEqual(
            origin.acquisition_source,
            "culture_collection",
        )

        self.assertEqual(
            origin.source_collection_name,
            "DSMZ",
        )

        self.assertEqual(
            origin.source_collection_accession,
            "DSM 12345",
        )

        self.assertEqual(
            origin.ecosystem,
            "Host-associated",
        )

        self.assertEqual(
            origin.ecosystem_category,
            "Animal",
        )

        self.assertEqual(
            origin.ecosystem_type,
            "Mammal",
        )

        self.assertEqual(
            origin.ecosystem_subtype,
            "Human",
        )

        self.assertEqual(
            origin.specific_ecosystem,
            "Clinical isolate",
        )

        self.assertEqual(
            origin.coordinate_source,
            "gps",
        )

        self.assertEqual(
            origin.coordinate_uncertainty_m,
            Decimal("12.500"),
        )

    def test_coordinate_source_requires_coordinates(self):
        origin = SampleOrigin(
            sample=self.sample,
            coordinate_source="gps",
        )

        with self.assertRaises(
            ValidationError
        ) as context:
            origin.full_clean()

        self.assertIn(
            "coordinate_source",
            context.exception.message_dict,
        )

    def test_coordinate_uncertainty_requires_coordinates(self):
        origin = SampleOrigin(
            sample=self.sample,
            coordinate_uncertainty_m=Decimal(
                "15.000"
            ),
        )

        with self.assertRaises(
            ValidationError
        ) as context:
            origin.full_clean()

        self.assertIn(
            "coordinate_uncertainty_m",
            context.exception.message_dict,
        )

    def test_coordinate_uncertainty_cannot_be_negative(self):
        origin = SampleOrigin(
            sample=self.sample,
            latitude=Decimal(
                "-23.550520"
            ),
            longitude=Decimal(
                "-46.633308"
            ),
            coordinate_uncertainty_m=Decimal(
                "-1.000"
            ),
        )

        with self.assertRaises(
            ValidationError
        ) as context:
            origin.full_clean()

        self.assertIn(
            "coordinate_uncertainty_m",
            context.exception.message_dict,
        )

    def test_edit_page_renders_extended_origin_fields(self):
        response = self.client.get(
            self.client_path(
                reverse(
                    "sample_edit",
                    args=[
                        self.sample.pk,
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        for field_name in (
            "culture_status",
            "acquisition_source",
            "source_collection_name",
            "source_collection_accession",
            "ecosystem",
            "ecosystem_category",
            "ecosystem_type",
            "ecosystem_subtype",
            "specific_ecosystem",
            "coordinate_source",
            "coordinate_uncertainty_m",
        ):
            self.assertContains(
                response,
                (
                    f'name="origin-'
                    f'{field_name}"'
                ),
            )

    def test_detail_renders_extended_origin_metadata(self):
        SampleOrigin.objects.create(
            sample=self.sample,
            culture_status="cultured",
            acquisition_source="culture_collection",
            source_collection_name="ATCC",
            source_collection_accession="ATCC 123",
            latitude=Decimal(
                "-23.550520"
            ),
            longitude=Decimal(
                "-46.633308"
            ),
            coordinate_source="gps",
            coordinate_uncertainty_m=Decimal(
                "25.000"
            ),
            ecosystem="Host-associated",
            ecosystem_category="Animal",
            ecosystem_type="Mammal",
            ecosystem_subtype="Human",
            specific_ecosystem="Clinical isolate",
        )

        response = self.client.get(
            self.client_path(
                reverse(
                    "sample_detail",
                    args=[
                        self.sample.pk,
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        for text in (
            "Origin / Acquisition",
            "Cultured",
            "Obtained from culture collection",
            "ATCC",
            "ATCC 123",
            "Coordinate Provenance",
            "GPS",
            "25.000 m",
            "Environmental Classification",
            "Host-associated",
            "Animal",
            "Mammal",
            "Human",
            "Clinical isolate",
        ):
            self.assertContains(
                response,
                text,
            )
