import json
import urllib.error
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Bacteria,
    SampleAccessGrant,
    SampleEnrichmentSnapshot,
    SampleExternalIdentifier,
    SampleTaxonomyAssignment,
)
from core.services.sample_enrichment.ncbi_taxonomy import (
    NCBITaxonomyLookupError,
    normalize_ncbi_taxonomy_payload,
    resolve_and_store_ncbi_taxonomy,
    suggest_ncbi_taxonomy_query,
)


def ncbi_taxonomy_payload(
    *,
    tax_id=287,
    scientific_name="Pseudomonas aeruginosa",
):
    return {
        "reports": [
            {
                "query": [
                    scientific_name,
                ],
                "taxonomy": {
                    "tax_id": tax_id,
                    "rank": "SPECIES",
                    "current_scientific_name": {
                        "name": scientific_name,
                        "authority": (
                            "Migula 1894 "
                            "(Approved Lists 1980)"
                        ),
                    },
                    "classification": {
                        "domain": {
                            "id": 2,
                            "name": "Bacteria",
                        },
                        "kingdom": {
                            "id": 3379134,
                            "name": "Pseudomonadati",
                        },
                        "phylum": {
                            "id": 1224,
                            "name": "Pseudomonadota",
                        },
                        "class": {
                            "id": 1236,
                            "name": (
                                "Gammaproteobacteria"
                            ),
                        },
                        "order": {
                            "id": 72274,
                            "name": (
                                "Pseudomonadales"
                            ),
                        },
                        "family": {
                            "id": 135621,
                            "name": (
                                "Pseudomonadaceae"
                            ),
                        },
                        "genus": {
                            "id": 286,
                            "name": "Pseudomonas",
                        },
                        "species": {
                            "id": tax_id,
                            "name": (
                                scientific_name
                            ),
                        },
                    },
                    "parents": [
                        1,
                        131567,
                        2,
                        3379134,
                        1224,
                        1236,
                        72274,
                        135621,
                        286,
                    ],
                    "secondary_tax_ids": [],
                },
            },
        ],
        "total_count": 1,
    }


class FakeResponse:
    def __init__(
        self,
        payload,
        status=200,
    ):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False

    def read(
        self,
        *args,
        **kwargs,
    ):
        return json.dumps(
            self.payload
        ).encode(
            "utf-8"
        )


