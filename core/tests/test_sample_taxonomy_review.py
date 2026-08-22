from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Bacteria,
    SampleAccessGrant,
    SampleEnrichmentSnapshot,
    SampleTaxonomyAssignment,
    SampleTaxonomyReview,
)
from core.services.sample_enrichment.taxonomy_review import (
    review_taxonomy_assignment,
)


class SampleTaxonomyReviewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="taxonomy-review-owner",
            password="test-password",
        )

        self.viewer = User.objects.create_user(
            username="taxonomy-review-viewer",
            password="test-password",
        )

        self.sample = Bacteria.objects.create(
            owner=self.owner,
            sample_id="BAC-TAX-REVIEW-001",
            sample_type="Bacterium (Host)",
            organism_name="Pseudomonas aeruginosa PA14",
            official_name="PA14",
            genus="Pseudomonas",
            species="Pseudomonas aeruginosa",
            strain="PA14",
        )

        self.snapshot = (
            SampleEnrichmentSnapshot.objects.create(
                sample=self.sample,
                source="ncbi",
                query="Pseudomonas aeruginosa",
                request_url=(
                    "https://api.ncbi.nlm.nih.gov/"
                    "datasets/v2/taxonomy/taxon/"
                    "Pseudomonas%20aeruginosa/"
                    "dataset_report"
                ),
                source_version="datasets-v2",
                source_record_id="287",
                http_status=200,
                success=True,
                raw_payload={},
                normalized_payload={},
                checksum_sha256="a" * 64,
                requested_by=self.owner,
            )
        )

        self.assignment = (
            SampleTaxonomyAssignment.objects.create(
                sample=self.sample,
                source="ncbi",
                taxon_id="287",
                scientific_name=(
                    "Pseudomonas aeruginosa"
                ),
                rank="species",
                domain_or_realm="Bacteria",
                genus="Pseudomonas",
                species=(
                    "Pseudomonas aeruginosa"
                ),
                match_status="candidate",
                is_current=True,
                snapshot=self.snapshot,
            )
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

    def review_url(self):
        return self.client_path(
            reverse(
                "sample_taxonomy_review",
                args=[
                    self.sample.pk,
                    self.assignment.pk,
                ],
            )
        )

    def test_verify_creates_review_history(
        self,
    ):
        review = review_taxonomy_assignment(
            assignment=self.assignment,
            reviewer=self.owner,
            new_status="verified",
            note="Confirmed against NCBI taxonomy.",
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.match_status,
            "verified",
        )
        self.assertEqual(
            self.assignment.reviewed_by,
            self.owner,
        )
        self.assertIsNotNone(
            self.assignment.reviewed_at
        )

        self.assertEqual(
            review.previous_status,
            "candidate",
        )
        self.assertEqual(
            review.new_status,
            "verified",
        )
        self.assertEqual(
            review.reviewer,
            self.owner,
        )

        self.assertEqual(
            SampleTaxonomyReview.objects.count(),
            1,
        )

    def test_conflict_requires_note(
        self,
    ):
        with self.assertRaises(
            ValidationError
        ):
            review_taxonomy_assignment(
                assignment=self.assignment,
                reviewer=self.owner,
                new_status="conflict",
                note="",
            )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.match_status,
            "candidate",
        )
        self.assertFalse(
            SampleTaxonomyReview.objects.exists()
        )

    def test_conflict_with_note_is_recorded(
        self,
    ):
        review = review_taxonomy_assignment(
            assignment=self.assignment,
            reviewer=self.owner,
            new_status="conflict",
            note=(
                "Curated metadata conflicts "
                "with the proposed assignment."
            ),
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.match_status,
            "conflict",
        )
        self.assertEqual(
            review.previous_status,
            "candidate",
        )
        self.assertEqual(
            review.new_status,
            "conflict",
        )
        self.assertTrue(review.note)

    def test_re_review_preserves_history(
        self,
    ):
        review_taxonomy_assignment(
            assignment=self.assignment,
            reviewer=self.owner,
            new_status="conflict",
            note="Initial conflict.",
        )

        self.assignment.refresh_from_db()

        review_taxonomy_assignment(
            assignment=self.assignment,
            reviewer=self.owner,
            new_status="verified",
            note="Conflict resolved after review.",
        )

        self.assignment.refresh_from_db()

        reviews = list(
            self.assignment.reviews.order_by("pk")
        )

        self.assertEqual(
            self.assignment.match_status,
            "verified",
        )
        self.assertEqual(
            len(reviews),
            2,
        )
        self.assertEqual(
            reviews[0].previous_status,
            "candidate",
        )
        self.assertEqual(
            reviews[0].new_status,
            "conflict",
        )
        self.assertEqual(
            reviews[1].previous_status,
            "conflict",
        )
        self.assertEqual(
            reviews[1].new_status,
            "verified",
        )

    def test_duplicate_status_is_rejected(
        self,
    ):
        review_taxonomy_assignment(
            assignment=self.assignment,
            reviewer=self.owner,
            new_status="verified",
        )

        self.assignment.refresh_from_db()

        with self.assertRaises(
            ValidationError
        ):
            review_taxonomy_assignment(
                assignment=self.assignment,
                reviewer=self.owner,
                new_status="verified",
            )

        self.assertEqual(
            SampleTaxonomyReview.objects.count(),
            1,
        )

    def test_invalid_status_is_rejected(
        self,
    ):
        with self.assertRaises(
            ValidationError
        ):
            review_taxonomy_assignment(
                assignment=self.assignment,
                reviewer=self.owner,
                new_status="stale",
            )

    def test_owner_can_review_via_http(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.review_url(),
            {
                "status": "verified",
                "note": "Reviewed by owner.",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.match_status,
            "verified",
        )
        self.assertEqual(
            self.assignment.reviews.count(),
            1,
        )

    def test_view_only_user_cannot_review(
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
            self.review_url(),
            {
                "status": "verified",
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assignment.refresh_from_db()

        self.assertEqual(
            self.assignment.match_status,
            "candidate",
        )
        self.assertFalse(
            self.assignment.reviews.exists()
        )

    def test_other_sample_cannot_address_assignment(
        self,
    ):
        other = Bacteria.objects.create(
            owner=self.owner,
            sample_id="BAC-TAX-REVIEW-OTHER",
            sample_type="Bacterium (Host)",
            organism_name="Escherichia coli",
            official_name="E. coli",
            genus="Escherichia",
            species="Escherichia coli",
            strain="K-12",
        )

        self.client.force_login(
            self.owner
        )

        url = self.client_path(
            reverse(
                "sample_taxonomy_review",
                args=[
                    other.pk,
                    self.assignment.pk,
                ],
            )
        )

        response = self.client.post(
            url,
            {
                "status": "verified",
            },
        )

        self.assertEqual(
            response.status_code,
            404,
        )

        self.assertFalse(
            self.assignment.reviews.exists()
        )

    def test_detail_renders_review_history(
        self,
    ):
        review_taxonomy_assignment(
            assignment=self.assignment,
            reviewer=self.owner,
            new_status="verified",
            note="Confirmed taxonomy.",
        )

        self.client.force_login(
            self.owner
        )

        detail = self.client.get(
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
            detail.status_code,
            200,
        )
        self.assertContains(
            detail,
            "Review Taxonomy",
        )
        self.assertContains(
            detail,
            "Review History",
        )
        self.assertContains(
            detail,
            "Candidate",
        )
        self.assertContains(
            detail,
            "Verified",
        )
        self.assertContains(
            detail,
            "Confirmed taxonomy.",
        )
