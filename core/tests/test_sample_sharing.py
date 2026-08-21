from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Sample,
    SampleAccessGrant,
    SampleFile,
)
from core.permissions.samples import (
    can_delete_sample,
    can_edit_sample,
    can_manage_sample_sharing,
    can_view_sample,
    visible_samples_for_user,
)
from core.services.sample_sharing import (
    bulk_grant_sample_access,
    grant_sample_access,
    revoke_sample_access,
)


class SampleDirectSharingTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="shareowner",
            password="test-password",
        )

        self.viewer = User.objects.create_user(
            username="shareviewer",
            password="test-password",
        )

        self.editor = User.objects.create_user(
            username="shareeditor",
            password="test-password",
        )

        self.outsider = User.objects.create_user(
            username="shareoutsider",
            password="test-password",
        )

        self.sample_x = Sample.objects.create(
            sample_id="SHARE-X",
            sample_type="Other",
            organism_name="Shared X",
            owner=self.owner,
            status="available",
            is_active=True,
            is_public=False,
        )

        self.sample_y = Sample.objects.create(
            sample_id="SHARE-Y",
            sample_type="Other",
            organism_name="Shared Y",
            owner=self.owner,
            status="available",
            is_active=True,
            is_public=False,
        )

    @staticmethod
    def client_path(url):
        prefix = str(
            getattr(
                settings,
                "FORCE_SCRIPT_NAME",
                "",
            )
            or ""
        )

        if prefix and url.startswith(
            prefix
        ):
            return (
                url[len(prefix):]
                or "/"
            )

        return url

    def test_view_grant_allows_visibility_but_not_edit(self):
        grant, created = grant_sample_access(
            sample=self.sample_x,
            user=self.viewer,
            access_level="view",
            granted_by=self.owner,
        )

        self.assertTrue(
            created
        )

        self.assertEqual(
            grant.access_level,
            "view",
        )

        self.assertTrue(
            can_view_sample(
                self.viewer,
                self.sample_x,
            )
        )

        self.assertFalse(
            can_edit_sample(
                self.viewer,
                self.sample_x,
            )
        )

        self.assertFalse(
            can_delete_sample(
                self.viewer,
                self.sample_x,
            )
        )

        self.assertFalse(
            can_manage_sample_sharing(
                self.viewer,
                self.sample_x,
            )
        )

    def test_edit_grant_allows_metadata_edit_but_not_delegation(self):
        grant_sample_access(
            sample=self.sample_x,
            user=self.editor,
            access_level="edit",
            granted_by=self.owner,
        )

        self.assertTrue(
            can_view_sample(
                self.editor,
                self.sample_x,
            )
        )

        self.assertTrue(
            can_edit_sample(
                self.editor,
                self.sample_x,
            )
        )

        self.assertFalse(
            can_delete_sample(
                self.editor,
                self.sample_x,
            )
        )

        self.assertFalse(
            can_manage_sample_sharing(
                self.editor,
                self.sample_x,
            )
        )

    def test_direct_grant_works_outside_research_group(self):
        self.assertFalse(
            can_view_sample(
                self.outsider,
                self.sample_x,
            )
        )

        grant_sample_access(
            sample=self.sample_x,
            user=self.outsider,
            access_level="view",
            granted_by=self.owner,
        )

        self.assertTrue(
            can_view_sample(
                self.outsider,
                self.sample_x,
            )
        )

    def test_visible_samples_includes_directly_shared_sample(self):
        grant_sample_access(
            sample=self.sample_x,
            user=self.viewer,
            access_level="view",
            granted_by=self.owner,
        )

        ids = set(
            visible_samples_for_user(
                self.viewer
            ).values_list(
                "pk",
                flat=True,
            )
        )

        self.assertIn(
            self.sample_x.pk,
            ids,
        )

        self.assertNotIn(
            self.sample_y.pk,
            ids,
        )

    def test_expired_grant_provides_no_access(self):
        SampleAccessGrant.objects.create(
            sample=self.sample_x,
            user=self.viewer,
            access_level="view",
            granted_by=self.owner,
            expires_at=(
                timezone.now()
                - timedelta(
                    minutes=1
                )
            ),
        )

        self.assertFalse(
            can_view_sample(
                self.viewer,
                self.sample_x,
            )
        )

    def test_revoke_removes_direct_access(self):
        grant_sample_access(
            sample=self.sample_x,
            user=self.viewer,
            access_level="view",
            granted_by=self.owner,
        )

        deleted = revoke_sample_access(
            sample=self.sample_x,
            user=self.viewer,
            revoked_by=self.owner,
        )

        self.assertEqual(
            deleted,
            1,
        )

        self.assertFalse(
            can_view_sample(
                self.viewer,
                self.sample_x,
            )
        )

    def test_bulk_share_x_and_y_with_outside_user(self):
        result = bulk_grant_sample_access(
            samples=[
                self.sample_x,
                self.sample_y,
            ],
            user=self.outsider,
            access_level="view",
            granted_by=self.owner,
        )

        self.assertEqual(
            result.created,
            2,
        )

        self.assertEqual(
            result.updated,
            0,
        )

        self.assertEqual(
            SampleAccessGrant.objects.filter(
                user=self.outsider,
            ).count(),
            2,
        )

        self.assertTrue(
            can_view_sample(
                self.outsider,
                self.sample_x,
            )
        )

        self.assertTrue(
            can_view_sample(
                self.outsider,
                self.sample_y,
            )
        )

    def test_bulk_share_is_atomic_when_actor_cannot_manage_one_sample(self):
        other = get_user_model().objects.create_user(
            username="otherowner",
            password="test-password",
        )

        foreign_sample = Sample.objects.create(
            sample_id="SHARE-FOREIGN",
            sample_type="Other",
            organism_name="Foreign Sample",
            owner=other,
            status="available",
            is_active=True,
            is_public=False,
        )

        with self.assertRaises(
            PermissionDenied
        ):
            bulk_grant_sample_access(
                samples=[
                    self.sample_x,
                    foreign_sample,
                ],
                user=self.viewer,
                access_level="view",
                granted_by=self.owner,
            )

        self.assertFalse(
            SampleAccessGrant.objects.filter(
                user=self.viewer,
            ).exists()
        )

    def test_owner_cannot_receive_redundant_grant(self):
        with self.assertRaises(
            ValidationError
        ):
            grant_sample_access(
                sample=self.sample_x,
                user=self.owner,
                access_level="view",
                granted_by=self.owner,
            )

    def test_non_owner_cannot_grant_access(self):
        with self.assertRaises(
            PermissionDenied
        ):
            grant_sample_access(
                sample=self.sample_x,
                user=self.viewer,
                access_level="view",
                granted_by=self.outsider,
            )

    def test_direct_view_grant_allows_protected_file_download(self):
        grant_sample_access(
            sample=self.sample_x,
            user=self.viewer,
            access_level="view",
            granted_by=self.owner,
        )

        sample_file = SampleFile(
            sample=self.sample_x,
            file=(
                "users/shareowner/"
                "samples/sample_"
                f"{self.sample_x.pk}_SHARE-X/"
                "files/shared.pdf"
            ),
            category="pdf",
            mime_type="application/pdf",
            file_size=8,
        )

        # Avoid touching protected filesystem storage in this permission test.
        SampleFile.objects.bulk_create(
            [
                sample_file,
            ]
        )

        sample_file = SampleFile.objects.get(
            sample=self.sample_x
        )

        fake_handle = ContentFile(
            b"%PDF-1.4"
        )

        self.client.force_login(
            self.viewer
        )

        with patch.object(
            sample_file.file.storage,
            "open",
            return_value=fake_handle,
        ):
            response = self.client.get(
                self.client_path(
                    reverse(
                        "sample_file_download",
                        args=[
                            sample_file.pk,
                        ],
                    )
                )
            )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_direct_grant_does_not_change_sample_owner(self):
        original_owner_id = (
            self.sample_x.owner_id
        )

        grant_sample_access(
            sample=self.sample_x,
            user=self.viewer,
            access_level="edit",
            granted_by=self.owner,
        )

        self.sample_x.refresh_from_db()

        self.assertEqual(
            self.sample_x.owner_id,
            original_owner_id,
        )


