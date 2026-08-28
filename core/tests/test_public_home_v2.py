from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    Sample,
    SampleOrigin,
    Tag,
)
from core.services.public_catalog import (
    featured_public_collections,
    public_home_context,
    public_home_metrics,
    public_sample_type_distribution,
)


class PublicHomeV2Tests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.owner = User.objects.create_user(
            username=(
                "PRIVATE-HOME-OWNER-SENTINEL"
            ),
        )

        cls.public_collection = (
            Collection.objects.create(
                name=(
                    "Public Home Collection"
                ),
                description=(
                    "Publication-approved Collection "
                    "for the dynamic Home."
                ),
                owner=cls.owner,
                is_public=True,
                is_active=True,
            )
        )

        cls.private_collection = (
            Collection.objects.create(
                name=(
                    "PRIVATE-HOME-COLLECTION-SENTINEL"
                ),
                owner=cls.owner,
                is_public=False,
                is_active=True,
            )
        )

        cls.active_tag = Tag.objects.create(
            name="PUBLIC-HOME-TAG",
            is_active=True,
        )

        cls.inactive_tag = Tag.objects.create(
            name="INACTIVE-HOME-TAG-SENTINEL",
            is_active=False,
        )

        cls.public_collection.tags.add(
            cls.active_tag,
            cls.inactive_tag,
        )

        cls.bacteria = (
            Sample.objects.create(
                sample_id="HOME-PUBLIC-001",
                sample_type="Bacteria",
                organism_name=(
                    "Pseudomonas publicensis"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.phage = (
            Sample.objects.create(
                sample_id="HOME-PUBLIC-002",
                sample_type="Bacteriophage",
                organism_name=(
                    "Public phage alpha"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.construct = (
            Sample.objects.create(
                sample_id="HOME-PUBLIC-003",
                sample_type=(
                    "Vector / Construct"
                ),
                organism_name="",
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.private_sample = (
            Sample.objects.create(
                sample_id=(
                    "PRIVATE-HOME-SAMPLE-SENTINEL"
                ),
                sample_type=(
                    "PRIVATE-HOME-TYPE-SENTINEL"
                ),
                organism_name=(
                    "PRIVATE-HOME-ORGANISM-SENTINEL"
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
                    "EMBARGOED-HOME-SAMPLE-SENTINEL"
                ),
                sample_type=(
                    "EMBARGOED-HOME-TYPE-SENTINEL"
                ),
                organism_name=(
                    "EMBARGOED-HOME-ORGANISM-SENTINEL"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=True,
                is_active=True,
            )
        )

        cls.public_collection.samples.add(
            cls.bacteria,
            cls.phage,
            cls.construct,
            cls.private_sample,
            cls.embargoed_sample,
        )

        cls.private_collection.samples.add(
            cls.bacteria,
        )

        SampleOrigin.objects.create(
            sample=cls.bacteria,
            country_or_ocean="Brazil",
            location_visibility=(
                SampleOrigin
                .LOCATION_APPROXIMATE
            ),
        )

        SampleOrigin.objects.create(
            sample=cls.phage,
            country_or_ocean=(
                "Atlantic Ocean"
            ),
            location_visibility=(
                SampleOrigin
                .LOCATION_EXACT
            ),
        )

        SampleOrigin.objects.create(
            sample=cls.construct,
            country_or_ocean=(
                "PRIVATE-INTERNAL-ORIGIN-SENTINEL"
            ),
            location_visibility=(
                SampleOrigin
                .LOCATION_INTERNAL
            ),
        )

        SampleOrigin.objects.create(
            sample=cls.private_sample,
            country_or_ocean=(
                "PRIVATE-SAMPLE-ORIGIN-SENTINEL"
            ),
            location_visibility=(
                SampleOrigin
                .LOCATION_EXACT
            ),
        )

    def test_public_home_metrics_use_only_public_projection(
        self,
    ):
        metrics = (
            public_home_metrics()
        )

        self.assertEqual(
            metrics,
            {
                "public_samples": 3,
                "public_collections": 1,
                "organisms": 2,
                "geographic_origins": 2,
            },
        )

    def test_internal_origin_does_not_contribute_to_public_geography(
        self,
    ):
        metrics = (
            public_home_metrics()
        )

        self.assertEqual(
            metrics[
                "geographic_origins"
            ],
            2,
        )

    def test_private_sample_origin_does_not_contribute_to_public_geography(
        self,
    ):
        metrics = (
            public_home_metrics()
        )

        self.assertEqual(
            metrics[
                "geographic_origins"
            ],
            2,
        )

    def test_sample_type_distribution_excludes_private_and_embargoed_samples(
        self,
    ):
        rows = (
            public_sample_type_distribution()
        )

        types = {
            row["sample_type"]
            for row in rows
        }

        self.assertEqual(
            types,
            {
                "Bacteria",
                "Bacteriophage",
                "Vector / Construct",
            },
        )

        self.assertNotIn(
            "PRIVATE-HOME-TYPE-SENTINEL",
            types,
        )

        self.assertNotIn(
            "EMBARGOED-HOME-TYPE-SENTINEL",
            types,
        )

        self.assertEqual(
            sum(
                row["total"]
                for row in rows
            ),
            3,
        )

    def test_featured_collection_count_uses_public_samples_only(
        self,
    ):
        collections = (
            featured_public_collections()
        )

        self.assertEqual(
            len(
                collections
            ),
            1,
        )

        collection = (
            collections[0]
        )

        self.assertEqual(
            collection.pk,
            self.public_collection.pk,
        )

        self.assertEqual(
            collection.public_sample_count,
            3,
        )

        self.assertEqual(
            collection.samples.count(),
            5,
        )

    def test_featured_collection_exposes_active_tag_only(
        self,
    ):
        collection = (
            featured_public_collections()[0]
        )

        self.assertEqual(
            [
                tag.name
                for tag in (
                    collection.public_tags
                )
            ],
            [
                "PUBLIC-HOME-TAG",
            ],
        )

    def test_private_collection_is_not_featured(
        self,
    ):
        ids = {
            collection.pk
            for collection in (
                featured_public_collections()
            )
        }

        self.assertNotIn(
            self.private_collection.pk,
            ids,
        )

    def test_public_home_context_contains_only_public_analytics(
        self,
    ):
        context = (
            public_home_context()
        )

        self.assertEqual(
            context[
                "public_metrics"
            ][
                "public_samples"
            ],
            3,
        )

        self.assertEqual(
            context[
                "featured_collections"
            ][0]
            .public_sample_count,
            3,
        )

    def test_public_home_response_renders_dynamic_public_metrics(
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

        self.assertEqual(
            response.context[
                "public_metrics"
            ][
                "public_samples"
            ],
            3,
        )

        self.assertEqual(
            response.context[
                "public_metrics"
            ][
                "public_collections"
            ],
            1,
        )

        self.assertContains(
            response,
            "Catalog at a glance",
        )

        self.assertContains(
            response,
            "Public catalog by Sample type",
        )

        self.assertContains(
            response,
            "Featured public Collections",
        )

    def test_public_home_does_not_render_private_sample_metadata(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_home"
            )
        )

        for sentinel in (
            "PRIVATE-HOME-SAMPLE-SENTINEL",
            "PRIVATE-HOME-TYPE-SENTINEL",
            "PRIVATE-HOME-ORGANISM-SENTINEL",
            "EMBARGOED-HOME-SAMPLE-SENTINEL",
            "EMBARGOED-HOME-TYPE-SENTINEL",
            "EMBARGOED-HOME-ORGANISM-SENTINEL",
        ):
            self.assertNotContains(
                response,
                sentinel,
            )

    def test_public_home_does_not_render_private_collection_metadata(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_home"
            )
        )

        self.assertNotContains(
            response,
            (
                "PRIVATE-HOME-"
                "COLLECTION-SENTINEL"
            ),
        )

        self.assertNotContains(
            response,
            (
                "PRIVATE-HOME-"
                "OWNER-SENTINEL"
            ),
        )

    def test_public_home_does_not_render_internal_geography(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_home"
            )
        )

        self.assertNotContains(
            response,
            (
                "PRIVATE-INTERNAL-"
                "ORIGIN-SENTINEL"
            ),
        )

        self.assertNotContains(
            response,
            (
                "PRIVATE-SAMPLE-"
                "ORIGIN-SENTINEL"
            ),
        )

    def test_public_home_does_not_render_inactive_tags(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_home"
            )
        )

        self.assertContains(
            response,
            "PUBLIC-HOME-TAG",
        )

        self.assertNotContains(
            response,
            "INACTIVE-HOME-TAG-SENTINEL",
        )

    def test_public_home_removed_static_estimates_and_stale_modules(
        self,
    ):
        template = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        self.assertNotIn(
            "Estimativa 2026",
            template,
        )

        self.assertNotIn(
            "?module=",
            template,
        )

        self.assertNotIn(
            'name="module"',
            template,
        )

    def test_home_view_has_no_direct_inventory_query(
        self,
    ):
        source = Path(
            "core/views/public/home.py"
        ).read_text()

        self.assertIn(
            "public_home_context",
            source,
        )

        self.assertNotIn(
            "Sample.objects",
            source,
        )

        self.assertNotIn(
            "Collection.objects",
            source,
        )

    def test_public_home_analytics_start_from_canonical_public_projection(
        self,
    ):
        source = Path(
            "core/services/public_catalog.py"
        ).read_text()

        start = source.index(
            "def public_home_metrics():"
        )

        distribution = (
            source.index(
                "def public_sample_type_distribution("
            )
        )

        featured = (
            source.index(
                "def featured_public_collections("
            )
        )

        context_start = (
            source.index(
                "def public_home_context():"
            )
        )

        metrics_block = source[
            start:distribution
        ]

        distribution_block = source[
            distribution:featured
        ]

        featured_block = source[
            featured:context_start
        ]

        self.assertIn(
            "public_samples_queryset()",
            metrics_block,
        )

        self.assertIn(
            "public_collections_queryset()",
            metrics_block,
        )

        self.assertIn(
            "public_samples_queryset()",
            distribution_block,
        )

        self.assertIn(
            "public_collection_catalog_queryset()",
            featured_block,
        )

        self.assertIn(
            "public_samples_queryset()",
            featured_block,
        )

        self.assertNotIn(
            "Sample.objects",
            (
                metrics_block
                + distribution_block
                + featured_block
            ),
        )

        self.assertNotIn(
            "Collection.objects",
            (
                metrics_block
                + distribution_block
                + featured_block
            ),
        )
