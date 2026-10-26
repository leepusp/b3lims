"""V8.14.6B3: shared child UI and isolated movement submission."""

from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.samples.sample import Sample


class StorageChildUIV8146Tests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="v8146b3-ui",
            is_staff=True,
        )

        cls.sample = Sample.objects.create(
            sample_id="V8146B3-UI-001",
            sample_type="Other",
            organism_name="Storage UI integration",
            owner=cls.user,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location="",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_new_sample_has_explicit_child_creation(self):
        response = self.client.get(reverse("sample_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, 'data-b3-storage-child-v8146', count=1
        )
        self.assertContains(
            response, "storage_child_v8146.js", count=1
        )
        self.assertContains(
            response, "storage_path_builder_v8.js"
        )
        self.assertContains(
            response, 'id="storageChildCreateV8146"'
        )

    def test_edit_sample_has_child_and_move_panels(self):
        response = self.client.get(
            reverse("sample_edit", args=[self.sample.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, 'data-b3-storage-child-v8146', count=1
        )
        self.assertContains(
            response, "storage_child_v8146.js", count=1
        )
        self.assertContains(
            response, 'id="sample-physical-movement-v8146"'
        )

    def test_movement_button_is_not_metadata_submit(self):
        file = (
            Path(settings.BASE_DIR) /
            "core/interfaces/internal/samples/_storage_move_v8146.html"
        )
        content = file.read_text()

        self.assertIn(
            '<button type="button"\n'
            '                    id="storageMoveSubmitV8146"',
            content,
        )
        self.assertIn("data-move-url=", content)
        self.assertNotIn("formaction=", content)

    def test_both_controllers_receive_created_location(self):
        base = (
            Path(settings.BASE_DIR) /
            "core/static/internal/samples"
        )

        for filename in (
            "storage_path_builder_v8.js",
            "storage_edit_move_v8146.js",
        ):
            with self.subTest(filename=filename):
                self.assertIn(
                    "b3:storage-child-created-v8146",
                    (base / filename).read_text(),
                )

        self.assertIn(
            "document.createElement(\"form\")",
            (base / "storage_edit_move_v8146.js").read_text(),
        )
