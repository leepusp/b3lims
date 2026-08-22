import json
import urllib.error
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.models import (
    Bacteria,
    SampleEnrichmentSnapshot,
    SampleExternalIdentifier,
    SampleGenomeAssemblyAssignment,
    SampleGenomeAssemblyReview,
)
from core.services.sample_enrichment import (
    NCBIGenomeLookupError,
    normalize_assembly_accession,
    normalize_ncbi_genome_payload,
    resolve_and_store_ncbi_genome_assembly,
    review_genome_assembly_assignment,
)


ASSEMBLY = "GCF_000006765.1"
PAIRED = "GCA_000006765.1"


def genome_payload(
    *,
    biosample=True,
):
    assembly_info = {
        "assembly_name": "ASM676v1",
        "assembly_level": "Complete Genome",
        "assembly_status": "current",
        "assembly_type": "haploid",
        "refseq_category": "reference genome",
        "release_date": "2004-05-25",
        "submitter": "Pseudomonas Genome Project",
        "bioproject_accession": "PRJNA331",
    }

    if biosample:
        assembly_info[
            "biosample_accession"
        ] = "SAMN02603714"

    return {
        "reports": [
            {
                "accession": ASSEMBLY,
                "current_accession": ASSEMBLY,
                "paired_accession": PAIRED,
                "source_database": (
                    "SOURCE_DATABASE_REFSEQ"
                ),
                "organism": {
                    "organism_name": (
                        "Pseudomonas aeruginosa PAO1"
                    ),
                    "tax_id": 208964,
                },
                "assembly_info": assembly_info,
                "assembly_stats": {
                    "total_sequence_length": 6264404,
                    "number_of_contigs": 1,
                    "number_of_scaffolds": 1,
                    "contig_n50": 6264404,
                    "scaffold_n50": 6264404,
                    "gc_percent": 66.56,
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
        ).encode("utf-8")


class SampleGenomeAssemblyServiceTests(
    TestCase
):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="assembly-owner",
            password="test-password",
        )

        self.sample = Bacteria.objects.create(
            owner=self.owner,
            sample_id="BAC-ASSEMBLY-TEST-001",
            sample_type="Bacterium (Host)",
            organism_name=(
                "Pseudomonas aeruginosa PAO1"
            ),
            official_name="PAO1",
            genus="Pseudomonas",
            species="Pseudomonas aeruginosa",
            strain="PAO1",
        )

    def resolve(self):
        return (
            resolve_and_store_ncbi_genome_assembly(
                self.sample,
                self.owner,
                ASSEMBLY,
            )
        )

    def test_accession_requires_versioned_gcf_or_gca(
        self,
    ):
        self.assertEqual(
            normalize_assembly_accession(
                "gcf_000006765.1"
            ),
            ASSEMBLY,
        )

        self.assertEqual(
            normalize_assembly_accession(
                "gca_000006765.1"
            ),
            PAIRED,
        )

        for invalid in [
            "",
            "Pseudomonas aeruginosa",
            "GCF_000006765",
            "GCF_123.1",
            "SAMN02603714",
        ]:
            with self.subTest(
                invalid=invalid
            ):
                with self.assertRaises(
                    ValueError
                ):
                    normalize_assembly_accession(
                        invalid
                    )

        self.assertFalse(
            SampleEnrichmentSnapshot
            .objects
            .exists()
        )

    def test_normalizer_maps_ncbi_genome_contract(
        self,
    ):
        result = (
            normalize_ncbi_genome_payload(
                genome_payload()
            )
        )

        self.assertEqual(
            result["resolution_status"],
            "resolved",
        )
        self.assertEqual(
            result["accession"],
            ASSEMBLY,
        )
        self.assertEqual(
            result["paired_accession"],
            PAIRED,
        )
        self.assertEqual(
            result["taxon_id"],
            "208964",
        )
        self.assertEqual(
            result["bioproject_accession"],
            "PRJNA331",
        )
        self.assertEqual(
            result["biosample_accession"],
            "SAMN02603714",
        )
        self.assertEqual(
            result["total_sequence_length"],
            6264404,
        )
        self.assertAlmostEqual(
            result["gc_percent"],
            66.56,
        )

    def test_biosample_is_optional(
        self,
    ):
        result = (
            normalize_ncbi_genome_payload(
                genome_payload(
                    biosample=False
                )
            )
        )

        self.assertEqual(
            result["resolution_status"],
            "resolved",
        )
        self.assertEqual(
            result["biosample_accession"],
            "",
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_genome.urllib.request.urlopen"
    )
    def test_resolution_persists_evidence_without_curated_overwrite(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = (
            FakeResponse(
                genome_payload()
            )
        )

        before = {
            "organism_name":
                self.sample.organism_name,
            "genus":
                self.sample.genus,
            "species":
                self.sample.species,
            "strain":
                self.sample.strain,
        }

        result = self.resolve()
        assignment = result["assignment"]

        self.assertEqual(
            assignment.accession,
            ASSEMBLY,
        )
        self.assertEqual(
            assignment.match_status,
            "candidate",
        )
        self.assertEqual(
            assignment.assembly_level,
            "Complete Genome",
        )
        self.assertEqual(
            assignment.bioproject_accession,
            "PRJNA331",
        )
        self.assertEqual(
            assignment.biosample_accession,
            "SAMN02603714",
        )

        self.assertEqual(
            SampleEnrichmentSnapshot
            .objects
            .count(),
            1,
        )
        self.assertEqual(
            SampleGenomeAssemblyAssignment
            .objects
            .count(),
            1,
        )

        identifiers = {
            (
                row.identifier_type,
                row.identifier,
            ): row.is_primary
            for row in (
                SampleExternalIdentifier
                .objects
                .all()
            )
        }

        self.assertTrue(
            identifiers[
                (
                    "assembly_accession",
                    ASSEMBLY,
                )
            ]
        )

        self.assertIn(
            (
                "paired_assembly_accession",
                PAIRED,
            ),
            identifiers,
        )
        self.assertIn(
            (
                "bioproject",
                "PRJNA331",
            ),
            identifiers,
        )
        self.assertIn(
            (
                "biosample",
                "SAMN02603714",
            ),
            identifiers,
        )

        snapshot = (
            SampleEnrichmentSnapshot
            .objects
            .get()
        )

        self.assertTrue(snapshot.success)
        self.assertEqual(
            snapshot.source_record_id,
            ASSEMBLY,
        )
        self.assertNotIn(
            "api_key",
            snapshot.request_url,
        )

        self.sample.refresh_from_db()

        after = {
            "organism_name":
                self.sample.organism_name,
            "genus":
                self.sample.genus,
            "species":
                self.sample.species,
            "strain":
                self.sample.strain,
        }

        self.assertEqual(
            after,
            before,
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_genome.urllib.request.urlopen"
    )
    def test_refresh_is_idempotent_except_snapshot(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = (
            FakeResponse(
                genome_payload()
            )
        )

        self.resolve()
        self.resolve()

        self.assertEqual(
            SampleEnrichmentSnapshot
            .objects
            .count(),
            2,
        )
        self.assertEqual(
            SampleGenomeAssemblyAssignment
            .objects
            .count(),
            1,
        )
        self.assertEqual(
            SampleExternalIdentifier
            .objects
            .count(),
            4,
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_genome.urllib.request.urlopen"
    )
    def test_refresh_preserves_verified_review(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = (
            FakeResponse(
                genome_payload()
            )
        )

        assignment = (
            self.resolve()["assignment"]
        )

        review_genome_assembly_assignment(
            assignment=assignment,
            reviewer=self.owner,
            new_status="verified",
        )

        self.resolve()

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.match_status,
            "verified",
        )
        self.assertEqual(
            assignment.reviewed_by,
            self.owner,
        )
        self.assertEqual(
            assignment.reviews.count(),
            1,
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_genome.urllib.request.urlopen"
    )
    def test_refresh_preserves_conflict_review(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = (
            FakeResponse(
                genome_payload()
            )
        )

        assignment = (
            self.resolve()["assignment"]
        )

        review_genome_assembly_assignment(
            assignment=assignment,
            reviewer=self.owner,
            new_status="conflict",
            note=(
                "Assembly conflicts with "
                "curated strain."
            ),
        )

        self.resolve()

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.match_status,
            "conflict",
        )
        self.assertEqual(
            assignment.reviews.count(),
            1,
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_genome.urllib.request.urlopen"
    )
    def test_network_failure_records_failed_snapshot(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.side_effect = (
            urllib.error.URLError(
                "offline"
            )
        )

        with self.assertRaises(
            NCBIGenomeLookupError
        ):
            self.resolve()

        snapshot = (
            SampleEnrichmentSnapshot
            .objects
            .get()
        )

        self.assertFalse(
            snapshot.success
        )
        self.assertEqual(
            snapshot.query,
            ASSEMBLY,
        )
        self.assertIn(
            "offline",
            snapshot.error_message,
        )
        self.assertFalse(
            SampleGenomeAssemblyAssignment
            .objects
            .exists()
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_genome.urllib.request.urlopen"
    )
    def test_review_validation_and_history(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = (
            FakeResponse(
                genome_payload()
            )
        )

        assignment = (
            self.resolve()["assignment"]
        )

        with self.assertRaises(
            ValidationError
        ):
            review_genome_assembly_assignment(
                assignment=assignment,
                reviewer=self.owner,
                new_status="conflict",
                note="",
            )

        self.assertFalse(
            assignment.reviews.exists()
        )

        first = (
            review_genome_assembly_assignment(
                assignment=assignment,
                reviewer=self.owner,
                new_status="conflict",
                note="Initial conflict.",
            )
        )

        assignment.refresh_from_db()

        second = (
            review_genome_assembly_assignment(
                assignment=assignment,
                reviewer=self.owner,
                new_status="verified",
                note="Conflict resolved.",
            )
        )

        assignment.refresh_from_db()

        reviews = list(
            assignment.reviews
            .order_by("pk")
        )

        self.assertEqual(
            assignment.match_status,
            "verified",
        )
        self.assertEqual(
            len(reviews),
            2,
        )
        self.assertEqual(
            (
                first.previous_status,
                first.new_status,
            ),
            (
                "candidate",
                "conflict",
            ),
        )
        self.assertEqual(
            (
                second.previous_status,
                second.new_status,
            ),
            (
                "conflict",
                "verified",
            ),
        )

        self.assertEqual(
            SampleGenomeAssemblyReview
            .objects
            .count(),
            2,
        )

        with self.assertRaises(
            ValidationError
        ):
            review_genome_assembly_assignment(
                assignment=assignment,
                reviewer=self.owner,
                new_status="verified",
            )

        self.assertEqual(
            SampleGenomeAssemblyReview
            .objects
            .count(),
            2,
        )
