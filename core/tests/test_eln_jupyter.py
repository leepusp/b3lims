import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models.lab_tools.notebook import (
    NotebookEntry,
    NotebookKernelDocument,
    NotebookKernelExecution,
)
from core.services.jupyter_notebooks import normalize_notebook


def request_path(name, args=None):
    return reverse(name, args=args).removeprefix("/biobank")


class ElnJupyterTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workspace = tempfile.TemporaryDirectory()
        cls.settings_override = override_settings(
            FORCE_SCRIPT_NAME=None,
            BIOBANK_JUPYTER_NOTEBOOK_ROOT=str(
                Path(cls.workspace.name, "notebooks")
            ),
            BIOBANK_JUPYTER_JOB_ROOT=str(
                Path(cls.workspace.name, "jobs")
            ),
        )
        cls.settings_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings_override.disable()
        cls.workspace.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="eln-jupyter-owner",
            password="test-password",
        )
        self.admin = get_user_model().objects.create_superuser(
            username="eln-jupyter-admin",
            password="test-password",
            email="admin@example.invalid",
        )
        self.entry = NotebookEntry.objects.create(
            title="ELN Jupyter experiment",
            author=self.owner,
        )
        self.notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": "intro",
                    "metadata": {},
                    "source": "# Analysis",
                },
                {
                    "cell_type": "code",
                    "id": "calculation",
                    "metadata": {},
                    "source": "print(sum([2, 3, 5, 7]))",
                    "execution_count": None,
                    "outputs": [],
                },
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }

    def test_notebook_page_exposes_native_jupyter_cells(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            request_path("notebook_index")
            + f"?entry_id={self.entry.id}&tab=jupyter"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="jupyter-tab"')
        self.assertContains(response, 'id="jupyter-pane"')
        self.assertContains(response, 'id="eln-jupyter-workspace"')
        self.assertContains(response, "internal/lab_tools/notebook_jupyter.css")
        self.assertContains(response, "internal/lab_tools/notebook_jupyter.js")
        self.assertContains(response, 'data-can-execute="true"')
        self.assertContains(
            response,
            reverse("notebook_jupyter_workspace", args=[self.entry.id]),
        )

    def test_owner_can_save_and_download_ipynb(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            request_path("notebook_jupyter_document_api", [self.entry.id]),
            data=json.dumps(
                {
                    "title": "Read count analysis",
                    "notebook": self.notebook,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        document = NotebookKernelDocument.objects.get(entry=self.entry)
        self.assertEqual(document.title, "Read count analysis")
        self.assertEqual(len(document.notebook_json["cells"]), 2)

        stored = Path(
            settings.BIOBANK_JUPYTER_NOTEBOOK_ROOT,
            f"entry_{self.entry.id}",
            f"document_{document.id}.ipynb",
        )
        self.assertTrue(stored.exists())

        download = self.client.get(
            request_path("notebook_jupyter_download", [self.entry.id])
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "application/x-ipynb+json")
        self.assertIn(".ipynb", download["Content-Disposition"])

    def test_owner_can_submit_managed_execution(self):
        document = NotebookKernelDocument.objects.create(
            entry=self.entry,
            title="Owner execution",
            notebook_json=normalize_notebook(self.notebook),
            created_by=self.owner,
            updated_by=self.owner,
        )

        def fake_submit(document_arg, user, **resources):
            return NotebookKernelExecution.objects.create(
                document=document_arg,
                submitted_by=user,
                job_id="40000",
                run_id="owner_run_40000",
                status="submitted",
                cpus=resources["cpus"],
                memory_mb=resources["memory_mb"],
                time_minutes=resources["time_minutes"],
                source_path="/tmp/source.ipynb",
                run_directory="/tmp/run",
                result_path="/tmp/run/executed.ipynb",
            )

        self.client.force_login(self.owner)
        with patch(
            "core.views.internal.lab_tools.notebook.submit_document",
            side_effect=fake_submit,
        ):
            response = self.client.post(
                request_path("notebook_jupyter_submit_api", [self.entry.id]),
                data="{}",
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        execution = NotebookKernelExecution.objects.get(document=document)
        self.assertEqual(execution.submitted_by, self.owner)

    def test_launch_creates_workspace_starter_cells_and_default_job(self):
        def fake_submit(document_arg, user, **resources):
            return NotebookKernelExecution.objects.create(
                document=document_arg,
                submitted_by=user,
                job_id="40002",
                run_id="launch_run_40002",
                status="submitted",
                cpus=resources["cpus"],
                memory_mb=resources["memory_mb"],
                time_minutes=resources["time_minutes"],
                source_path="/tmp/source.ipynb",
                run_directory="/tmp/run",
                result_path="/tmp/run/executed.ipynb",
            )

        self.client.force_login(self.owner)
        with patch(
            "core.views.internal.lab_tools.notebook.submit_document",
            side_effect=fake_submit,
        ):
            response = self.client.post(
                request_path("notebook_jupyter_launch")
            )

        entry = NotebookEntry.objects.exclude(pk=self.entry.pk).get()
        document = entry.kernel_document
        execution = document.executions.get()

        self.assertRedirects(
            response,
            request_path("notebook_jupyter_workspace", [entry.id]),
        )
        self.assertEqual(entry.entry_type, "analysis")
        self.assertEqual(len(document.notebook_json["cells"]), 3)
        self.assertEqual(execution.submitted_by, self.owner)
        self.assertEqual(execution.cpus, settings.BIOBANK_JUPYTER_DEFAULT_CPUS)

    def test_dedicated_workspace_is_full_width_and_linked_to_eln(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            request_path("notebook_jupyter_workspace", [self.entry.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "eln-jupyter-standalone")
        self.assertContains(response, 'data-standalone="true"')
        self.assertContains(response, 'data-can-execute="true"')
        self.assertContains(response, "Back to ELN")

    def test_superuser_submission_is_audited(self):
        document = NotebookKernelDocument.objects.create(
            entry=self.entry,
            title="Managed execution",
            notebook_json=normalize_notebook(self.notebook),
            created_by=self.owner,
            updated_by=self.owner,
        )

        def fake_submit(document_arg, user, **resources):
            return NotebookKernelExecution.objects.create(
                document=document_arg,
                submitted_by=user,
                job_id="40001",
                run_id="test_run_40001",
                status="submitted",
                requested_cell_index=resources.get("cell_index"),
                cpus=resources["cpus"],
                memory_mb=resources["memory_mb"],
                time_minutes=resources["time_minutes"],
                source_path="/tmp/source.ipynb",
                run_directory="/tmp/run",
                result_path="/tmp/run/executed.ipynb",
            )

        self.client.force_login(self.admin)
        with patch(
            "core.views.internal.lab_tools.notebook.submit_document",
            side_effect=fake_submit,
        ):
            response = self.client.post(
                request_path("notebook_jupyter_submit_api", [self.entry.id]),
                data=json.dumps(
                    {
                        "cpus": 4,
                        "memory_mb": 16384,
                        "time_minutes": 120,
                        "cell_index": 1,
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        execution = NotebookKernelExecution.objects.get(document=document)
        self.assertEqual(execution.submitted_by, self.admin)
        self.assertEqual(execution.job_id, "40001")
        self.assertEqual(execution.requested_cell_index, 1)
        self.assertEqual(execution.cpus, 4)

    def test_html_outputs_are_not_persisted_as_executable_markup(self):
        notebook = dict(self.notebook)
        notebook["cells"] = [
            {
                "cell_type": "code",
                "id": "unsafe-output",
                "metadata": {},
                "source": "display('result')",
                "execution_count": 1,
                "outputs": [
                    {
                        "output_type": "display_data",
                        "data": {
                            "text/html": "<script>alert(1)</script>",
                            "text/plain": "safe result",
                        },
                        "metadata": {},
                    }
                ],
            }
        ]

        normalized = normalize_notebook(notebook)
        data = normalized["cells"][0]["outputs"][0]["data"]
        self.assertNotIn("text/html", data)
        self.assertEqual(data["text/plain"], "safe result")
