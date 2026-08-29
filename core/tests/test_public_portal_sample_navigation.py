from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    Sample,
)


class PublicPortalSampleNavigationTests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.owner = User.objects.create_user(
            username="portal-navigation-owner",
        )

        cls.collection = (
            Collection.objects.create(
                name=(
                    "Navigation Public Collection"
                ),
                description=(
                    "Public Collection used for "
                    "navigation regression tests."
                ),
                owner=cls.owner,
                is_public=True,
                is_active=True,
            )
        )

        cls.public_sample = (
            Sample.objects.create(
                sample_id=(
                    "PUBLIC-NAV-001"
                ),
                sample_type=(
                    "Bacterium (Host)"
                ),
                organism_name=(
                    "Navigation public organism"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.private_sample = (
            Sample.objects.create(
                sample_id=(
                    "PRIVATE-NAV-SENTINEL"
                ),
                sample_type=(
                    "Private navigation type"
                ),
                organism_name=(
                    "PRIVATE-NAV-ORGANISM-SENTINEL"
                ),
                owner=cls.owner,
                is_public=False,
                is_embargoed=False,
                is_active=True,
            )
        )

        cls.public_sample.collections.add(
            cls.collection
        )

        cls.private_sample.collections.add(
            cls.collection
        )


    def test_public_home_links_to_sample_catalog(
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
                "public_samples"
            ),
        )

        self.assertContains(
            response,
            "Browse Samples",
        )

        self.assertContains(
            response,
            "Browse all public Samples",
        )


    def test_public_home_collection_kpi_is_navigable(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_home"
            )
        )

        self.assertContains(
            response,
            "Browse all public Collections",
        )

        self.assertContains(
            response,
            reverse(
                "public_collections"
            ),
        )


    def test_public_collection_detail_lists_only_public_samples(
        self,
    ):
        response = self.client.get(
            reverse(
                "public_collection_detail",
                args=[
                    self.collection.pk,
                ],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "PUBLIC-NAV-001",
        )

        self.assertContains(
            response,
            "Navigation public organism",
        )

        self.assertContains(
            response,
            reverse(
                "public_sample_detail",
                args=[
                    "PUBLIC-NAV-001",
                ],
            ),
        )

        self.assertNotContains(
            response,
            "PRIVATE-NAV-SENTINEL",
        )

        self.assertNotContains(
            response,
            "PRIVATE-NAV-ORGANISM-SENTINEL",
        )


    def test_public_collection_template_never_traverses_raw_samples(
        self,
    ):
        source = Path(
            "core/interfaces/public/"
            "collections/detail.html"
        ).read_text()

        for forbidden in (
            "collection.samples",
            "sample.owner",
            "sample.research_group",
            "sample.storage_location",
            "sample.uuid",
            "sample.micro_qr_token",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )


    def test_public_collection_view_uses_public_sample_projection(
        self,
    ):
        source = Path(
            "core/views/public/collections.py"
        ).read_text()

        self.assertIn(
            "public_sample_catalog_queryset()",
            source,
        )

        self.assertIn(
            "collections=collection",
            source,
        )

        self.assertNotIn(
            "collection.samples.all()",
            source,
        )


    def test_network_navigation_targets_public_sample_catalog(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        for token in (
            "PUBLIC_SAMPLES_CATALOG_URL",
            "publicSamplesCatalogUrl",
            "__b3PublicSampleNavigationBound",
            "params.data.category",
            "sample_type:",
            "window.location.assign(",
        ):
            self.assertIn(
                token,
                source,
            )


    def test_ranking_navigation_preserves_taxonomy_source_semantics(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        for token in (
            "source: row.source",
            "rank: rank",
            "group.source",
            '"curated"',
            "rankingCatalogFilters",
            "Browse matching public Samples",
            "candidate.candidate",
        ):
            self.assertIn(
                token,
                source,
            )


    def test_ranking_mapper_does_not_claim_family_or_phylum_filter(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()

        start = source.index(
            "function rankingCatalogFilters("
        )

        end = source.index(
            "function buildNetworkModel(",
            start,
        )

        mapper = source[
            start:
            end
        ]

        self.assertIn(
            '"species"',
            mapper,
        )

        self.assertIn(
            '"genus"',
            mapper,
        )

        self.assertIn(
            '"candidate"',
            mapper,
        )

        self.assertNotIn(
            '"family"',
            mapper,
        )

        self.assertNotIn(
            '"phylum"',
            mapper,
        )


    def test_no_new_public_route_or_api_is_added(
        self,
    ):
        urls = Path(
            "biobank/urls.py"
        ).read_text()

        self.assertEqual(
            urls.count(
                'name="public_samples"'
            ),
            1,
        )

        self.assertEqual(
            urls.count(
                'name="public_sample_detail"'
            ),
            1,
        )

        self.assertNotIn(
            "public/api/",
            urls,
        )
