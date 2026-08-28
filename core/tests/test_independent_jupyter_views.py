import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import (
    get_script_prefix,
    reverse,
    set_script_prefix,
)

from core.models.lab_tools.notebook import (
    JupyterNotebook,
    NotebookEntry,
)
from core.services.jupyter_documents import (
    JupyterNotebookError,
)
from core.services.jupyter_server import (
    starter_notebook,
)


@override_settings(
    FORCE_SCRIPT_NAME=None,
    BIOBANK_JUPYTER_PARTITION="basic",
    BIOBANK_JUPYTER_PARTITIONS=("basic", "max50"),
    BIOBANK_JUPYTER_NODES=("n01", "gn01", "gn02", "gn03"),
    BIOBANK_JUPYTER_PARTITION_MAX_HOURS={
        "basic": 72,
        "max50": 168,
    },
    BIOBANK_JUPYTER_DEFAULT_CPUS=2,
    BIOBANK_JUPYTER_DEFAULT_MEMORY_MB=8192,
    BIOBANK_JUPYTER_DEFAULT_TIME_MINUTES=60,
    BIOBANK_JUPYTERLAB_OOD_LAUNCH_URL=(
        "https://davinci.example/pun/sys/dashboard/"
        "batch_connect/sys/jupyterlab/session_contexts/new"
    ),
)
class IndependentJupyterViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls._original_script_prefix = (
            get_script_prefix()
        )
        set_script_prefix("/")

        cls.addClassCleanup(
            set_script_prefix,
            cls._original_script_prefix,
        )

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
                "node": "gn03",
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
            node="gn03",
        )

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "start_session"
    )
    def test_launch_does_not_show_redundant_submission_banner(
        self,
        mocked_start_session,
    ):
        response = self.client.post(
            reverse("jupyter_launch"),
            {
                "title": "Quiet cluster analysis",
                "partition": "basic",
                "node": "gn03",
                "cpus": "2",
                "memory_mb": "8192",
                "hours": "1",
            },
            follow=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertNotContains(
            response,
            "Persistent Jupyter session submitted to Slurm.",
        )

        mocked_start_session.assert_called_once()

    def test_launch_form_exposes_compute_node_selection(self):
        response = self.client.get(
            reverse("jupyter_launch")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Automatic (Slurm decides)",
        )
        for node in ("n01", "gn01", "gn02", "gn03"):
            self.assertContains(
                response,
                f'value="{node}"',
            )

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "start_session"
    )
    def test_launch_rejects_unknown_compute_node(
        self,
        mocked_start_session,
    ):
        response = self.client.post(
            reverse("jupyter_launch"),
            {
                "title": "Invalid node",
                "partition": "basic",
                "node": "gn03;id",
                "cpus": "2",
                "memory_mb": "8192",
                "hours": "1",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "Invalid compute node.",
            status_code=400,
        )
        self.assertFalse(
            JupyterNotebook.objects.filter(
                title="Invalid node"
            ).exists()
        )
        mocked_start_session.assert_not_called()

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "start_session"
    )
    def test_basic_partition_rejects_more_than_72_hours(
        self,
        mocked_start_session,
    ):
        response = self.client.post(
            reverse("jupyter_launch"),
            {
                "title": "Too long",
                "partition": "basic",
                "node": "auto",
                "cpus": "2",
                "memory_mb": "8192",
                "hours": "73",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            "1 and 72 hours for basic",
            status_code=400,
        )
        mocked_start_session.assert_not_called()

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

    def test_index_exposes_download_action(self):
        notebook = JupyterNotebook.objects.create(
            title="Downloadable notebook",
            owner=self.owner,
            updated_by=self.owner,
            notebook_json=starter_notebook(
                "Downloadable notebook",
                self.owner.get_username(),
            ),
        )

        response = self.client.get(
            reverse("jupyter_index")
        )

        self.assertContains(
            response,
            reverse(
                "jupyter_download",
                args=[notebook.id],
            ),
        )

    def test_owner_can_delete_independent_notebook(self):
        notebook = JupyterNotebook.objects.create(
            title="Delete notebook",
            owner=self.owner,
            updated_by=self.owner,
            notebook_json=starter_notebook(
                "Delete notebook",
                self.owner.get_username(),
            ),
        )

        session = notebook.sessions.create(
            started_by=self.owner,
            job_id="99881",
            run_id="delete_notebook_session",
            status="running",
            partition="basic",
            cpus=2,
            memory_mb=2048,
            time_minutes=60,
            run_directory="/tmp/delete-notebook-session",
        )

        with patch(
            "core.views.internal.lab_tools.jupyter."
            "stop_session",
            return_value=session,
        ) as mocked_stop, patch(
            "core.views.internal.lab_tools.jupyter."
            "delete_notebook_workspace",
            return_value=True,
        ) as mocked_delete_workspace:
            response = self.client.post(
                reverse(
                    "jupyter_delete",
                    args=[notebook.id],
                )
            )

        self.assertRedirects(
            response,
            reverse("jupyter_index"),
        )
        self.assertFalse(
            JupyterNotebook.objects.filter(
                pk=notebook.id
            ).exists()
        )
        mocked_stop.assert_called_once()
        mocked_delete_workspace.assert_called_once()

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "delete_notebook_workspace",
        return_value=True,
    )
    @patch(
        "core.views.internal.lab_tools.jupyter."
        "start_session",
        side_effect=JupyterNotebookError(
            "Submission failed."
        ),
    )
    def test_failed_new_launch_removes_workspace_and_record(
        self,
        mocked_start_session,
        mocked_delete_workspace,
    ):
        response = self.client.post(
            reverse("jupyter_launch"),
            {
                "title": "Failed launch",
                "partition": "basic",
                "node": "",
                "cpus": "2",
                "memory_mb": "8192",
                "hours": "1",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            JupyterNotebook.objects.filter(
                title="Failed launch",
            ).exists()
        )
        self.assertEqual(
            mocked_delete_workspace.call_count,
            1,
        )
        mocked_start_session.assert_called_once()

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "active_session_for_notebook",
        return_value=None,
    )
    def test_stopped_workspace_offers_standalone_jupyterlab(
        self,
        mocked_active_session,
    ):
        notebook = JupyterNotebook.objects.create(
            title="Stopped workspace",
            owner=self.owner,
            updated_by=self.owner,
            notebook_json=starter_notebook(
                "Stopped workspace",
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
            "Standalone JupyterLab",
        )
        self.assertContains(
            response,
            "batch_connect/sys/jupyterlab/"
            "session_contexts/new",
        )
        mocked_active_session.assert_called_once()

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "active_session_for_notebook",
    )
    def test_running_workspace_offers_managed_jupyterlab(
        self,
        mocked_active_session,
    ):
        notebook = JupyterNotebook.objects.create(
            title="Running workspace",
            owner=self.owner,
            updated_by=self.owner,
            notebook_json=starter_notebook(
                "Running workspace",
                self.owner.get_username(),
            ),
        )

        session = notebook.sessions.create(
            started_by=self.owner,
            job_id="99102",
            run_id="managed_lab_session",
            status="running",
            partition="basic",
            cpus=2,
            memory_mb=8192,
            time_minutes=60,
            run_directory="/tmp/managed-lab-session",
        )
        mocked_active_session.return_value = session

        response = self.client.get(
            reverse(
                "jupyter_workspace",
                args=[notebook.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Open JupyterLab",
        )
        self.assertContains(
            response,
            (
                reverse(
                    "jupyter_connect",
                    args=[notebook.id],
                )
                + "?interface=lab"
            ),
        )
        self.assertNotContains(
            response,
            "Standalone JupyterLab",
        )

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "connection_target"
    )
    @patch(
        "core.views.internal.lab_tools.jupyter."
        "active_session_for_notebook"
    )
    def test_connect_forwards_managed_lab_interface(
        self,
        mocked_active_session,
        mocked_target,
    ):
        notebook = JupyterNotebook.objects.create(
            title="Managed lab redirect",
            owner=self.owner,
            updated_by=self.owner,
            notebook_json=starter_notebook(
                "Managed lab redirect",
                self.owner.get_username(),
            ),
        )

        session = object()
        mocked_active_session.return_value = session

        target = mocked_target.return_value
        target.redirect_path = "/managed-jupyterlab"
        target.cookie_path = (
            "/b3lims/internal/lab-tools/jupyter/"
            f"{notebook.id}/node/gn03/45679/"
        )
        target.token = (
            "protected-lab-token-value-1234567890"
        )

        response = self.client.get(
            reverse(
                "jupyter_connect",
                args=[notebook.id],
            ),
            {"interface": "lab"},
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            response.url,
            "/managed-jupyterlab",
        )
        self.assertNotIn(
            "?token=",
            response.url,
        )

        cookie = response.cookies[
            "__Secure-biobank-jupyter-token"
        ]
        self.assertEqual(
            cookie.value,
            target.token,
        )
        self.assertEqual(
            cookie["path"],
            target.cookie_path,
        )

        mocked_target.assert_called_once_with(
            session,
            interface="lab",
        )
