from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.forms import CollectionEditForm
from core.models import (
    Collection,
    ResearchGroup,
    ResourceAccessGrant,
    Tag,
)
from core.services.collection_sharing import (
    grant_collection_access,
)
from core.services.metadata_vocabularies import (
    get_or_create_active_keyword_value,
)


User = get_user_model()


class CollectionEditTests(
    TestCase
):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="collection-edit-owner",
        )

        cls.other_user = User.objects.create_user(
            username="collection-edit-other",
        )

        cls.group_member = User.objects.create_user(
            username="collection-edit-member",
        )

        cls.explicit_editor = User.objects.create_user(
            username="collection-edit-explicit",
        )

        cls.viewer = User.objects.create_user(
            username="collection-edit-viewer",
        )

        cls.manager = User.objects.create_user(
            username="collection-edit-manager",
        )

        cls.coordinator = User.objects.create_user(
            username="collection-edit-coordinator",
        )

        cls.group = ResearchGroup.objects.create(
            name="Collection Edit Group",
            coordinator=cls.coordinator,
        )

        cls.group.members.add(
            cls.group_member
        )

    def collection(
        self,
        name="Editable Collection",
        *,
        owner=None,
        research_group=None,
        is_public=False,
        is_active=True,
    ):
        return Collection.objects.create(
            name=name,
            description="Original description",
            owner=owner or self.owner,
            research_group=research_group,
            is_public=is_public,
            is_active=is_active,
        )

    def edit_url(
        self,
        collection,
    ):
        return reverse(
            "collection_edit",
            args=[
                collection.pk,
            ],
        )

    def detail_url(
        self,
        collection,
    ):
        return reverse(
            "collection_detail",
            args=[
                collection.pk,
            ],
        )

    def test_edit_form_has_exact_descriptive_field_allowlist(self):
        form = CollectionEditForm()

        self.assertEqual(
            list(
                form.fields
            ),
            [
                "name",
                "description",
            ],
        )

        for forbidden in (
            "owner",
            "research_group",
            "is_active",
            "is_public",
            "tags",
            "keywords",
        ):
            self.assertNotIn(
                forbidden,
                form.fields,
            )

    def test_owner_sees_enabled_edit_link_and_can_open_editor(self):
        collection = self.collection()

        self.client.force_login(
            self.owner
        )

        detail = self.client.get(
            self.detail_url(
                collection
            )
        )

        self.assertEqual(
            detail.status_code,
            200,
        )

        self.assertContains(
            detail,
            self.edit_url(
                collection
            ),
        )

        self.assertNotContains(
            detail,
            "Collection editing will be added in a dedicated changeset.",
        )

        editor = self.client.get(
            self.edit_url(
                collection
            )
        )

        self.assertEqual(
            editor.status_code,
            200,
        )

        self.assertContains(
            editor,
            "Collection Metadata",
        )

        self.assertContains(
            editor,
            "Governance fields are not changed here.",
        )

    def test_unauthorized_user_cannot_open_or_post_editor(self):
        collection = self.collection()

        self.client.force_login(
            self.other_user
        )

        get_response = self.client.get(
            self.edit_url(
                collection
            )
        )

        self.assertEqual(
            get_response.status_code,
            403,
        )

        post_response = self.client.post(
            self.edit_url(
                collection
            ),
            {
                "name": "Unauthorized change",
                "description": "Blocked",
            },
        )

        self.assertEqual(
            post_response.status_code,
            403,
        )

        collection.refresh_from_db()

        self.assertEqual(
            collection.name,
            "Editable Collection",
        )

    def test_research_group_member_can_edit_descriptive_metadata(self):
        collection = self.collection(
            research_group=self.group,
        )

        self.client.force_login(
            self.group_member
        )

        response = self.client.post(
            self.edit_url(
                collection
            ),
            {
                "name": "Group Member Update",
                "description": "Updated by group member",
            },
        )

        self.assertRedirects(
            response,
            self.detail_url(
                collection
            ),
        )

        collection.refresh_from_db()

        self.assertEqual(
            collection.name,
            "Group Member Update",
        )

        self.assertEqual(
            collection.description,
            "Updated by group member",
        )

    def test_explicit_edit_grant_can_edit_but_view_grant_cannot(self):
        editable = self.collection(
            "Explicit Edit Collection"
        )

        view_only = self.collection(
            "View Only Collection"
        )

        grant_collection_access(
            collection=editable,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .EDIT
            ),
            granted_by=self.owner,
            user=self.explicit_editor,
        )

        grant_collection_access(
            collection=view_only,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .VIEW
            ),
            granted_by=self.owner,
            user=self.viewer,
        )

        self.client.force_login(
            self.explicit_editor
        )

        edit_response = self.client.post(
            self.edit_url(
                editable
            ),
            {
                "name": "Explicitly Edited",
                "description": "Allowed",
            },
        )

        self.assertRedirects(
            edit_response,
            self.detail_url(
                editable
            ),
        )

        editable.refresh_from_db()

        self.assertEqual(
            editable.name,
            "Explicitly Edited",
        )

        self.client.force_login(
            self.viewer
        )

        view_response = self.client.get(
            self.edit_url(
                view_only
            )
        )

        self.assertEqual(
            view_response.status_code,
            403,
        )

    def test_explicit_manage_grant_can_use_standard_editor(self):
        collection = self.collection(
            "Managed Editable Collection"
        )

        grant_collection_access(
            collection=collection,
            access_level=(
                ResourceAccessGrant
                .AccessLevel
                .MANAGE
            ),
            granted_by=self.owner,
            user=self.manager,
        )

        self.client.force_login(
            self.manager
        )

        response = self.client.post(
            self.edit_url(
                collection
            ),
            {
                "name": "Managed Metadata Update",
                "description": "Manage includes edit",
            },
        )

        self.assertRedirects(
            response,
            self.detail_url(
                collection
            ),
        )

        collection.refresh_from_db()

        self.assertEqual(
            collection.name,
            "Managed Metadata Update",
        )

    def test_standard_edit_ignores_governance_field_smuggling(self):
        other_group = ResearchGroup.objects.create(
            name="Smuggled Research Group",
            coordinator=self.other_user,
        )

        collection = self.collection(
            is_public=False,
        )

        original_owner_id = (
            collection.owner_id
        )

        original_group_id = (
            collection.research_group_id
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.edit_url(
                collection
            ),
            {
                "name": "Safe Metadata Update",
                "description": "Governance unchanged",
                "owner": str(
                    self.other_user.pk
                ),
                "research_group": str(
                    other_group.pk
                ),
                "is_active": "",
                "is_public": "on",
            },
        )

        self.assertRedirects(
            response,
            self.detail_url(
                collection
            ),
        )

        collection.refresh_from_db()

        self.assertEqual(
            collection.name,
            "Safe Metadata Update",
        )

        self.assertEqual(
            collection.owner_id,
            original_owner_id,
        )

        self.assertEqual(
            collection.research_group_id,
            original_group_id,
        )

        self.assertTrue(
            collection.is_active
        )

        self.assertFalse(
            collection.is_public
        )

    def test_standard_edit_preserves_tags_and_keywords(self):
        collection = self.collection()

        tag = Tag.objects.create(
            name="Preserved Collection Tag",
        )

        keyword_value, _ = (
            get_or_create_active_keyword_value(
                "Collection Edit Key",
                "Preserved Value",
            )
        )

        collection.tags.add(
            tag
        )

        collection.keywords.add(
            keyword_value
        )

        original_tag_ids = set(
            collection.tags.values_list(
                "pk",
                flat=True,
            )
        )

        original_keyword_ids = set(
            collection.keywords.values_list(
                "pk",
                flat=True,
            )
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.edit_url(
                collection
            ),
            {
                "name": "Vocabulary Preserved",
                "description": "No vocabulary mutation",
                "tags": [],
                "keyword_pairs": [
                    "Injected:::Value",
                ],
            },
        )

        self.assertRedirects(
            response,
            self.detail_url(
                collection
            ),
        )

        collection.refresh_from_db()

        self.assertEqual(
            set(
                collection.tags.values_list(
                    "pk",
                    flat=True,
                )
            ),
            original_tag_ids,
        )

        self.assertEqual(
            set(
                collection.keywords.values_list(
                    "pk",
                    flat=True,
                )
            ),
            original_keyword_ids,
        )

    def test_invalid_edit_renders_errors_without_partial_write(self):
        collection = self.collection()

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.edit_url(
                collection
            ),
            {
                "name": "",
                "description": "Should not persist",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFormError(
            response.context[
                "collection_edit_form"
            ],
            "name",
            "This field is required.",
        )

        collection.refresh_from_db()

        self.assertEqual(
            collection.name,
            "Editable Collection",
        )

        self.assertEqual(
            collection.description,
            "Original description",
        )

    def test_inactive_collection_cannot_be_edited(self):
        collection = self.collection(
            is_active=False,
        )

        self.client.force_login(
            self.owner
        )

        get_response = self.client.get(
            self.edit_url(
                collection
            )
        )

        self.assertEqual(
            get_response.status_code,
            404,
        )

        post_response = self.client.post(
            self.edit_url(
                collection
            ),
            {
                "name": "Inactive Update",
                "description": "Blocked",
            },
        )

        self.assertEqual(
            post_response.status_code,
            404,
        )
