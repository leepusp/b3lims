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
    SampleGenomeAssemblyAssignment,
    SampleGenomeAssemblyReview,
)

from core.tests.test_sample_genome_assembly_services import (
    ASSEMBLY,
    FakeResponse,
    genome_payload,
)


class SampleGenomeAssemblyHTTPTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="assembly-http-owner",
            password="test-password",
        )

        self.viewer = User.objects.create_user(
            username="assembly-http-viewer",
            password="test-password",
        )

        self.sample = Bacteria.objects.create(
            owner=self.owner,
            sample_id="BAC-ASSEMBLY-HTTP-001",
            sample_type="Bacterium (Host)",
            organism_name=(
                "Pseudomonas aeruginosa PAO1"
            ),
            official_name="PAO1",
            genus="Pseudomonas",
            species="Pseudomonas aeruginosa",
            strain="PAO1",
        )

    @staticmethod
    def client_path(url):
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

    def resolve_url(self):
        return self.client_path(
            reverse(
                "sample_ncbi_genome_resolve",
                args=[self.sample.pk],
            )
        )

    def review_url(
        self,
        assignment,
        *,
        sample=None,
    ):
        target_sample = (
            sample
            if sample is not None
            else self.sample
        )

        return self.client_path(
            reverse(
                "sample_genome_assembly_review",
                args=[
                    target_sample.pk,
                    assignment.pk,
                ],
            )
        )

    def make_assignment(
        self,
        *,
        is_current=True,
    ):
        snapshot = (
            SampleEnrichmentSnapshot
            .objects
            .create(
                sample=self.sample,
                source="ncbi",
                query=ASSEMBLY,
                request_url=(
                    "https://api.ncbi.nlm.nih.gov/"
                    "datasets/v2/genome/accession/"
                    f"{ASSEMBLY}/dataset_report"
                ),
                source_version="datasets-v2",
                source_record_id=ASSEMBLY,
                http_status=200,
                success=True,
                raw_payload={},
                normalized_payload={},
                checksum_sha256="a" * 64,
                requested_by=self.owner,
            )
        )

        return (
            SampleGenomeAssemblyAssignment
            .objects
            .create(
                sample=self.sample,
                source="ncbi",
                accession=ASSEMBLY,
                current_accession=ASSEMBLY,
                organism_name=(
                    "Pseudomonas aeruginosa PAO1"
                ),
                taxon_id="208964",
                assembly_name="ASM676v1",
                assembly_level="Complete Genome",
                match_status="candidate",
                is_current=is_current,
                snapshot=snapshot,
            )
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_genome.urllib.request.urlopen"
    )
    def test_owner_can_resolve_genome_assembly_via_http(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.return_value = (
            FakeResponse(
                genome_payload()
            )
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.resolve_url(),
            {
                "accession": ASSEMBLY,
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        assignment = (
            SampleGenomeAssemblyAssignment
            .objects
            .get()
        )

        self.assertEqual(
            assignment.sample_id,
            self.sample.pk,
        )

        self.assertEqual(
            assignment.accession,
            ASSEMBLY,
        )

        self.assertEqual(
            assignment.match_status,
            "candidate",
        )

        self.assertTrue(
            assignment.is_current
        )

        snapshot = (
            SampleEnrichmentSnapshot
            .objects
            .get()
        )

        self.assertTrue(
            snapshot.success
        )

    @patch(
        "core.services.sample_enrichment."
        "ncbi_genome.urllib.request.urlopen"
    )
    def test_blank_and_invalid_accession_do_not_call_ncbi(
        self,
        mocked_urlopen,
    ):
        self.client.force_login(
            self.owner
        )

        for accession in [
            "",
            "Pseudomonas aeruginosa",
            "GCF_000006765",
        ]:
            with self.subTest(
                accession=accession
            ):
                response = self.client.post(
                    self.resolve_url(),
                    {
                        "accession": accession,
                    },
                )

                self.assertEqual(
                    response.status_code,
                    302,
                )

        mocked_urlopen.assert_not_called()

        self.assertFalse(
            SampleEnrichmentSnapshot
            .objects
            .exists()
        )

        self.assertFalse(
            SampleGenomeAssemblyAssignment
            .objects
            .exists()
        )

    def test_view_only_user_cannot_resolve_genome_assembly(
        self,
    ):
        SampleAccessGrant.objects.create(
            sample=self.sample,
            user=self.viewer,
            access_level=(
                SampleAccessGrant.ACCESS_VIEW
            ),
            granted_by=self.owner,
        )

        self.client.force_login(
            self.viewer
        )

        response = self.client.post(
            self.resolve_url(),
            {
                "accession": ASSEMBLY,
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

    @patch(
        "core.services.sample_enrichment."
        "ncbi_genome.urllib.request.urlopen"
    )
    def test_network_failure_records_failed_snapshot_via_http(
        self,
        mocked_urlopen,
    ):
        mocked_urlopen.side_effect = (
            urllib.error.URLError(
                "offline"
            )
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.resolve_url(),
            {
                "accession": ASSEMBLY,
            },
        )

        self.assertEqual(
            response.status_code,
            302,
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
            "offline",
            snapshot.error_message,
        )

        self.assertFalse(
            SampleGenomeAssemblyAssignment
            .objects
            .exists()
        )

    def test_owner_can_verify_genome_assembly_via_http(
        self,
    ):
        assignment = (
            self.make_assignment()
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.review_url(
                assignment
            ),
            {
                "status": "verified",
                "note": (
                    "Assembly accession confirmed."
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.match_status,
            "verified",
        )

        self.assertEqual(
            assignment.reviewed_by,
            self.owner,
        )

        self.assertIsNotNone(
            assignment.reviewed_at
        )

        self.assertEqual(
            SampleGenomeAssemblyReview
            .objects
            .count(),
            1,
        )

    def test_conflict_without_note_is_rejected_via_http(
        self,
    ):
        assignment = (
            self.make_assignment()
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.review_url(
                assignment
            ),
            {
                "status": "conflict",
                "note": "",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.match_status,
            "candidate",
        )

        self.assertFalse(
            assignment.reviews.exists()
        )

    def test_view_only_user_cannot_review_genome_assembly(
        self,
    ):
        assignment = (
            self.make_assignment()
        )

        SampleAccessGrant.objects.create(
            sample=self.sample,
            user=self.viewer,
            access_level=(
                SampleAccessGrant.ACCESS_VIEW
            ),
            granted_by=self.owner,
        )

        self.client.force_login(
            self.viewer
        )

        response = self.client.post(
            self.review_url(
                assignment
            ),
            {
                "status": "verified",
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.match_status,
            "candidate",
        )

        self.assertFalse(
            assignment.reviews.exists()
        )

    def test_other_sample_cannot_address_assignment(
        self,
    ):
        assignment = (
            self.make_assignment()
        )

        other = Bacteria.objects.create(
            owner=self.owner,
            sample_id=(
                "BAC-ASSEMBLY-HTTP-OTHER"
            ),
            sample_type="Bacterium (Host)",
            organism_name="Escherichia coli K-12",
            official_name="K-12",
            genus="Escherichia",
            species="Escherichia coli",
            strain="K-12",
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.review_url(
                assignment,
                sample=other,
            ),
            {
                "status": "verified",
            },
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.match_status,
            "candidate",
        )

        self.assertFalse(
            assignment.reviews.exists()
        )

    def test_noncurrent_assignment_cannot_be_reviewed(
        self,
    ):
        assignment = (
            self.make_assignment(
                is_current=False
            )
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.review_url(
                assignment
            ),
            {
                "status": "verified",
            },
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        assignment.refresh_from_db()

        self.assertEqual(
            assignment.match_status,
            "candidate",
        )

        self.assertFalse(
            assignment.reviews.exists()
        )

    def test_owner_detail_renders_genome_assembly_review_history(
        self,
    ):
        assignment = (
            self.make_assignment()
        )

        self.client.force_login(
            self.owner
        )

        review_response = self.client.post(
            self.review_url(
                assignment
            ),
            {
                "status": "verified",
                "note": (
                    "Confirmed assembly for UI."
                ),
            },
        )

        self.assertEqual(
            review_response.status_code,
            302,
        )

        detail_url = self.client_path(
            reverse(
                "sample_detail",
                args=[self.sample.pk],
            )
        )

        response = self.client.get(
            detail_url
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Genome Assemblies",
        )
        self.assertContains(
            response,
            ASSEMBLY,
        )
        self.assertContains(
            response,
            "ASM676v1",
        )
        self.assertContains(
            response,
            "Complete Genome",
        )
        self.assertContains(
            response,
            "Verified",
        )
        self.assertContains(
            response,
            "Review Genome Assembly",
        )
        self.assertContains(
            response,
            "Review History",
        )
        self.assertContains(
            response,
            "Candidate",
        )
        self.assertContains(
            response,
            "Confirmed assembly for UI.",
        )
        self.assertContains(
            response,
            "Resolve NCBI Genome Assembly",
        )
        self.assertContains(
            response,
            "GCF_000006765.1 or GCA_000006765.1",
        )
        self.assertContains(
            response,
            (
                "External Genome Assembly metadata "
                "does not"
            ),
        )

    def test_view_only_detail_hides_genome_write_controls(
        self,
    ):
        assignment = (
            self.make_assignment()
        )

        SampleAccessGrant.objects.create(
            sample=self.sample,
            user=self.viewer,
            access_level=(
                SampleAccessGrant.ACCESS_VIEW
            ),
            granted_by=self.owner,
        )

        self.client.force_login(
            self.viewer
        )

        detail_url = self.client_path(
            reverse(
                "sample_detail",
                args=[self.sample.pk],
            )
        )

        response = self.client.get(
            detail_url
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Genome Assemblies",
        )
        self.assertContains(
            response,
            assignment.accession,
        )
        self.assertContains(
            response,
            "ASM676v1",
        )

        self.assertNotContains(
            response,
            "Resolve NCBI Genome Assembly",
        )
        self.assertNotContains(
            response,
            "Review Genome Assembly",
        )

        resolve_url = reverse(
            "sample_ncbi_genome_resolve",
            args=[self.sample.pk],
        )

        review_url = reverse(
            "sample_genome_assembly_review",
            args=[
                self.sample.pk,
                assignment.pk,
            ],
        )

        self.assertNotContains(
            response,
            resolve_url,
        )

        self.assertNotContains(
            response,
            review_url,
        )

    def test_owner_detail_renders_empty_genome_state_and_resolver(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        detail_url = self.client_path(
            reverse(
                "sample_detail",
                args=[self.sample.pk],
            )
        )

        response = self.client.get(
            detail_url
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Genome Assemblies",
        )
        self.assertContains(
            response,
            (
                "No external Genome Assembly assignment "
                "has been"
            ),
        )
        self.assertContains(
            response,
            "recorded for this Sample.",
        )
        self.assertContains(
            response,
            "Resolve NCBI Genome Assembly",
        )
        self.assertContains(
            response,
            'name="accession"',
            html=False,
        )
        self.assertContains(
            response,
            "Versioned NCBI Genome Assembly accession",
        )
        self.assertContains(
            response,
            "The Biobank does not infer an",
        )
        self.assertContains(
            response,
            "Assembly from species or strain",
        )