class SampleExternalEnrichmentTests(
    TestCase
):
    def setUp(self):
        self.owner = (
            User.objects.create_user(
                username=(
                    "enrichment-owner"
                ),
                password="test-password",
            )
        )

        self.viewer = (
            User.objects.create_user(
                username=(
                    "enrichment-viewer"
                ),
                password="test-password",
            )
        )

        self.bacterium = (
            Bacteria.objects.create(
                owner=self.owner,
                sample_id=(
                    "BAC-TEST-ENRICH-0001"
                ),
                sample_type=(
                    "Bacterium (Host)"
                ),
                organism_name=(
                    "Pseudomonas "
                    "aeruginosa PA14"
                ),
                official_name="PA14",
                genus="Pseudomonas",
                species=(
                    "Pseudomonas aeruginosa"
                ),
                strain="PA14",
            )
        )

    @staticmethod
    def client_path(url):
        """
        Convert a reverse() URL containing FORCE_SCRIPT_NAME
        into the internal path expected by Django's test client.
        """
        script_name = str(
            getattr(
                settings,
                "FORCE_SCRIPT_NAME",
                "",
            )
            or ""
        ).rstrip("/")

        if not script_name:
            return url

        if url == script_name:
            return "/"

        if url.startswith(
            script_name + "/"
        ):
            return url[
                len(script_name):
            ]

        return url

    def test_normalizer_uses_real_snake_case_contract(
        self,
    ):
        normalized = (
            normalize_ncbi_taxonomy_payload(
                ncbi_taxonomy_payload()
            )
        )

        self.assertEqual(
            normalized[
                "resolution_status"
            ],
            "resolved",
        )

        self.assertEqual(
            normalized["taxon_id"],
            "287",
        )

        self.assertEqual(
            normalized[
                "scientific_name"
            ],
            "Pseudomonas aeruginosa",
        )

        self.assertEqual(
            normalized["rank"],
            "species",
        )

        self.assertEqual(
            normalized[
                "domain_or_realm"
            ],
            "Bacteria",
        )

        self.assertEqual(
            normalized["phylum"],
            "Pseudomonadota",
        )

        self.assertEqual(
            normalized["class_name"],
            "Gammaproteobacteria",
        )

    def test_bacterial_full_species_query_is_not_duplicated(
        self,
    ):
        self.assertEqual(
            suggest_ncbi_taxonomy_query(
                self.bacterium
            ),
            "Pseudomonas aeruginosa",
        )

    def test_species_epithet_query_receives_genus(
        self,
    ):
        self.bacterium.species = (
            "aeruginosa"
        )

        self.assertEqual(
            suggest_ncbi_taxonomy_query(
                self.bacterium
            ),
            "Pseudomonas aeruginosa",
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_taxonomy.urllib.request.urlopen"
    )
    def test_resolution_stores_snapshot_identifier_and_taxonomy(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = (
            FakeResponse(
                ncbi_taxonomy_payload()
            )
        )

        before = {
            "organism_name": (
                self.bacterium.organism_name
            ),
            "genus": (
                self.bacterium.genus
            ),
            "species": (
                self.bacterium.species
            ),
            "strain": (
                self.bacterium.strain
            ),
        }

        result = (
            resolve_and_store_ncbi_taxonomy(
                self.bacterium,
                self.owner,
                "Pseudomonas aeruginosa",
            )
        )

        self.assertIsNotNone(
            result["assignment"]
        )

        self.assertEqual(
            SampleEnrichmentSnapshot
            .objects
            .count(),
            1,
        )

        self.assertEqual(
            SampleExternalIdentifier
            .objects
            .count(),
            1,
        )

        self.assertEqual(
            SampleTaxonomyAssignment
            .objects
            .count(),
            1,
        )

        identifier = (
            SampleExternalIdentifier
            .objects
            .get()
        )

        self.assertEqual(
            identifier.identifier_type,
            "tax_id",
        )

        self.assertEqual(
            identifier.identifier,
            "287",
        )

        self.assertTrue(
            identifier.is_primary
        )

        assignment = (
            SampleTaxonomyAssignment
            .objects
            .get()
        )

        self.assertEqual(
            assignment.scientific_name,
            "Pseudomonas aeruginosa",
        )

        self.assertEqual(
            assignment.phylum,
            "Pseudomonadota",
        )

        self.assertEqual(
            assignment.match_status,
            (
                SampleTaxonomyAssignment
                .STATUS_CANDIDATE
            ),
        )

        snapshot = (
            SampleEnrichmentSnapshot
            .objects
            .get()
        )

        self.assertTrue(
            snapshot.success
        )

        self.assertEqual(
            len(
                snapshot.checksum_sha256
            ),
            64,
        )

        self.assertNotIn(
            "api_key",
            snapshot.request_url,
        )

        self.bacterium.refresh_from_db()

        after = {
            "organism_name": (
                self.bacterium.organism_name
            ),
            "genus": (
                self.bacterium.genus
            ),
            "species": (
                self.bacterium.species
            ),
            "strain": (
                self.bacterium.strain
            ),
        }

        self.assertEqual(
            after,
            before,
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_taxonomy.urllib.request.urlopen"
    )
    def test_refresh_adds_snapshot_without_duplicate_identity(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = (
            FakeResponse(
                ncbi_taxonomy_payload()
            )
        )

        for _ in range(2):
            resolve_and_store_ncbi_taxonomy(
                self.bacterium,
                self.owner,
                "Pseudomonas aeruginosa",
            )

        self.assertEqual(
            SampleEnrichmentSnapshot
            .objects
            .count(),
            2,
        )

        self.assertEqual(
            SampleExternalIdentifier
            .objects
            .count(),
            1,
        )

        self.assertEqual(
            SampleTaxonomyAssignment
            .objects
            .count(),
            1,
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_taxonomy.urllib.request.urlopen"
    )
    def test_refresh_preserves_verified_human_review(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = FakeResponse(
            ncbi_taxonomy_payload()
        )

        first = resolve_and_store_ncbi_taxonomy(
            self.bacterium,
            self.owner,
            "Pseudomonas aeruginosa",
        )

        assignment = first["assignment"]
        assignment.match_status = (
            SampleTaxonomyAssignment
            .STATUS_VERIFIED
        )
        assignment.reviewed_by = self.owner
        assignment.save(
            update_fields=[
                "match_status",
                "reviewed_by",
            ]
        )

        resolve_and_store_ncbi_taxonomy(
            self.bacterium,
            self.owner,
            "Pseudomonas aeruginosa",
        )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.match_status,
            SampleTaxonomyAssignment
            .STATUS_VERIFIED,
        )
        self.assertEqual(
            assignment.reviewed_by,
            self.owner,
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_taxonomy.urllib.request.urlopen"
    )
    def test_refresh_preserves_conflict_human_review(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = FakeResponse(
            ncbi_taxonomy_payload()
        )

        first = resolve_and_store_ncbi_taxonomy(
            self.bacterium,
            self.owner,
            "Pseudomonas aeruginosa",
        )

        assignment = first["assignment"]
        assignment.match_status = (
            SampleTaxonomyAssignment
            .STATUS_CONFLICT
        )
        assignment.reviewed_by = self.owner
        assignment.save(
            update_fields=[
                "match_status",
                "reviewed_by",
            ]
        )

        resolve_and_store_ncbi_taxonomy(
            self.bacterium,
            self.owner,
            "Pseudomonas aeruginosa",
        )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.match_status,
            SampleTaxonomyAssignment
            .STATUS_CONFLICT,
        )
        self.assertEqual(
            assignment.reviewed_by,
            self.owner,
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_taxonomy.urllib.request.urlopen"
    )
    def test_ambiguous_response_is_snapshotted_without_assignment(
        self,
        mocked_urlopen,
    ):
        payload = (
            ncbi_taxonomy_payload()
        )

        payload["reports"].append(
            ncbi_taxonomy_payload(
                tax_id=286,
                scientific_name=(
                    "Pseudomonas"
                ),
            )["reports"][0]
        )

        payload["total_count"] = 2

        mocked_urlopen.return_value = (
            FakeResponse(payload)
        )

        result = (
            resolve_and_store_ncbi_taxonomy(
                self.bacterium,
                self.owner,
                "Pseudomonas",
            )
        )

        self.assertIsNone(
            result["assignment"]
        )

        self.assertEqual(
            result["normalized"][
                "resolution_status"
            ],
            "ambiguous",
        )

        self.assertEqual(
            SampleEnrichmentSnapshot
            .objects
            .count(),
            1,
        )

        self.assertFalse(
            SampleTaxonomyAssignment
            .objects
            .exists()
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_taxonomy.urllib.request.urlopen"
    )
    def test_network_failure_is_recorded_as_failed_snapshot(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.side_effect = (
            urllib.error.URLError(
                "offline"
            )
        )

        with self.assertRaises(
            NCBITaxonomyLookupError
        ):
            resolve_and_store_ncbi_taxonomy(
                self.bacterium,
                self.owner,
                "Pseudomonas aeruginosa",
            )

        snapshot = (
            SampleEnrichmentSnapshot
            .objects
            .get()
        )

        self.assertFalse(
            snapshot.success
        )

        self.assertIn(
            "Could not reach NCBI",
            snapshot.error_message,
        )

        self.assertFalse(
            SampleTaxonomyAssignment
            .objects
            .exists()
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_taxonomy.urllib.request.urlopen"
    )
    def test_owner_can_resolve_from_sample_detail_action(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = (
            FakeResponse(
                ncbi_taxonomy_payload()
            )
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_ncbi_taxonomy_resolve",
                    args=[
                        self.bacterium.pk,
                    ],
                )
            ),
            {
                "query": (
                    "Pseudomonas aeruginosa"
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            SampleTaxonomyAssignment
            .objects
            .filter(
                sample=self.bacterium,
                taxon_id="287",
            )
            .exists()
        )

    def test_view_only_user_cannot_run_enrichment(
        self,
    ):
        SampleAccessGrant.objects.create(
            sample=self.bacterium,
            user=self.viewer,
            access_level=(
                SampleAccessGrant
                .ACCESS_VIEW
            ),
            granted_by=self.owner,
        )

        self.client.force_login(
            self.viewer
        )

        detail = self.client.get(
            self.client_path(
                reverse(
                    "sample_detail",
                    args=[
                        self.bacterium.pk,
                    ],
                )
            )
        )

        self.assertEqual(
            detail.status_code,
            200,
        )

        self.assertContains(
            detail,
            "External Data",
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_ncbi_taxonomy_resolve",
                    args=[
                        self.bacterium.pk,
                    ],
                )
            ),
            {
                "query": (
                    "Pseudomonas aeruginosa"
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assertFalse(
            SampleEnrichmentSnapshot
            .objects
            .exists()
        )

    def test_owner_detail_exposes_external_data_panel_and_suggestion(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.client_path(
                reverse(
                    "sample_detail",
                    args=[
                        self.bacterium.pk,
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "External Data",
        )

        self.assertContains(
            response,
            "Resolve NCBI Taxonomy",
        )

        self.assertContains(
            response,
            'value="Pseudomonas aeruginosa"',
            html=False,
        )
