from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.lab_tools.notebook import NotebookEntry
from core.views.internal.lab_tools.notebook import (
    _notebook_entry_templates,
)



def request_path(name):
    path = reverse(name)
    script_name = settings.FORCE_SCRIPT_NAME or ""

    if script_name and path.startswith(script_name):
        return path[len(script_name):] or "/"

    return path


class ELNTemplateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eln-template-owner",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_template_catalog_contains_supported_workflows(self):
        templates = _notebook_entry_templates()

        self.assertEqual(
            list(templates),
            [
                "blank",
                "experiment",
                "protocol",
                "analysis",
                "sample_characterization",
                "plasmid_construction",
                "lab_report",
                "pcr",
                "cell_culture",
                "meeting",
                "sequencing_bioinformatics",
            ],
        )

        for template in templates.values():
            self.assertIn("label", template)
            self.assertIn("description", template)
            self.assertIn("entry_type", template)
            self.assertIn("content", template)
            self.assertIn("protocol_content", template)

    def test_general_experiment_is_created_with_structure(self):
        response = self.client.get(
            request_path("notebook_create")
            + "?template=experiment"
        )

        entry = NotebookEntry.objects.get(
            author=self.user
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(entry.entry_type, "experiment")
        self.assertIn("<h2>Objective</h2>", entry.content)
        self.assertIn("<h2>Results</h2>", entry.content)
        self.assertIn("<h2>Conclusion</h2>", entry.content)
        self.assertIn("Materials", entry.protocol_content)
        self.assertIn("Quality criteria", entry.protocol_content)

    def test_blank_template_remains_empty(self):
        self.client.get(
            request_path("notebook_create")
            + "?template=blank"
        )

        entry = NotebookEntry.objects.get(
            author=self.user
        )

        self.assertEqual(entry.entry_type, "other")
        self.assertEqual(entry.content, "")
        self.assertEqual(entry.protocol_content, "")

    def test_plasmid_template_contains_design_workflow(self):
        self.client.get(
            request_path("notebook_create")
            + "?template=plasmid_construction"
        )

        entry = NotebookEntry.objects.get(
            author=self.user
        )

        self.assertIn("Design objective", entry.content)
        self.assertIn("Assembly strategy", entry.content)
        self.assertIn("Sequence validation", entry.content)
        self.assertIn("Screening plan", entry.protocol_content)



class ELNStructuredLayoutTests(TestCase):
    def test_every_layout_has_real_structure_and_survives_sanitising(self):
        from core.services.notebook_html import sanitize_notebook_html
        from core.services.notebook_layouts import LAYOUTS, layout_html

        for key in LAYOUTS:
            html = layout_html(key)

            self.assertIn("<h2>", html, key)
            self.assertIn("<table", html, key)
            self.assertIn('class="b3-hint"', html, key)
            clean = sanitize_notebook_html(html)
            self.assertEqual(clean.count("<table"), html.count("<table"), key)
            self.assertIn("b3-tpl", clean, key)

    def test_lab_report_follows_the_protocol_template_sections(self):
        from core.services.notebook_layouts import layout_html

        html = layout_html("lab_report")

        for heading in (
            "Objective", "Theoretical background", "Materials and equipment",
            "Experimental procedure", "Results and measurements", "Discussion",
            "Conclusion", "References", "Appendix",
        ):
            self.assertIn(f"<h2>{heading}</h2>", html)


class ELNToolsPanelTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user("tools-user", password="x")
        self.client.force_login(self.user)

    def test_entry_page_loads_the_tools_drawer(self):
        entry = NotebookEntry.objects.create(title="Tools", author=self.user)
        response = self.client.get(reverse("notebook_entry", args=[entry.id]))

        self.assertContains(response, 'id="bx-tools"')
        self.assertContains(response, "eln_tools_calc.js")
        self.assertContains(response, "eln_tools.js")
        self.assertContains(response, "eln_tools.css")
        self.assertContains(response, "eln_elements.js")

    def test_calculator_logic_and_scripts_are_valid(self):
        import shutil
        import subprocess
        from pathlib import Path

        from django.conf import settings

        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")

        base = Path(settings.BASE_DIR, "core")
        for script, marker in (
            (base / "tests/js/test_eln_tools_calc.cjs", "eln calc ok"),
            (base / "tests/js/test_eln_elements.cjs", "eln elements ok"),
        ):
            result = subprocess.run([node, str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(marker, result.stdout)

        check = subprocess.run(
            [node, "--check", str(base / "static/internal/lab_tools/eln_tools.js")],
            capture_output=True, text=True,
        )
        self.assertEqual(check.returncode, 0, check.stderr)
