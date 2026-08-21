from django.conf import settings
from django.contrib.auth import get_user_model
from django.forms import CheckboxInput
from django.test import TestCase
from django.urls import reverse

from core.forms import SampleForm
from core.models import Sample, Tag
from core.services.metadata_vocabularies import (
    get_or_create_active_keyword_value,
)


class SampleEditMetadataTests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="editmetadataowner",
            password="test-password",
        )

        self.sample = Sample.objects.create(
            sample_id="EDIT-METADATA-001",
            sample_type="Other",
            organism_name="Metadata Test Sample",
            owner=self.owner,
            status="available",
            aliquot_count=1,
            is_active=True,
            is_public=False,
        )

        self.client.force_login(
            self.owner
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

    def edit_url(self):
        return self.client_path(
            reverse(
                "sample_edit",
                args=[
                    self.sample.pk
                ],
            )
        )

    def current_form_data(self):
        form = SampleForm(
            instance=self.sample,
            user=self.owner,
        )

        data = {}

        for name, field in form.fields.items():

            if field.disabled:
                continue

            value = form[name].value()

            if isinstance(
                field.widget,
                CheckboxInput,
            ):
                if value:
                    data[name] = "on"

                continue

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

            else:
                data[name] = str(
                    value
                )

        return data

    def test_edit_page_exposes_metadata_controls(self):
        response = self.client.get(
            self.edit_url()
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Internal Notes",
        )

        self.assertContains(
            response,
            "Metadata & Classification",
        )

        self.assertContains(
            response,
            "Custom Keywords",
        )

        self.assertContains(
            response,
            'name="tags"',
        )

        self.assertContains(
            response,
            'name="keyword_pairs_text"',
        )

        self.assertNotContains(
            response,
            'name="collaborator"',
        )

    def test_edit_updates_notes_tags_and_keywords(self):
        tag = Tag.objects.create(
            name="Metadata Test Tag"
        )

        data = self.current_form_data()

        data.update({
            "notes": (
                "Private operational note."
            ),
            "tags": [
                str(
                    tag.pk
                )
            ],
            "keyword_pairs_text": (
                "Target Gene: eGFP\n"
                "Expression System: T7"
            ),
        })

        response = self.client.post(
            self.edit_url(),
            data=data,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.sample.refresh_from_db()

        self.assertEqual(
            self.sample.notes,
            "Private operational note.",
        )

        self.assertTrue(
            self.sample.tags.filter(
                pk=tag.pk
            ).exists()
        )

        pairs = set(
            self.sample.keywords
            .values_list(
                "keyword__name",
                "value",
            )
        )

        self.assertEqual(
            pairs,
            {
                (
                    "Target Gene",
                    "eGFP",
                ),
                (
                    "Expression System",
                    "T7",
                ),
            },
        )

    def test_edit_can_clear_all_tags_and_keywords(self):
        tag = Tag.objects.create(
            name="Tag To Clear"
        )

        keyword_value, _ = (
            get_or_create_active_keyword_value(
                "Host",
                "E. coli",
            )
        )

        self.sample.tags.add(
            tag
        )

        self.sample.keywords.add(
            keyword_value
        )

        data = self.current_form_data()

        data["notes"] = ""
        data["tags"] = []
        data["keyword_pairs_text"] = ""

        response = self.client.post(
            self.edit_url(),
            data=data,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            self.sample.tags.count(),
            0,
        )

        self.assertEqual(
            self.sample.keywords.count(),
            0,
        )

    def test_invalid_keyword_does_not_save_sample(self):
        original_name = (
            self.sample.organism_name
        )

        data = self.current_form_data()

        data["organism_name"] = (
            "Should Not Be Saved"
        )

        data["keyword_pairs_text"] = (
            "invalid keyword line"
        )

        response = self.client.post(
            self.edit_url(),
            data=data,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            (
                "Custom keyword line 1 must use "
                "the format Key: Value."
            ),
        )

        self.sample.refresh_from_db()

        self.assertEqual(
            self.sample.organism_name,
            original_name,
        )
