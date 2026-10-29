"""Biobank-scoped Sample RBAC and Member administration."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models.biobanks.biobank import Biobank
from core.models.biobanks.biobank_user_role import BiobankUserRole
from core.models.samples.sample import Sample
from core.permissions.samples import (
    can_edit_sample,
    can_view_sample,
    visible_samples_for_user,
)
from core.permissions.storage_workspaces_v8 import (
    can_operate_on_sample_storage,
)


class BiobankSampleMemberRBACTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        def user(name):
            return User.objects.create_user(
                username="rbac-" + name,
                password="test-only-password",
            )

        cls.bank_owner = user("bank-owner")
        cls.sample_owner = user("sample-owner")
        cls.editor = user("editor")
        cls.manager = user("manager")
        cls.viewer = user("viewer")
        cls.outsider = user("outsider")
        cls.other_owner = user("other-owner")

        cls.bank = Biobank.objects.create(
            name="RBAC BBAMS",
            owner=cls.bank_owner,
            is_active=True,
            is_public=False,
        )

        cls.other_bank = Biobank.objects.create(
            name="RBAC Unrelated",
            owner=cls.other_owner,
            is_active=True,
            is_public=False,
        )

        for member, role in (
            (cls.editor, BiobankUserRole.EDITOR),
            (cls.manager, BiobankUserRole.MANAGER),
            (cls.viewer, BiobankUserRole.VIEWER),
        ):
            BiobankUserRole.objects.create(
                biobank=cls.bank,
                user=member,
                role=role,
            )

        cls.sample = Sample.objects.create(
            sample_id="RBAC-BBAMS-001",
            sample_type="Other",
            organism_name="RBAC test sample",
            owner=cls.sample_owner,
            biobank=cls.bank,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

        cls.unrelated_sample = Sample.objects.create(
            sample_id="RBAC-OTHER-001",
            sample_type="Other",
            organism_name="Unrelated private sample",
            owner=cls.sample_owner,
            biobank=cls.other_bank,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

    def members_url(self):
        return reverse(
            "biobank_members",
            args=[self.bank.pk],
        )

    def test_editor_edits_non_owned_sample(self):
        self.assertNotEqual(
            self.sample.owner_id,
            self.editor.pk,
        )
        self.assertTrue(
            can_edit_sample(self.editor, self.sample)
        )
        self.assertTrue(
            can_operate_on_sample_storage(
                self.editor,
                self.sample,
            )
        )

    def test_editor_can_see_sample_listing(self):
        self.assertTrue(
            can_view_sample(self.editor, self.sample)
        )
        self.assertIn(
            self.sample.pk,
            visible_samples_for_user(
                self.editor
            ).values_list("pk", flat=True),
        )

    def test_manager_can_edit_sample(self):
        self.assertTrue(
            can_edit_sample(self.manager, self.sample)
        )

    def test_viewer_can_view_but_not_edit(self):
        self.assertTrue(
            can_view_sample(self.viewer, self.sample)
        )
        self.assertFalse(
            can_edit_sample(self.viewer, self.sample)
        )
        self.assertFalse(
            can_operate_on_sample_storage(
                self.viewer,
                self.sample,
            )
        )

    def test_unrelated_user_cannot_edit(self):
        self.assertFalse(
            can_edit_sample(self.outsider, self.sample)
        )
        self.assertFalse(
            can_view_sample(self.outsider, self.sample)
        )

    def test_editor_cannot_edit_other_biobank(self):
        self.assertFalse(
            can_edit_sample(
                self.editor,
                self.unrelated_sample,
            )
        )
        self.assertFalse(
            can_operate_on_sample_storage(
                self.editor,
                self.unrelated_sample,
            )
        )

    def test_trash_sample_remains_immutable(self):
        self.sample.deletion_requested_at = timezone.now()

        self.assertFalse(
            can_edit_sample(self.editor, self.sample)
        )
        self.assertFalse(
            can_operate_on_sample_storage(
                self.editor,
                self.sample,
            )
        )

    def test_editor_edit_page_is_accessible(self):
        self.client.force_login(self.editor)

        response = self.client.get(
            reverse(
                "sample_edit",
                args=[self.sample.pk],
            )
        )

        self.assertEqual(response.status_code, 200)

    def test_viewer_edit_page_is_forbidden(self):
        self.client.force_login(self.viewer)

        response = self.client.get(
            reverse(
                "sample_edit",
                args=[self.sample.pk],
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_owner_updates_member_role_with_named_redirect(self):
        self.client.force_login(self.bank_owner)

        role = BiobankUserRole.objects.get(
            biobank=self.bank,
            user=self.editor,
        )

        response = self.client.post(
            self.members_url(),
            {
                "action": "update_role",
                "role_id": str(role.pk),
                "role": "viewer",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            self.members_url(),
        )

        role.refresh_from_db()
        self.assertEqual(
            role.role,
            BiobankUserRole.VIEWER,
        )

    def test_invalid_role_cannot_be_saved(self):
        self.client.force_login(self.bank_owner)

        role = BiobankUserRole.objects.get(
            biobank=self.bank,
            user=self.editor,
        )

        response = self.client.post(
            self.members_url(),
            {
                "action": "update_role",
                "role_id": str(role.pk),
                "role": "supereditor",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            self.members_url(),
        )

        role.refresh_from_db()
        self.assertEqual(
            role.role,
            BiobankUserRole.EDITOR,
        )

    def test_editor_cannot_manage_members(self):
        self.client.force_login(self.editor)

        response = self.client.get(self.members_url())

        self.assertEqual(response.status_code, 403)

    def test_manager_can_manage_members(self):
        self.client.force_login(self.manager)

        response = self.client.get(self.members_url())

        self.assertEqual(response.status_code, 200)

    def test_anonymous_member_page_requires_login(self):
        response = self.client.get(self.members_url())

        self.assertIn(response.status_code, (301, 302))
