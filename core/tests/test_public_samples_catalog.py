from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Bacteria,
    Collection,
    Sample,
    SampleOrigin,
    SampleTaxonomyAssignment,
)
from core.services.public_catalog import (
    public_sample_catalog_queryset,
    public_sample_detail_record,
    public_sample_facets,
    search_public_samples_queryset,
)


class PublicSampleCatalogTests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.owner = User.objects.create_user(
            username=(
                "PRIVATE-SAMPLE-OWNER-SENTINEL"
            ),
            first_name="Private",
            last_name="Sample Owner",
        )

        cls.public_collection = (
            Collection.objects.create(
                name=(
                    "Published Sample Collection"
                ),
                description=(
                    "Publication-safe Collection."
                ),
                owner=cls.owner,
                is_public=True,
                is_active=True,
            )
        )

        cls.private_collection = (
            Collection.objects.create(
                name=(
                    "PRIVATE-COLLECTION-SENTINEL"
                ),
                owner=cls.owner,
                is_public=False,
                is_active=True,
            )
        )

        cls.public_bacterium = (
            Bacteria.objects.create(
                sample_id=(
                    "BAC-PUBLIC-001"
                ),
                sample_type=(
                    "Bacterium (Host)"
                ),
                organism_name=(
                    "Pseudomonas aeruginosa PA14"
                ),
                owner=cls.owner,
                genus="Pseudomonas",
                species=(
                    "Pseudomonas aeruginosa"
                ),
                strain="PA14",
                storage_location=(
                    "PRIVATE-STORAGE-SENTINEL"
                ),
                is_public=True,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.public_bacterium.collections.add(
            cls.public_collection,
            cls.private_collection,
        )

        cls.public_internal_location = (
            Bacteria.objects.create(
                sample_id=(
                    "BAC-PUBLIC-INTERNAL-GEO"
                ),
                sample_type=(
                    "Bacterium (Host)"
                ),
                organism_name=(
                    "Pseudomonas putida KT2440"
                ),
                owner=cls.owner,
                genus="Pseudomonas",
                species=(
                    "Pseudomonas putida"
                ),
                strain="KT2440",
                is_public=True,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.private_sample = (
            Sample.objects.create(
                sample_id=(
                    "PRIVATE-SAMPLE-SENTINEL"
                ),
                sample_type=(
                    "PRIVATE-TYPE-SENTINEL"
                ),
                organism_name=(
                    "PRIVATE-ORGANISM-SENTINEL"
                ),
                owner=cls.owner,
                is_public=False,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.embargoed_sample = (
            Sample.objects.create(
                sample_id=(
                    "EMBARGOED-SAMPLE-SENTINEL"
                ),
                sample_type="Embargoed type",
                organism_name=(
                    "EMBARGOED-ORGANISM-SENTINEL"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=True,
                is_active=True,
            )
        )

        cls.inactive_sample = (
            Sample.objects.create(
                sample_id=(
                    "INACTIVE-SAMPLE-SENTINEL"
                ),
                sample_type="Inactive type",
                organism_name=(
                    "INACTIVE-ORGANISM-SENTINEL"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=False,
            )
        )

        cls.trash_sample = (
            Sample.objects.create(
                sample_id=(
                    "TRASH-SAMPLE-SENTINEL"
                ),
                sample_type="Trash type",
                organism_name=(
                    "TRASH-ORGANISM-SENTINEL"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=True,
                deletion_requested_at=(
                    timezone.now()
                ),
            )
        )

        SampleOrigin.objects.create(
            sample=cls.public_bacterium,
            country_or_ocean="Brazil",
            geo_loc_name=(
                "PRIVATE-GEO-LOC-SENTINEL"
            ),
            collection_site_name=(
                "PRIVATE-COLLECTION-SITE-SENTINEL"
            ),
            latitude="-23.550520",
            longitude="-46.633308",
            location_visibility=(
                SampleOrigin.LOCATION_APPROXIMATE
            ),
        )

        SampleOrigin.objects.create(
            sample=(
                cls.public_internal_location
            ),
            country_or_ocean=(
                "PRIVATE-COUNTRY-SENTINEL"
            ),
            geo_loc_name=(
                "PRIVATE-INTERNAL-GEO-SENTINEL"
            ),
            collection_site_name=(
                "PRIVATE-INTERNAL-SITE-SENTINEL"
            ),
            location_visibility=(
                SampleOrigin.LOCATION_INTERNAL
            ),
        )

        SampleTaxonomyAssignment.objects.create(
            sample=cls.public_bacterium,
            source="ncbi",
            taxon_id="287",
            scientific_name=(
                "Pseudomonas aeruginosa"
            ),
            rank="species",
            domain_or_realm="Bacteria",
            phylum="Pseudomonadota",
            class_name=(
                "Gammaproteobacteria"
            ),
            order_name=(
                "Pseudomonadales"
            ),
            family=(
                "Pseudomonadaceae"
            ),
            genus="Pseudomonas",
            species=(
                "Pseudomonas aeruginosa"
            ),
            match_status=(
                SampleTaxonomyAssignment.STATUS_VERIFIED
            ),
            is_current=True,
            source_release="NCBI-test-release",
        )

        SampleTaxonomyAssignment.objects.create(
            sample=cls.public_bacterium,
            source="gtdb",
            taxon_id="GTDB-CANDIDATE",
            scientific_name=(
                "PRIVATE-CANDIDATE-TAXON-SENTINEL"
            ),
            rank="species",
            match_status=(
                SampleTaxonomyAssignment.STATUS_CANDIDATE
            ),
            is_current=True,
        )


    def test_public_sample_routes_exist(
        self,
    ):
        self.assertEqual(
            reverse(
                "public_samples"
            ),
            "/public/samples/",
        )

        self.assertEqual(
            reverse(
                "public_sample_detail",
                args=[
                    "BAC-PUBLIC-001",
                ],
            ),
            (
                "/public/samples/"
                "BAC-PUBLIC-001/"
            ),
        )


    def test_catalog_queryset_contains_only_public_projection(
        self,
    ):
        ids = set(
            public_sample_catalog_queryset()
            .values_list(
                "sample_id",
                flat=True,
            )
        )

        self.assertEqual(
            ids,
            {
                "BAC-PUBLIC-001",
                "BAC-PUBLIC-INTERNAL-GEO",
            },
        )


    def test_public_sample_list_is_anonymous_and_public_only(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_samples"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "BAC-PUBLIC-001",
        )

        self.assertContains(
            response,
            "BAC-PUBLIC-INTERNAL-GEO",
        )

        for sentinel in (
            "PRIVATE-SAMPLE-SENTINEL",
            "EMBARGOED-SAMPLE-SENTINEL",
            "INACTIVE-SAMPLE-SENTINEL",
            "TRASH-SAMPLE-SENTINEL",
            "PRIVATE-ORGANISM-SENTINEL",
        ):
            self.assertNotContains(
                response,
                sentinel,
            )


    def test_public_sample_search_uses_public_metadata(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_samples"
            ),
            {
                "q": "PA14",
            },
        )

        self.assertContains(
            response,
            "BAC-PUBLIC-001",
        )

        self.assertNotContains(
            response,
            "BAC-PUBLIC-INTERNAL-GEO",
        )


    def test_private_metadata_cannot_drive_public_sample_search(
        self,
    ):
        samples = (
            search_public_samples_queryset(
                "PRIVATE-ORGANISM-SENTINEL"
            )
        )

        self.assertFalse(
            samples.exists()
        )


    def test_public_sample_facets_are_curated_and_public_only(
        self,
    ):
        facets = (
            public_sample_facets()
        )

        self.assertEqual(
            facets[
                "sample_types"
            ],
            [
                "Bacterium (Host)",
            ],
        )

        self.assertEqual(
            facets[
                "genera"
            ],
            [
                "Pseudomonas",
            ],
        )

        self.assertEqual(
            facets[
                "species"
            ],
            [
                "Pseudomonas aeruginosa",
                "Pseudomonas putida",
            ],
        )


    def test_sample_type_genus_and_species_filters_work(
        self,
    ):
        by_type = (
            search_public_samples_queryset(
                "",
                sample_type=(
                    "Bacterium (Host)"
                ),
            )
        )

        by_genus = (
            search_public_samples_queryset(
                "",
                genus="Pseudomonas",
            )
        )

        by_species = (
            search_public_samples_queryset(
                "",
                species=(
                    "Pseudomonas aeruginosa"
                ),
            )
        )

        self.assertEqual(
            by_type.count(),
            2,
        )

        self.assertEqual(
            by_genus.count(),
            2,
        )

        self.assertEqual(
            list(
                by_species.values_list(
                    "sample_id",
                    flat=True,
                )
            ),
            [
                "BAC-PUBLIC-001",
            ],
        )


    def test_public_sample_detail_uses_existing_sample_id(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_sample_detail",
                args=[
                    "BAC-PUBLIC-001",
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "BAC-PUBLIC-001",
        )

        self.assertContains(
            response,
            "Pseudomonas aeruginosa PA14",
        )

        self.assertContains(
            response,
            "Pseudomonas aeruginosa",
        )

        self.assertContains(
            response,
            "PA14",
        )


    def test_non_public_sample_details_fail_closed(
        self,
    ):
        for sample in (
            self.private_sample,
            self.embargoed_sample,
            self.inactive_sample,
            self.trash_sample,
        ):
            response = self.client.get(
                reverse(
                    "public_sample_detail",
                    args=[
                        sample.sample_id,
                    ],
                )
            )

            self.assertEqual(
                response.status_code,
                404,
            )


    def test_detail_exposes_only_public_collection_relationships(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_sample_detail",
                args=[
                    "BAC-PUBLIC-001",
                ],
            )
        )

        self.assertContains(
            response,
            "Published Sample Collection",
        )

        self.assertNotContains(
            response,
            "PRIVATE-COLLECTION-SENTINEL",
        )


    def test_detail_geography_is_country_only(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_sample_detail",
                args=[
                    "BAC-PUBLIC-001",
                ],
            )
        )

        self.assertContains(
            response,
            "Brazil",
        )

        for sentinel in (
            "PRIVATE-GEO-LOC-SENTINEL",
            "PRIVATE-COLLECTION-SITE-SENTINEL",
            "-23.550520",
            "-46.633308",
        ):
            self.assertNotContains(
                response,
                sentinel,
            )


    def test_internal_geography_is_not_public(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_sample_detail",
                args=[
                    (
                        "BAC-PUBLIC-"
                        "INTERNAL-GEO"
                    ),
                ],
            )
        )

        for sentinel in (
            "PRIVATE-COUNTRY-SENTINEL",
            "PRIVATE-INTERNAL-GEO-SENTINEL",
            "PRIVATE-INTERNAL-SITE-SENTINEL",
        ):
            self.assertNotContains(
                response,
                sentinel,
            )


    def test_only_current_verified_external_taxonomy_is_public(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_sample_detail",
                args=[
                    "BAC-PUBLIC-001",
                ],
            )
        )

        self.assertContains(
            response,
            "NCBI",
        )

        self.assertContains(
            response,
            "NCBI-test-release",
        )

        self.assertContains(
            response,
            "Gammaproteobacteria",
        )

        self.assertNotContains(
            response,
            "PRIVATE-CANDIDATE-TAXON-SENTINEL",
        )


    def test_detail_projection_contains_no_sensitive_sample_keys(
        self,
    ):
        sample = (
            public_sample_catalog_queryset()
            .get(
                sample_id="BAC-PUBLIC-001",
            )
        )

        record = (
            public_sample_detail_record(
                sample
            )
        )

        for forbidden in (
            "uuid",
            "micro_qr_token",
            "owner",
            "research_group",
            "storage_location",
            "notes",
            "scientific_notes",
            "status",
        ):
            self.assertNotIn(
                forbidden,
                record,
            )


    def test_public_sample_templates_do_not_traverse_sensitive_fields(
        self,
    ):
        list_template = Path(
            "core/interfaces/public/"
            "samples/list.html"
        ).read_text()

        detail_template = Path(
            "core/interfaces/public/"
            "samples/detail.html"
        ).read_text()

        combined = (
            list_template
            +
            "\n"
            +
            detail_template
        )

        for forbidden in (
            "sample.uuid",
            "sample.micro_qr",
            "sample.owner",
            "sample.research_group",
            "sample.storage",
            "sample.notes",
            "sample.scientific_notes",
            "sample.origin.latitude",
            "sample.origin.longitude",
            "sample.origin.collection_site_name",
            "sample.origin.geo_loc_name",
            "record.uuid",
            "record.owner",
            "record.storage",
            "record.latitude",
            "record.longitude",
            "record.collection_site_name",
            "record.geo_loc_name",
        ):
            self.assertNotIn(
                forbidden,
                combined,
            )


    def test_public_sample_source_does_not_add_public_api(
        self,
    ):
        urls = Path(
            "biobank/urls.py"
        ).read_text()

        self.assertNotIn(
            "public/api/",
            urls,
        )
