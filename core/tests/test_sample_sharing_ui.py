from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Sample,
    SampleAccessGrant,
)


class SampleSharingUITests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="sharinguiowner",
            password="test-password",
        )

        self.viewer = User.objects.create_user(
            username="sharinguiviewer",
            password="test-password",
        )

        self.outside = User.objects.create_user(
            username="sharinguioutside",
            password="test-password",
        )

        self.other_owner = User.objects.create_user(
            username="sharinguiotherowner",
            password="test-password",
        )

        self.sample_x = Sample.objects.create(
            sample_id="SHARE-UI-X",
            sample_type="Other",
            organism_name="Sharing UI X",
            owner=self.owner,
            status="available",
            is_active=True,
            is_public=False,
        )

        self.sample_y = Sample.objects.create(
            sample_id="SHARE-UI-Y",
            sample_type="Other",
            organism_name="Sharing UI Y",
            owner=self.owner,
            status="available",
            is_active=True,
            is_public=False,
        )

        self.public_sample = Sample.objects.create(
            sample_id="PUBLIC-NOT-DIRECT",
            sample_type="Other",
            organism_name="Public not direct",
            owner=self.other_owner,
            status="available",
            is_active=True,
            is_public=True,
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

        if (
            prefix
            and url.startswith(
                prefix
            )
        ):
            return (
                url[len(prefix):]
                or "/"
            )

        return url


    def test_owner_list_renders_bulk_share_controls(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.client_path(
                reverse(
                    "samples_list"
                )
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Share Selected",
        )

        self.assertContains(
            response,
            "Shared With Me",
        )

        self.assertContains(
            response,
            "sample-share-select",
        )

        self.assertContains(
            response,
            self.outside.username,
        )


    def test_bulk_share_selected_samples_with_outside_user(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_bulk_share"
                )
            ),
            data={
                "sample_ids": [
                    str(
                        self.sample_x.pk
                    ),
                    str(
                        self.sample_y.pk
                    ),
                ],
                "user_id": str(
                    self.outside.pk
                ),
                "access_level": "view",
                "expires_at": "",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        grants = (
            SampleAccessGrant.objects
            .filter(
                user=self.outside
            )
        )

        self.assertEqual(
            grants.count(),
            2,
        )

        self.assertEqual(
            set(
                grants.values_list(
                    "sample__sample_id",
                    flat=True,
                )
            ),
            {
                "SHARE-UI-X",
                "SHARE-UI-Y",
            },
        )


    def test_shared_with_me_excludes_merely_public_sample(self):
        SampleAccessGrant.objects.create(
            sample=self.sample_x,
            user=self.viewer,
            access_level="view",
            granted_by=self.owner,
        )

        self.client.force_login(
            self.viewer
        )

        response = self.client.get(
            (
                self.client_path(
                    reverse(
                        "samples_list"
                    )
                )
                + "?access=shared"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "SHARE-UI-X",
        )

        self.assertNotContains(
            response,
            "PUBLIC-NOT-DIRECT",
        )


    def test_single_sample_share_from_detail(self):
        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_share",
                    args=[
                        self.sample_x.pk
                    ],
                )
            ),
            data={
                "user_id": str(
                    self.outside.pk
                ),
                "access_level": "edit",
                "expires_at": "",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        grant = (
            SampleAccessGrant.objects
            .get(
                sample=self.sample_x,
                user=self.outside,
            )
        )

        self.assertEqual(
            grant.access_level,
            "edit",
        )


    def test_owner_detail_shows_direct_access_management(self):
        SampleAccessGrant.objects.create(
            sample=self.sample_x,
            user=self.viewer,
            access_level="view",
            granted_by=self.owner,
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.client_path(
                reverse(
                    "sample_detail",
                    args=[
                        self.sample_x.pk
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Access & Sharing",
        )

        self.assertContains(
            response,
            self.viewer.username,
        )

        self.assertContains(
            response,
            "Revoke",
        )

        self.assertContains(
            response,
            "Share Sample",
        )


    def test_direct_viewer_sees_shared_state_without_management(self):
        grant = SampleAccessGrant.objects.create(
            sample=self.sample_x,
            user=self.viewer,
            access_level="view",
            granted_by=self.owner,
        )

        self.client.force_login(
            self.viewer
        )

        response = self.client.get(
            self.client_path(
                reverse(
                    "sample_detail",
                    args=[
                        self.sample_x.pk
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Shared with you",
        )

        self.assertNotContains(
            response,
            (
                f"/samples/{self.sample_x.pk}/"
                f"share/{grant.pk}/revoke/"
            ),
        )


    def test_owner_can_revoke_direct_access(self):
        grant = SampleAccessGrant.objects.create(
            sample=self.sample_x,
            user=self.viewer,
            access_level="view",
            granted_by=self.owner,
        )

        self.client.force_login(
            self.owner
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_share_revoke",
                    args=[
                        self.sample_x.pk,
                        grant.pk,
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            SampleAccessGrant.objects.filter(
                pk=grant.pk
            ).exists()
        )


    def test_non_owner_cannot_bulk_share_sample(self):
        self.client.force_login(
            self.viewer
        )

        response = self.client.post(
            self.client_path(
                reverse(
                    "sample_bulk_share"
                )
            ),
            data={
                "sample_ids": [
                    str(
                        self.sample_x.pk
                    ),
                ],
                "user_id": str(
                    self.outside.pk
                ),
                "access_level": "view",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            SampleAccessGrant.objects.filter(
                sample=self.sample_x,
                user=self.outside,
            ).exists()
        )


    def test_sharing_does_not_change_owner(self):
        owner_id = (
            self.sample_x.owner_id
        )

        self.client.force_login(
            self.owner
        )

        self.client.post(
            self.client_path(
                reverse(
                    "sample_share",
                    args=[
                        self.sample_x.pk
                    ],
                )
            ),
            data={
                "user_id": str(
                    self.outside.pk
                ),
                "access_level": "view",
            },
        )

        self.sample_x.refresh_from_db()

        self.assertEqual(
            self.sample_x.owner_id,
            owner_id,
        )
