import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import (
    JupyterNotebook,
    NotebookEntry,
    NotebookKernelDocument,
)
from core.services.jupyter_sessions import (
    starter_notebook,
)


@override_settings(
    FORCE_SCRIPT_NAME=None,
    BIOBANK_JUPYTER_PARTITION="basic",
    BIOBANK_JUPYTER_PARTITIONS=("basic", "max50"),
    BIOBANK_JUPYTER_DEFAULT_CPUS=2,
    BIOBANK_JUPYTER_DEFAULT_MEMORY_MB=8192,
    BIOBANK_JUPYTER_DEFAULT_TIME_MINUTES=60,
)
class IndependentJupyterViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="jupyter-view-owner",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="jupyter-view-other",
            password="test-password",
        )

        self.client.force_login(self.owner)

    def test_index_uses_independent_notebook_list(self):
        notebook = JupyterNotebook.objects.create(
            title="Independent analysis",
            owner=self.owner,
            updated_by=self.owner,
            notebook_json=starter_notebook(
                "Independent analysis",
                self.owner.get_username(),
            ),
        )

        response = self.client.get(
            reverse("jupyter_index")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            notebook.title,
        )
        self.assertTemplateUsed(
            response,
            "internal/lab_tools/jupyter_index.html",
        )

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "start_session"
    )
    def test_launch_creates_no_eln_note(
        self,
        mocked_start_session,
    ):
        response = self.client.post(
            reverse("jupyter_launch"),
            {
                "title": "Cluster analysis",
                "partition": "basic",
                "cpus": "4",
                "memory_mb": "16384",
                "hours": "2",
            },
        )

        notebook = JupyterNotebook.objects.get(
            title="Cluster analysis"
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            response.url,
            reverse(
                "jupyter_workspace",
                args=[notebook.id],
            ),
        )
        self.assertEqual(
            NotebookEntry.objects.count(),
            0,
        )

        mocked_start_session.assert_called_once_with(
            notebook,
            self.owner,
            cpus=4,
            memory_mb=16384,
            time_minutes=120,
            partition="basic",
        )

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "active_session_for_notebook",
        return_value=None,
    )
    def test_owner_can_open_workspace(
        self,
        mocked_active_session,
    ):
        notebook = JupyterNotebook.objects.create(
            title="Owner workspace",
            owner=self.owner,
            updated_by=self.owner,
            notebook_json=starter_notebook(
                "Owner workspace",
                self.owner.get_username(),
            ),
        )

        response = self.client.get(
            reverse(
                "jupyter_workspace",
                args=[notebook.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Start session",
        )
        mocked_active_session.assert_called_once()

    def test_other_user_cannot_open_workspace(self):
        notebook = JupyterNotebook.objects.create(
            title="Private workspace",
            owner=self.owner,
            updated_by=self.owner,
            notebook_json=starter_notebook(
                "Private workspace",
                self.owner.get_username(),
            ),
        )

        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse(
                "jupyter_workspace",
                args=[notebook.id],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_document_api_saves_independent_notebook(self):
        notebook = JupyterNotebook.objects.create(
            title="Before save",
            owner=self.owner,
            updated_by=self.owner,
            notebook_json=starter_notebook(
                "Before save",
                self.owner.get_username(),
            ),
        )

        payload = starter_notebook(
            "After save",
            self.owner.get_username(),
        )

        response = self.client.post(
            reverse(
                "jupyter_document_api",
                args=[notebook.id],
            ),
            data=json.dumps(
                {
                    "title": "After save",
                    "notebook": payload,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        notebook.refresh_from_db()

        self.assertEqual(
            notebook.title,
            "After save",
        )
        self.assertEqual(
            notebook.notebook_json["nbformat"],
            4,
        )

    def test_legacy_jupyter_entry_is_hidden_from_notes_list(self):
        entry = NotebookEntry.objects.create(
            title="Legacy Jupyter entry",
            author=self.owner,
            entry_type="analysis",
            status="draft",
            visibility="private",
        )

        NotebookKernelDocument.objects.create(
            entry=entry,
            title=entry.title,
            notebook_json=starter_notebook(
                entry.title,
                self.owner.get_username(),
            ),
            updated_by=self.owner,
        )

        response = self.client.get(
            reverse("notebook_index")
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            entry.title,
        )
