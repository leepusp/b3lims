from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Collection,
    Sample,
)
from core.permissions.samples import (
    is_sample_publicly_accessible,
)
from core.services.public_catalog import (
    public_collections_queryset,
    public_samples_queryset,
)


class PublicCatalogSecurityTests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.owner = User.objects.create_user(
            username="public-catalog-owner",
        )

        # -------------------------------------------------
        # COLLECTION PUBLICATION MATRIX
        # -------------------------------------------------

        cls.public_collection = (
            Collection.objects.create(
                name="Public Security Collection",
                description=(
                    "Collection intentionally exposed "
                    "through the public catalog."
                ),
                owner=cls.owner,
                is_public=True,
                is_active=True,
            )
        )

        cls.private_collection = (
            Collection.objects.create(
                name="PRIVATE COLLECTION SENTINEL",
                description=(
                    "This Collection must never appear "
                    "in the unauthenticated catalog."
                ),
                owner=cls.owner,
                is_public=False,
                is_active=True,
            )
        )

        cls.inactive_public_collection = (
            Collection.objects.create(
                name="INACTIVE PUBLIC COLLECTION SENTINEL",
                description=(
                    "Public flag alone must not bypass "
                    "Collection lifecycle state."
                ),
                owner=cls.owner,
                is_public=True,
                is_active=False,
            )
        )

        # -------------------------------------------------
        # SAMPLE PUBLICATION MATRIX
        # -------------------------------------------------

        cls.public_sample = (
            Sample.objects.create(
                sample_id="PUBLIC-SAMPLE-001",
                sample_type="Bacteria",
                organism_name=(
                    "Pseudomonas aeruginosa"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.private_sample = (
            Sample.objects.create(
                sample_id="PRIVATE-SAMPLE-SENTINEL",
                sample_type="Bacteria",
                organism_name=(
                    "PRIVATE ORGANISM SENTINEL"
                ),
                owner=cls.owner,
                is_public=False,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.embargoed_sample = (
            Sample.objects.create(
                sample_id="EMBARGOED-SAMPLE-SENTINEL",
                sample_type="Bacteria",
                organism_name=(
                    "EMBARGOED ORGANISM SENTINEL"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=True,
                is_active=True,
            )
        )

        cls.inactive_sample = (
            Sample.objects.create(
                sample_id="INACTIVE-SAMPLE-SENTINEL",
                sample_type="Bacteria",
                organism_name=(
                    "INACTIVE ORGANISM SENTINEL"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=False,
            )
        )

        cls.trash_sample = (
            Sample.objects.create(
                sample_id="TRASH-SAMPLE-SENTINEL",
                sample_type="Bacteria",
                organism_name=(
                    "TRASH ORGANISM SENTINEL"
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

        # Deliberately place every Sample in one public Collection.
        #
        # Collection publication must NEVER make private,
        # embargoed, inactive or trashed Samples public.
        cls.public_collection.samples.add(
            cls.public_sample,
            cls.private_sample,
            cls.embargoed_sample,
            cls.inactive_sample,
            cls.trash_sample,
        )

        # A private Collection containing a public Sample must remain
        # absent from the public Collection catalog.
        cls.private_collection.samples.add(
            cls.public_sample,
        )

    def test_public_sample_projection_exposes_only_publishable_sample(
        self,
    ):
        public_ids = set(
            public_samples_queryset()
            .values_list(
                "pk",
                flat=True,
            )
        )

        self.assertEqual(
            public_ids,
            {
                self.public_sample.pk,
            },
        )

    def test_public_sample_queryset_matches_object_publication_policy(
        self,
    ):
        projected_ids = set(
            public_samples_queryset()
            .values_list(
                "pk",
                flat=True,
            )
        )

        samples = (
            self.public_sample,
            self.private_sample,
            self.embargoed_sample,
            self.inactive_sample,
            self.trash_sample,
        )

        for sample in samples:
            with self.subTest(
                sample_id=sample.sample_id,
            ):
                self.assertEqual(
                    (
                        sample.pk
                        in projected_ids
                    ),
                    is_sample_publicly_accessible(
                        sample
                    ),
                )

    def test_public_sample_projection_rejects_private_sample(
        self,
    ):
        self.assertFalse(
            public_samples_queryset()
            .filter(
                pk=self.private_sample.pk,
            )
            .exists()
        )

    def test_public_sample_projection_rejects_embargoed_sample(
        self,
    ):
        self.assertFalse(
            public_samples_queryset()
            .filter(
                pk=self.embargoed_sample.pk,
            )
            .exists()
        )

    def test_public_sample_projection_rejects_inactive_sample(
        self,
    ):
        self.assertFalse(
            public_samples_queryset()
            .filter(
                pk=self.inactive_sample.pk,
            )
            .exists()
        )

    def test_public_sample_projection_rejects_trash_sample(
        self,
    ):
        self.assertFalse(
            public_samples_queryset()
            .filter(
                pk=self.trash_sample.pk,
            )
            .exists()
        )

    def test_public_collection_projection_exposes_only_active_public_collection(
        self,
    ):
        public_ids = set(
            public_collections_queryset()
            .values_list(
                "pk",
                flat=True,
            )
        )

        self.assertEqual(
            public_ids,
            {
                self.public_collection.pk,
            },
        )

    def test_public_collection_does_not_expand_sample_publication(
        self,
    ):
        raw_membership_ids = set(
            self.public_collection
            .samples
            .values_list(
                "pk",
                flat=True,
            )
        )

        self.assertEqual(
            raw_membership_ids,
            {
                self.public_sample.pk,
                self.private_sample.pk,
                self.embargoed_sample.pk,
                self.inactive_sample.pk,
                self.trash_sample.pk,
            },
        )

        public_membership_ids = set(
            public_samples_queryset()
            .filter(
                collections=(
                    self.public_collection
                ),
            )
            .values_list(
                "pk",
                flat=True,
            )
        )

        self.assertEqual(
            public_membership_ids,
            {
                self.public_sample.pk,
            },
        )

    def test_public_collection_list_does_not_render_private_or_inactive_collection(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_collections"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            self.public_collection.name,
        )

        self.assertNotContains(
            response,
            self.private_collection.name,
        )

        self.assertNotContains(
            response,
            (
                self.inactive_public_collection
                .name
            ),
        )

    def test_private_collection_detail_is_not_found(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_collection_detail",
                args=[
                    self.private_collection.pk,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_inactive_public_collection_detail_is_not_found(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_collection_detail",
                args=[
                    (
                        self.inactive_public_collection
                        .pk
                    ),
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_public_collection_view_uses_canonical_projection_service(
        self,
    ):
        source = Path(
            "core/views/public/collections.py"
        ).read_text()

        self.assertIn(
            "public_collections_queryset",
            source,
        )

        self.assertNotIn(
            "Collection.objects",
            source,
        )
