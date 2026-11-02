"""HTTP tests for owner-scoped ELN drafts."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.services.eln_private_drafts import (
    DraftConflict,
    DraftNotFound,
)


ENTRY_UUID = "550e8400-e29b-41d4-a716-446655440000"

ENTRY = {
    "entry_id": ENTRY_UUID,
    "owner": "ccalomeno",
    "project": "eln_validation",
    "revision": 1,
    "title": "Test experiment",
    "content": "Synthetic observation",
    "protocol": "Protocol",
    "results": "None",
    "sample_ids": [],
    "chemical_ids": [],
    "saved_at": "2026-11-02T00:00:00+00:00",
}


@override_settings(B3_ELN_EXPERIMENTAL_ENABLED=True)
class PrivateElnWebTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="ccalomeno",
            password="test-password",
            is_active=True,
        )

        cls.outsider = get_user_model().objects.create_user(
            username="outsider",
            password="test-password",
            is_active=True,
        )

        group = Group.objects.create(
            name="b3_eln_evaluators"
        )

        cls.user.groups.add(group)

    def setUp(self):
        self.client.force_login(self.user)

    @patch(
        "core.views.internal.lab_tools."
        "eln_private_web.PrivateDraftRepository"
    )
    def test_list_private_entries(self, repository_class):
        repository = repository_class.return_value

        repository.storage.listdir.return_value = (
            ["eln_validation"], []
        )

        repository.list_entries.return_value = [ENTRY]

        response = self.client.get(
            reverse("eln_private_drafts")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test experiment")

    def test_preview_primary_action_opens_editor(self):
        response = self.client.get(
            reverse("eln_experimental_index")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'href="' + reverse("eln_private_new") + '"',
        )
        self.assertNotContains(
            response,
            'disabled title="Private draft storage pending"',
        )

    def test_new_entry_editor(self):
        response = self.client.get(
            reverse("eln_private_new")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, 'name="project"'
        )
        self.assertContains(
            response, 'name="sample_ids"'
        )
        self.assertContains(
            response, 'name="chemical_ids"'
        )

    @patch(
        "core.views.internal.lab_tools."
        "eln_private_web.PrivateDraftRepository"
    )
    def test_create_redirects_to_entry(self, repository_class):
        repository_class.return_value.create.return_value = ENTRY

        response = self.client.post(
            reverse("eln_private_new"),
            {
                "project": "eln_validation",
                "title": "Test experiment",
                "content": "Observation",
                "protocol": "Protocol",
                "results": "Result",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            ENTRY_UUID, response["Location"]
        )

    @patch(
        "core.views.internal.lab_tools."
        "eln_private_web.PrivateDraftRepository"
    )
    def test_detail_reads_existing_entry(self, repository_class):
        repository_class.return_value.latest.return_value = ENTRY

        response = self.client.get(
            reverse(
                "eln_private_detail",
                kwargs={
                    "project": "eln_validation",
                    "entry_id": ENTRY_UUID,
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Synthetic observation"
        )
        self.assertContains(
            response, "Save new revision"
        )

    @patch(
        "core.views.internal.lab_tools."
        "eln_private_web.PrivateDraftRepository"
    )
    def test_stale_revision_returns_conflict(self, repository_class):
        repository_class.return_value.latest.return_value = ENTRY

        repository_class.return_value.revise.side_effect = (
            DraftConflict("stale")
        )

        response = self.client.post(
            reverse(
                "eln_private_detail",
                kwargs={
                    "project": "eln_validation",
                    "entry_id": ENTRY_UUID,
                },
            ),
            {
                "title": "Test",
                "expected_revision": "1",
            },
        )

        self.assertEqual(response.status_code, 409)

    @patch(
        "core.views.internal.lab_tools."
        "eln_private_web.PrivateDraftRepository"
    )
    def test_missing_entry_returns_404(self, repository_class):
        repository_class.return_value.latest.side_effect = (
            DraftNotFound("missing")
        )

        response = self.client.get(
            reverse(
                "eln_private_detail",
                kwargs={
                    "project": "eln_validation",
                    "entry_id": ENTRY_UUID,
                },
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_unauthorized_sample_is_rejected(self):
        response = self.client.post(
            reverse("eln_private_new"),
            {
                "project": "eln_validation",
                "title": "Test",
                "sample_ids": [99999],
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_project_traversal_is_rejected(self):
        response = self.client.post(
            reverse("eln_private_new"),
            {
                "project": "../etc",
                "title": "Test",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_unapproved_evaluator_is_forbidden(self):
        self.client.force_login(self.outsider)

        for name in (
            "eln_private_drafts",
            "eln_private_new",
        ):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 403)

    @override_settings(B3_ELN_EXPERIMENTAL_ENABLED=False)
    def test_disabled_feature_returns_404(self):
        response = self.client.get(
            reverse("eln_private_new")
        )

        self.assertEqual(response.status_code, 404)

    def test_csrf_is_required_for_writes(self):
        strict_client = Client(
            enforce_csrf_checks=True
        )

        strict_client.force_login(self.user)

        response = strict_client.post(
            reverse("eln_private_new"),
            {
                "project": "eln_validation",
                "title": "Test",
            },
        )

        self.assertEqual(response.status_code, 403)
