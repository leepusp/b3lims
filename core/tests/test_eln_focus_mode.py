from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models.lab_tools.notebook import (
    NotebookEntry,
)


def request_path(name, args=None):
    path = reverse(name, args=args)
    script_name = settings.FORCE_SCRIPT_NAME or ""

    if script_name and path.startswith(script_name):
        return path[len(script_name):] or "/"

    return path


class ELNFocusModeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="eln-focus-mode",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_active_entry_exposes_all_layout_controls(self):
        entry = NotebookEntry.objects.create(
            title="Focus mode experiment",
            author=self.user,
            entry_type="experiment",
            status="draft",
            visibility="private",
        )

        response = self.client.get(
            request_path("notebook_index"),
            {"entry_id": entry.id},
        )

        self.assertEqual(response.status_code, 200)

        for identifier in [
            'id="eln-notebook-shell"',
            'id="eln-entries-panel"',
            'id="linked-experiment-context"',
            'id="eln-toggle-entries"',
            'id="eln-toggle-context"',
            'id="eln-toggle-focus"',
        ]:
            with self.subTest(identifier=identifier):
                self.assertContains(
                    response,
                    identifier,
                )

        self.assertContains(
            response,
            'data-has-active-entry="true"',
        )
        self.assertContains(
            response,
            "Focus",
        )
        self.assertContains(
            response,
            "Linked",
        )

    def test_empty_state_disables_context_control(self):
        response = self.client.get(
            request_path("notebook_index")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-has-active-entry="false"',
        )
        self.assertContains(
            response,
            'id="eln-toggle-context"',
        )
        self.assertContains(
            response,
            'disabled aria-disabled="true"',
        )
        self.assertNotContains(
            response,
            'id="linked-experiment-context"',
        )

    def test_template_persists_and_restores_layout(self):
        template = Path(
            settings.BASE_DIR,
            "core/interfaces/internal/lab_tools/"
            "notebook.html",
        ).read_text()

        required_markers = [
            ".notebook-shell.eln-entries-collapsed",
            ".notebook-shell.eln-context-collapsed",
            "biobank.eln.workspace-layout.v1",
            "window.localStorage.getItem",
            "window.localStorage.setItem",
            "window.toggleElnPanel",
            "window.toggleElnFocusMode",
            'shell.classList.toggle(',
            '"eln-entries-collapsed"',
            '"eln-context-collapsed"',
            'label.textContent = (',
        ]

        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, template)