class SampleSharingOwnershipBoundaryTests(TestCase):
    """
    Direct Sample sharing must never become an implicit
    ownership-transfer mechanism.
    """

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="boundaryowner",
            password="test-password",
        )

        self.editor = User.objects.create_user(
            username="boundaryeditor",
            password="test-password",
        )

        self.alternate_owner = User.objects.create_user(
            username="boundaryalternate",
            password="test-password",
        )

        self.sample = Sample.objects.create(
            sample_id="BOUNDARY-001",
            sample_type="Other",
            organism_name="Boundary Sample",
            owner=self.owner,
            status="available",
            is_active=True,
            is_public=False,
        )

        grant_sample_access(
            sample=self.sample,
            user=self.editor,
            access_level="edit",
            granted_by=self.owner,
        )

    @staticmethod
    def _post_data(form):
        """
        Convert the current unbound ModelForm values into data
        suitable for a bound form.
        """
        data = {}

        for name in form.fields:
            value = form[
                name
            ].value()

            if isinstance(
                value,
                (
                    list,
                    tuple,
                ),
            ):
                data[name] = [
                    str(item)
                    for item in value
                    if item not in (
                        None,
                        "",
                    )
                ]

            elif value is None:
                data[name] = ""

            elif isinstance(
                value,
                bool,
            ):
                if value:
                    data[name] = "on"

            else:
                data[name] = str(
                    value
                )

        return data

    def test_existing_sample_owner_field_is_locked_for_owner(self):
        from core.forms import SampleForm

        form = SampleForm(
            instance=self.sample,
            user=self.owner,
        )

        owner_field = (
            form.fields[
                "owner"
            ]
        )

        self.assertTrue(
            owner_field.disabled
        )

        self.assertEqual(
            list(
                owner_field.queryset
                .values_list(
                    "pk",
                    flat=True,
                )
            ),
            [
                self.owner.pk
            ],
        )

        self.assertIn(
            "Transfer Ownership",
            owner_field.help_text,
        )

    def test_existing_sample_owner_field_is_locked_for_edit_grantee(self):
        from core.forms import SampleForm

        form = SampleForm(
            instance=self.sample,
            user=self.editor,
        )

        owner_field = (
            form.fields[
                "owner"
            ]
        )

        self.assertTrue(
            owner_field.disabled
        )

        self.assertEqual(
            list(
                owner_field.queryset
                .values_list(
                    "pk",
                    flat=True,
                )
            ),
            [
                self.owner.pk
            ],
        )

    def test_existing_sample_owner_field_is_locked_without_user(self):
        from core.forms import SampleForm

        form = SampleForm(
            instance=self.sample,
        )

        self.assertTrue(
            form.fields[
                "owner"
            ].disabled
        )

    def test_create_sample_owner_field_remains_selectable(self):
        from core.forms import SampleForm

        form = SampleForm(
            user=self.owner,
        )

        self.assertFalse(
            form.fields[
                "owner"
            ].disabled
        )

    def test_edit_grantee_cannot_smuggle_new_owner_in_form_post(self):
        from core.forms import SampleForm

        unbound = SampleForm(
            instance=self.sample,
            user=self.editor,
        )

        data = self._post_data(
            unbound
        )

        data["owner"] = str(
            self.alternate_owner.pk
        )

        data["scientific_notes"] = (
            "Metadata edited by direct EDIT grant."
        )

        form = SampleForm(
            data=data,
            instance=self.sample,
            user=self.editor,
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        saved = form.save()

        saved.refresh_from_db()

        self.assertEqual(
            saved.owner_id,
            self.owner.pk,
        )

        self.assertEqual(
            saved.scientific_notes,
            "Metadata edited by direct EDIT grant.",
        )

    def test_owner_cannot_smuggle_new_owner_in_standard_edit_form(self):
        from core.forms import SampleForm

        unbound = SampleForm(
            instance=self.sample,
            user=self.owner,
        )

        data = self._post_data(
            unbound
        )

        data["owner"] = str(
            self.alternate_owner.pk
        )

        form = SampleForm(
            data=data,
            instance=self.sample,
            user=self.owner,
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        saved = form.save()

        saved.refresh_from_db()

        self.assertEqual(
            saved.owner_id,
            self.owner.pk,
        )
