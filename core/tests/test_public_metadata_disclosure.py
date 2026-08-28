from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    Sample,
    Tag,
)
from core.services.public_catalog import (
    public_collection_catalog_queryset,
    search_public_collections_queryset,
)


class PublicMetadataDisclosureTests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.owner = User.objects.create_user(
            username=(
                "PRIVATE-OWNER-ACCOUNT-SENTINEL"
            ),
            first_name="Private",
            last_name="Owner Sentinel",
        )

        cls.collection = (
            Collection.objects.create(
                name="Public Metadata Collection",
                description=(
                    "Public description for the "
                    "metadata disclosure test."
                ),
                owner=cls.owner,
                is_public=True,
                is_active=True,
            )
        )

        cls.active_tag = Tag.objects.create(
            name="PUBLIC-ACTIVE-TAG",
            is_active=True,
        )

        cls.inactive_tag = Tag.objects.create(
            name="INACTIVE-TAG-SENTINEL",
            is_active=False,
        )

        cls.collection.tags.add(
            cls.active_tag,
            cls.inactive_tag,
        )

        cls.public_sample = (
            Sample.objects.create(
                sample_id="PUBLIC-METADATA-001",
                sample_type=(
                    "BacteriaPublicType"
                ),
                organism_name=(
                    "Pseudomonas publicensis"
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
                    "PRIVATE-METADATA-SENTINEL"
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
                    "EMBARGOED-METADATA-SENTINEL"
                ),
                sample_type=(
                    "EMBARGOED-TYPE-SENTINEL"
                ),
                organism_name=(
                    "EMBARGOED-ORGANISM-SENTINEL"
                ),
                owner=cls.owner,
                is_public=True,
                is_embargoed=True,
                is_active=True,
            )
        )

        cls.collection.samples.add(
            cls.public_sample,
            cls.private_sample,
            cls.embargoed_sample,
        )

    def public_list(
        self,
        query=None,
    ):
        params = {}

        if query is not None:
            params["q"] = query

        return self.client.get(
            reverse(
                "public_collections"
            ),
            params,
        )

    def test_catalog_projection_prefetches_only_active_public_tags(
        self,
    ):
        collection = (
            public_collection_catalog_queryset()
            .get(
                pk=self.collection.pk,
            )
        )

        self.assertEqual(
            [
                tag.name
                for tag in collection.public_tags
            ],
            [
                "PUBLIC-ACTIVE-TAG",
            ],
        )

    def test_public_collection_list_renders_only_active_tag(
        self,
    ):
        response = self.public_list()

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "PUBLIC-ACTIVE-TAG",
        )

        self.assertNotContains(
            response,
            "INACTIVE-TAG-SENTINEL",
        )

    def test_public_collection_detail_does_not_disclose_owner_account(
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

        self.assertNotContains(
            response,
            "PRIVATE-OWNER-ACCOUNT-SENTINEL",
        )

        self.assertNotContains(
            response,
            "Private Owner Sentinel",
        )

        self.assertNotContains(
            response,
            "Responsável:",
        )

    def test_public_collection_detail_renders_only_active_tag(
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

        self.assertContains(
            response,
            "PUBLIC-ACTIVE-TAG",
        )

        self.assertNotContains(
            response,
            "INACTIVE-TAG-SENTINEL",
        )

    def test_public_search_matches_collection_name(
        self,
    ):
        response = self.public_list(
            "Public Metadata Collection"
        )

        self.assertContains(
            response,
            self.collection.name,
        )

    def test_public_search_matches_collection_description(
        self,
    ):
        response = self.public_list(
            "metadata disclosure"
        )

        self.assertContains(
            response,
            self.collection.name,
        )

    def test_public_search_matches_active_tag(
        self,
    ):
        response = self.public_list(
            "PUBLIC-ACTIVE-TAG"
        )

        self.assertContains(
            response,
            self.collection.name,
        )

    def test_public_search_does_not_match_inactive_tag(
        self,
    ):
        response = self.public_list(
            "INACTIVE-TAG-SENTINEL"
        )

        self.assertNotContains(
            response,
            self.collection.name,
        )

    def test_public_search_matches_public_sample_organism(
        self,
    ):
        response = self.public_list(
            "Pseudomonas publicensis"
        )

        self.assertContains(
            response,
            self.collection.name,
        )

    def test_public_search_matches_public_sample_type(
        self,
    ):
        response = self.public_list(
            "BacteriaPublicType"
        )

        self.assertContains(
            response,
            self.collection.name,
        )

    def test_private_sample_organism_cannot_drive_public_search(
        self,
    ):
        response = self.public_list(
            "PRIVATE-ORGANISM-SENTINEL"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        # The submitted search term is intentionally reflected
        # back into the search input. That is not disclosure of
        # private catalog metadata; it is user-supplied request
        # state.
        self.assertEqual(
            response.context["query"],
            "PRIVATE-ORGANISM-SENTINEL",
        )

        # The security invariant is that metadata from a private
        # Sample must not make its public Collection match.
        self.assertNotContains(
            response,
            self.collection.name,
        )

        self.assertEqual(
            list(
                response.context[
                    "collections"
                ]
            ),
            [],
        )

    def test_private_sample_type_cannot_drive_public_search(
        self,
    ):
        response = self.public_list(
            "PRIVATE-TYPE-SENTINEL"
        )

        self.assertNotContains(
            response,
            self.collection.name,
        )

    def test_embargoed_sample_cannot_drive_public_search(
        self,
    ):
        organism_response = self.public_list(
            "EMBARGOED-ORGANISM-SENTINEL"
        )

        type_response = self.public_list(
            "EMBARGOED-TYPE-SENTINEL"
        )

        self.assertNotContains(
            organism_response,
            self.collection.name,
        )

        self.assertNotContains(
            type_response,
            self.collection.name,
        )

    def test_service_search_rejects_private_sample_metadata(
        self,
    ):
        private_matches = (
            search_public_collections_queryset(
                "PRIVATE-ORGANISM-SENTINEL"
            )
        )

        public_matches = (
            search_public_collections_queryset(
                "Pseudomonas publicensis"
            )
        )

        self.assertFalse(
            private_matches
            .filter(
                pk=self.collection.pk,
            )
            .exists()
        )

        self.assertTrue(
            public_matches
            .filter(
                pk=self.collection.pk,
            )
            .exists()
        )

    def test_public_templates_do_not_traverse_sensitive_collection_fields(
        self,
    ):
        list_template = Path(
            "core/interfaces/public/"
            "collections/list.html"
        ).read_text()

        detail_template = Path(
            "core/interfaces/public/"
            "collections/detail.html"
        ).read_text()

        combined = (
            list_template
            + "\n"
            + detail_template
        )

        for forbidden in (
            "collection.owner",
            "owner.username",
            "owner.get_full_name",
            "collection.research_group",
            "collection.biobank",
            "collection.tags.all",
            "collection.tags.exists",
            "get_visibility_display",
        ):
            self.assertNotIn(
                forbidden,
                combined,
            )

        self.assertIn(
            "collection.public_tags",
            combined,
        )

    def test_public_list_no_longer_advertises_unimplemented_filters(
        self,
    ):
        template = Path(
            "core/interfaces/public/"
            "collections/list.html"
        ).read_text()

        self.assertNotIn(
            'name="module"',
            template,
        )

        self.assertNotIn(
            'name="type"',
            template,
        )

        self.assertNotIn(
            'name="tag"',
            template,
        )

        self.assertIn(
            'name="q"',
            template,
        )

    def test_navbar_search_claim_matches_public_search_backend(
        self,
    ):
        template = Path(
            "core/interfaces/public/base.html"
        ).read_text()

        service = Path(
            "core/services/public_catalog.py"
        ).read_text()

        self.assertIn(
            (
                "Buscar por coleção, organismo, "
                "tipo ou tag"
            ),
            template,
        )

        self.assertIn(
            "name__icontains",
            service,
        )

        self.assertIn(
            "description__icontains",
            service,
        )

        self.assertIn(
            "tags__name__icontains",
            service,
        )

        self.assertIn(
            "organism_name__icontains",
            service,
        )

        self.assertIn(
            "sample_type__icontains",
            service,
        )
