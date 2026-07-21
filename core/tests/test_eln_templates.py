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

    def test_template_menu_is_visible_in_eln(self):
        NotebookEntry.objects.create(
            title="Existing experiment",
            author=self.user,
            entry_type="experiment",
            status="draft",
            visibility="private",
        )

        response = self.client.get(
            request_path("notebook_index")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Choose a notebook template",
        )
        self.assertContains(
            response,
            "General experiment",
        )
        self.assertContains(
            response,
            "Sample characterization",
        )
        self.assertContains(
            response,
            "Plasmid construction",
        )
        self.assertContains(
            response,
            "Sequencing / bioinformatics",
        )
        self.assertContains(
            response,
            "?template=plasmid_construction",
        )
