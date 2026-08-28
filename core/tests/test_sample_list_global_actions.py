from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class SampleListGlobalActionsTests(
    SimpleTestCase
):
    def setUp(self):
        self.template = (
            Path(settings.BASE_DIR)
            / "core"
            / "interfaces"
            / "internal"
            / "samples"
            / "list.html"
        ).read_text()

    def test_micro_qr_lookup_is_global_action_only(
        self,
    ):
        lookup = (
            "{% url 'sample_micro_qr_lookup' %}"
        )

        manage_actions = (
            self.template
            .split(
                "{% block manage_actions %}",
                1,
            )[1]
            .split(
                "{% endblock %}",
                1,
            )[0]
        )

        table_body = (
            self.template
            .split(
                "{% block table_body %}",
                1,
            )[1]
            .split(
                "{% endblock %}",
                1,
            )[0]
        )

        self.assertEqual(
            self.template.count(
                lookup
            ),
            1,
        )

        self.assertIn(
            lookup,
            manage_actions,
        )

        self.assertIn(
            "Micro QR Lookup",
            manage_actions,
        )

        self.assertIn(
            "bi bi-qr-code-scan",
            manage_actions,
        )

        self.assertNotIn(
            lookup,
            table_body,
        )

    def test_sample_inventory_header_matches_section_style(
        self,
    ):
        manage_title = (
            self.template
            .split(
                "{% block manage_title %}",
                1,
            )[1]
            .split(
                "{% endblock %}",
                1,
            )[0]
        )

        manage_subtitle = (
            self.template
            .split(
                "{% block manage_subtitle %}",
                1,
            )[1]
            .split(
                "{% endblock %}",
                1,
            )[0]
        )

        self.assertIn(
            "Sample Inventory",
            manage_title,
        )

        self.assertIn(
            "bi bi-droplet text-primary",
            manage_title,
        )

        self.assertNotIn(
            "me-2",
            manage_title,
        )

        self.assertEqual(
            manage_subtitle.strip(),
            "",
        )

        self.assertIn(
            "font-size: 22px;",
            self.template,
        )

        self.assertIn(
            "font-weight: 800;",
            self.template,
        )

        self.assertIn(
            "color: #0f172a;",
            self.template,
        )

        self.assertIn(
            "gap: 10px;",
            self.template,
        )

        self.assertIn(
            "margin-bottom: 18px !important;",
            self.template,
        )
