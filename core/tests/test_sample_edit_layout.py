from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.forms import (
    BacteriaForm,
    PhageForm,
    PlasmidForm,
    SampleForm,
)
from core.models import Sample
from core.views.internal.samples.views import (
    SAMPLE_EDIT_NON_BIOLOGICAL_FIELD_NAMES,
    _sample_edit_biological_fields,
)


User = get_user_model()


class SampleEditLayoutTests(
    TestCase
):
    template_path = Path(
        "core/interfaces/internal/samples/edit.html"
    )

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="sample-layout-owner",
        )

        cls.sample = Sample.objects.create(
            sample_id="LAYOUT-001",
            sample_type="Other",
            organism_name="Layout Sample",
            owner=cls.owner,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
        )

    @staticmethod
    def client_path(
        url,
    ):
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
            and url.startswith(prefix)
        ):
            return (
                url[
                    len(prefix):
                ]
                or "/"
            )

        return url

    @classmethod
    def template_text(
        cls,
    ):
        return cls.template_path.read_text()

    def test_sample_form_base_fields_have_explicit_presentation_contract(
        self,
    ):
        text = self.template_text()

        explicit_form_fields = (
            "sample_id",
            "sample_type",
            "biosafety_level",
            "aliquot_count",
            "owner",
            "research_group",
            "biobank",
            "collections",
            "is_public",
            "is_embargoed",
            "notes",
        )

        for field_name in explicit_form_fields:
            with self.subTest(
                field=field_name
            ):
                self.assertIn(
                    f"form.{field_name}",
                    text,
                )

        self.assertIn(
            "sample.organism_name",
            text,
        )

        self.assertIn(
            "sample.get_status_display",
            text,
        )

        self.assertIn(
            'name="storage_location"',
            text,
        )

        self.assertIn(
            'name="scientific_notes"',
            text,
        )

    def test_standard_edit_does_not_render_status_select(
        self,
    ):
        text = self.template_text()

        self.assertNotIn(
            "{{ form.status }}",
            text,
        )

        self.assertIn(
            "Workflow-managed. Standard metadata editing",
            text,
        )

    def test_base_sample_has_no_unclassified_biological_fields(
        self,
    ):
        form = SampleForm()

        actual = tuple(
            field.name
            for field in _sample_edit_biological_fields(
                form
            )
        )

        self.assertEqual(
            actual,
            (),
        )

    def test_subtype_biological_field_grouping_is_complete(
        self,
    ):
        for form_class in (
            BacteriaForm,
            PhageForm,
            PlasmidForm,
        ):
            with self.subTest(
                form=form_class.__name__
            ):
                form = form_class()

                expected = tuple(
                    name
                    for name in form.fields
                    if name
                    not in SAMPLE_EDIT_NON_BIOLOGICAL_FIELD_NAMES
                )

                actual = tuple(
                    field.name
                    for field in _sample_edit_biological_fields(
                        form
                    )
                )

                self.assertEqual(
                    actual,
                    expected,
                )

                self.assertTrue(
                    actual,
                )

    def test_biological_properties_loop_is_structurally_explicit(
        self,
    ):
        text = self.template_text()

        self.assertIn(
            "{% if biological_fields %}",
            text,
        )

        self.assertIn(
            "{% for field in biological_fields %}",
            text,
        )

        self.assertNotIn(
            "forloop.first or forloop.counter0 == 0",
            text,
        )

    def test_standardized_section_matrix_is_complete(
        self,
    ):
        text = self.template_text()

        expected_sections = (
            "identity",
            "inventory",
            "governance",
            "biological-properties",
            "relationships",
            "traceability",
            "origin",
            "metadata",
            "scientific-notes",
            "files",
        )

        for section in expected_sections:
            with self.subTest(
                section=section
            ):
                self.assertIn(
                    (
                        'data-sample-edit-section="'
                        f'{section}"'
                    ),
                    text,
                )

    def test_origin_provenance_partial_is_preserved(
        self,
    ):
        text = self.template_text()

        self.assertIn(
            (
                '{% include '
                '"internal/samples/_origin_fields.html" %}'
            ),
            text,
        )

    def test_relationship_controls_are_preserved(
        self,
    ):
        text = self.template_text()

        for token in (
            "host_bacterium[]",
            "stored_plasmids[]",
            "infecting_phages[]",
            "allSamplesListForJS",
            "biologicalRelationshipsSection",
        ):
            with self.subTest(
                token=token
            ):
                self.assertIn(
                    token,
                    text,
                )

        # Notes controls are generated dynamically from the primary
        # relationship field name. Verify the JavaScript producer
        # contract instead of requiring generated names to appear as
        # literal template strings.
        self.assertIn(
            "nameParam.replace('[]', '_notes[]')",
            text,
        )

        # Verify that the backend consumes exactly the names generated
        # by that JavaScript contract.
        view_text = Path(
            "core/views/internal/samples/views.py"
        ).read_text()

        for token in (
            "host_bacterium_notes[]",
            "stored_plasmids_notes[]",
            "infecting_phages_notes[]",
        ):
            with self.subTest(
                backend_notes_token=token
            ):
                self.assertIn(
                    f'getlist("{token}")',
                    view_text,
                )

    def test_metadata_eln_and_file_controls_are_preserved(
        self,
    ):
        text = self.template_text()

        for token in (
            'name="tags"',
            'name="keyword_pairs_text"',
            'id="scientific_notes_input"',
            'id="eln-editor"',
            'name="remove_file_ids"',
            'id="fileContainer"',
            'id="addFileBtn"',
            'name="file"',
            'name="file_category"',
            'name="file_description"',
        ):
            with self.subTest(
                token=token
            ):
                self.assertIn(
                    token,
                    text,
                )

    def test_edit_view_renders_standardized_layout_and_context(
        self,
    ):
        self.client.force_login(
            self.owner
        )

        response = self.client.get(
            self.client_path(
                reverse(
                    "sample_edit",
                    args=[
                        self.sample.pk,
                    ],
                )
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            tuple(
                response.context[
                    "biological_fields"
                ]
            ),
            (),
        )

        self.assertContains(
            response,
            'data-sample-edit-layout="v1"',
        )

        self.assertContains(
            response,
            "Identity & Workflow",
        )

        self.assertContains(
            response,
            "Inventory & Biosafety",
        )

        self.assertContains(
            response,
            "Governance & Access",
        )

        self.assertContains(
            response,
            "Quality Control",
        )

        self.assertNotContains(
            response,
            'name="status"',
        )
