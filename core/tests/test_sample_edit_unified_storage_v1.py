"""Edit Sample layout, public visibility and validation regression."""

from pathlib import Path

from django import forms
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models.samples.sample import Sample


class EditSampleStorageLayoutTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = Path(__file__).resolve().parents[2]
        cls.html = (
            root / "core/interfaces/internal/samples/edit.html"
        ).read_text(encoding="utf-8")

    def test_unified_storage_card(self):
        self.assertEqual(
            self.html.count('id="b3-edit-unified-storage"'),
            1,
        )
        self.assertIn(
            "Physical path and Sample position",
            self.html,
        )

    def test_existing_storage_contracts(self):
        for marker in (
            'id="dynamicStorageContainer"',
            'id="storage_location_hidden"',
            'id="storage_edit_intent"',
            'name="storage_initial_paths"',
            'id="storageInputVisual"',
        ):
            self.assertEqual(self.html.count(marker), 1)

    def test_only_one_workspace_and_movement_component(self):
        for marker in (
            '_storage_child_v8146.html',
            '_storage_move_v8146.html',
        ):
            self.assertEqual(self.html.count(marker), 1)

    def test_workspace_precedes_path(self):
        self.assertLess(
            self.html.index('_storage_child_v8146.html'),
            self.html.index('id="dynamicStorageContainer"'),
        )

    def test_validation_messages_are_present(self):
        self.assertIn(
            'id="sample-edit-validation-summary"',
            self.html,
        )
        self.assertIn(
            "form.non_field_errors",
            self.html,
        )
        self.assertIn(
            "origin_form.non_field_errors",
            self.html,
        )

    def test_visibility_controls_are_preserved(self):
        self.assertIn(
            'data-sample-governance-toggle="public"',
            self.html,
        )
        self.assertIn(
            'data-sample-governance-toggle="embargo"',
            self.html,
        )


class EditSamplePublicPersistenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="edit-public-regression-admin",
            email="admin@example.invalid",
            password="test-only-password",
        )

        cls.sample = Sample.objects.create(
            sample_id="EDIT-PUBLIC-REG-001",
            sample_type="Other",
            organism_name="Visibility regression",
            owner=cls.admin,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse(
            "sample_edit",
            args=[self.sample.pk],
        )

    def _payload(self):
        response = self.client.get(self.url)
        self.assertEqual(
            response.status_code,
            200,
            f"EDIT_GET_STATUS={response.status_code}",
        )

        form = response.context["form"]
        origin_form = response.context["origin_form"]

        self.assertIn("is_public", form.fields)
        self.assertFalse(
            form.fields["is_public"].disabled,
            "Public visibility must be editable by an administrator.",
        )

        result = {}

        for current in (form, origin_form):
            for name, field in current.fields.items():
                if field.disabled:
                    continue

                html_name = current.add_prefix(name)
                value = current[name].value()

                if isinstance(
                    field,
                    (
                        forms.ModelMultipleChoiceField,
                        forms.MultipleChoiceField,
                    ),
                ):
                    result[html_name] = [
                        str(item)
                        for item in (value or [])
                    ]

                elif isinstance(field, forms.BooleanField):
                    if value:
                        result[html_name] = "on"

                else:
                    result[html_name] = (
                        "" if value is None else str(value)
                    )

        result["storage_edit_intent"] = "0"
        result["storage_initial_paths"] = (
            response.context.get("current_storage_location") or ""
        )
        result["keyword_pairs_text"] = ""

        return result

    @staticmethod
    def _details(response):
        context = response.context

        if context is None:
            return (
                f"status={response.status_code} "
                f"location={response.get('Location', '')}"
            )

        form = context.get("form")
        origin = context.get("origin_form")

        return (
            f"status={response.status_code} "
            f"location={response.get('Location', '')} "
            f"form_errors={dict(form.errors) if form else None} "
            f"origin_errors={dict(origin.errors) if origin else None}"
        )

    def test_valid_public_edit_is_persisted(self):
        payload = self._payload()
        payload["is_public"] = "on"

        response = self.client.post(self.url, payload)

        self.assertEqual(
            response.status_code,
            302,
            self._details(response),
        )
        self.assertEqual(
            response["Location"],
            reverse("samples_list"),
        )

        self.sample.refresh_from_db()

        self.assertTrue(
            self.sample.is_public,
            "Successful redirect without persisted Public visibility.",
        )
        self.assertEqual(self.sample.status, "qc")
        self.assertFalse(self.sample.is_embargoed)

    def test_invalid_public_edit_does_not_save(self):
        payload = self._payload()
        payload["is_public"] = "on"

        # Force a genuinely invalid ChoiceField value.
        # Changing Public by itself is a valid operation.
        self.assertIn(
            "biosafety_level",
            self.client.get(self.url).context["form"].fields,
        )
        payload["biosafety_level"] = "INVALID-BIOSAFETY-VALUE"

        response = self.client.post(self.url, payload)

        self.assertEqual(
            response.status_code,
            200,
            self._details(response),
        )
        self.assertIn(
            "biosafety_level",
            response.context["form"].errors,
        )
        self.assertContains(
            response,
            "sample-edit-validation-summary",
        )

        self.sample.refresh_from_db()
        self.assertFalse(self.sample.is_public)
        self.assertEqual(self.sample.status, "qc")
