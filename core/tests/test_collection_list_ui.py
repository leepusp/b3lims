from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Collection,
    ResearchGroup,
    ResourceAccessGrant,
    Sample,
)
from core.services.resource_access import (
    grant_resource_access,
)


class CollectionListUIV2Tests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.owner = User.objects.create_user(
            username="collection-list-owner",
        )

        cls.coordinator = (
            User.objects.create_user(
                username=(
                    "collection-list-coordinator"
                ),
            )
        )

        cls.member = User.objects.create_user(
            username="collection-list-member",
        )

        cls.outsider = User.objects.create_user(
            username="collection-list-outsider",
        )

        cls.view_delegate = (
            User.objects.create_user(
                username=(
                    "collection-list-view-delegate"
                ),
            )
        )

        cls.manage_delegate = (
            User.objects.create_user(
                username=(
                    "collection-list-manage-delegate"
                ),
            )
        )

        cls.group = ResearchGroup.objects.create(
            name="LEEP",
            coordinator=cls.coordinator,
        )

        cls.group.members.add(
            cls.member
        )

        cls.pseudomonas = (
            Collection.objects.create(
                name=(
                    "B3 Pseudomonas "
                    "Reference Collection"
                ),
                description=(
                    "Reference bacterial isolates "
                    "for comparative genomics."
                ),
                owner=cls.owner,
                research_group=cls.group,
                is_public=False,
                is_active=True,
            )
        )

        cls.environmental = (
            Collection.objects.create(
                name=(
                    "Environmental Isolates "
                    "— Brazil"
                ),
                description=(
                    "Environmental sampling "
                    "across Brazilian sites."
                ),
                owner=cls.owner,
                is_public=True,
                is_active=True,
            )
        )

        cls.amr = Collection.objects.create(
            name=(
                "Antimicrobial Resistance "
                "Surveillance"
            ),
            description=(
                "AMR surveillance dataset "
                "for bacterial isolates."
            ),
            owner=cls.owner,
            is_public=False,
            is_active=True,
        )

        cls.archived = (
            Collection.objects.create(
                name="Archived Phage Collection",
                description=(
                    "Inactive lifecycle fixture."
                ),
                owner=cls.owner,
                is_public=False,
                is_active=False,
            )
        )

        cls.visible_sample = (
            Sample.objects.create(
                sample_id="COL-LIST-VISIBLE-001",
                sample_type="Bacteria",
                organism_name=(
                    "Pseudomonas aeruginosa"
                ),
                owner=cls.owner,
                is_public=False,
                is_active=True,
            )
        )

        cls.hidden_sample = (
            Sample.objects.create(
                sample_id="COL-LIST-HIDDEN-001",
                sample_type="Bacteria",
                organism_name=(
                    "Hidden private isolate"
                ),
                owner=cls.outsider,
                is_public=False,
                is_active=True,
            )
        )

        cls.visible_sample.collections.add(
            cls.pseudomonas
        )

        cls.hidden_sample.collections.add(
            cls.pseudomonas
        )

        grant_resource_access(
            resource=cls.amr,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=cls.owner,
            user=cls.view_delegate,
        )

        grant_resource_access(
            resource=cls.amr,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .MANAGE
            ),
            granted_by=cls.owner,
            user=cls.manage_delegate,
        )

    def list_url(
        self,
    ):
        return reverse(
            "collections_list"
        )

    @staticmethod
    def collection_names(
        response,
    ):
        return [
            collection.name
            for collection
            in response.context[
                "collections"
            ]
        ]

    def test_scientific_fixture_list_and_archive_boundary(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.list_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        names = self.collection_names(
            response
        )

        self.assertIn(
            (
                "B3 Pseudomonas "
                "Reference Collection"
            ),
            names,
        )

        self.assertIn(
            (
                "Environmental Isolates "
                "— Brazil"
            ),
            names,
        )

        self.assertIn(
            (
                "Antimicrobial Resistance "
                "Surveillance"
            ),
            names,
        )

        self.assertNotIn(
            "Archived Phage Collection",
            names,
        )

    def test_visible_sample_count_does_not_leak_private_samples(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.list_url()
        )

        listed = {
            collection.pk: collection
            for collection
            in response.context[
                "collections"
            ]
        }

        pseudomonas = listed[
            self.pseudomonas.pk
        ]

        # The raw Collection contains two Samples.
        self.assertEqual(
            self.pseudomonas.samples.count(),
            2,
        )

        # Only the Sample visible through canonical Sample
        # authorization may contribute to this user's list count.
        self.assertEqual(
            pseudomonas.visible_sample_count,
            1,
        )

        self.assertContains(
            response,
            (
                "Sample totals include only "
                "Samples visible to your account."
            ),
        )

    def test_collection_filters_apply_inside_visible_scope(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        search_response = self.client.get(
            self.list_url(),
            {
                "q": "comparative genomics",
            },
        )

        self.assertEqual(
            self.collection_names(
                search_response
            ),
            [
                (
                    "B3 Pseudomonas "
                    "Reference Collection"
                )
            ],
        )

        group_response = self.client.get(
            self.list_url(),
            {
                "research_group": (
                    str(
                        self.group.pk
                    )
                ),
            },
        )

        self.assertEqual(
            self.collection_names(
                group_response
            ),
            [
                (
                    "B3 Pseudomonas "
                    "Reference Collection"
                )
            ],
        )

        public_response = self.client.get(
            self.list_url(),
            {
                "visibility": "public",
            },
        )

        self.assertEqual(
            self.collection_names(
                public_response
            ),
            [
                (
                    "Environmental Isolates "
                    "— Brazil"
                )
            ],
        )

        owner_response = self.client.get(
            self.list_url(),
            {
                "owner": str(
                    self.owner.pk
                ),
            },
        )

        self.assertEqual(
            set(
                self.collection_names(
                    owner_response
                )
            ),
            {
                (
                    "B3 Pseudomonas "
                    "Reference Collection"
                ),
                (
                    "Environmental Isolates "
                    "— Brazil"
                ),
                (
                    "Antimicrobial Resistance "
                    "Surveillance"
                ),
            },
        )

    def test_filters_never_broaden_collection_authorization(
        self,
    ):
        self.client.force_login(
            self.view_delegate
        )

        response = self.client.get(
            self.list_url(),
            {
                "q": "Pseudomonas",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            self.collection_names(
                response
            ),
            [],
        )

        self.assertNotContains(
            response,
            (
                "B3 Pseudomonas "
                "Reference Collection"
            ),
        )

    def test_owner_actions_include_explorer_edit_sharing_and_deactivate(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.list_url(),
            {
                "q": "Pseudomonas",
            },
        )

        self.assertContains(
            response,
            "Open Explorer",
        )

        self.assertContains(
            response,
            "Edit Collection",
        )

        self.assertContains(
            response,
            "Manage Sharing",
        )

        self.assertContains(
            response,
            "Deactivate",
        )

        self.assertContains(
            response,
            "#collection-sharing-panel",
        )

    def test_group_member_actions_exclude_manage_and_lifecycle(
        self,
    ):
        self.client.force_login(
            self.member
        )

        response = self.client.get(
            self.list_url(),
            {
                "q": "Pseudomonas",
            },
        )

        self.assertContains(
            response,
            "Open Explorer",
        )

        self.assertContains(
            response,
            "Edit Collection",
        )

        self.assertNotContains(
            response,
            "Manage Sharing",
        )

        self.assertNotContains(
            response,
            "Deactivate",
        )

    def test_view_grant_exposes_explorer_only(
        self,
    ):
        self.client.force_login(
            self.view_delegate
        )

        response = self.client.get(
            self.list_url(),
            {
                "q": "Antimicrobial",
            },
        )

        self.assertContains(
            response,
            "Open Explorer",
        )

        self.assertNotContains(
            response,
            "Edit Collection",
        )

        self.assertNotContains(
            response,
            "Manage Sharing",
        )

        self.assertNotContains(
            response,
            "Deactivate",
        )

    def test_manage_grant_exposes_edit_and_sharing_not_deactivate(
        self,
    ):
        self.client.force_login(
            self.manage_delegate
        )

        response = self.client.get(
            self.list_url(),
            {
                "q": "Antimicrobial",
            },
        )

        self.assertContains(
            response,
            "Open Explorer",
        )

        self.assertContains(
            response,
            "Edit Collection",
        )

        self.assertContains(
            response,
            "Manage Sharing",
        )

        self.assertNotContains(
            response,
            "Deactivate",
        )

    def test_template_has_no_unrestricted_sample_enumeration(
        self,
    ):
        template = Path(
            "core/interfaces/internal/"
            "collections/collections.html"
        ).read_text()

        self.assertNotIn(
            "collection.samples.",
            template,
        )

        self.assertIn(
            "collection.visible_sample_count",
            template,
        )

        self.assertIn(
            "Open Explorer",
            template,
        )

        self.assertIn(
            "Manage Sharing",
            template,
        )
