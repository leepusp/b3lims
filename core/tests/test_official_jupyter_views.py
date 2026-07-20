import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import (
    get_script_prefix,
    reverse,
    set_script_prefix,
)
from django.utils import timezone

from core.models.lab_tools.notebook import (
    JupyterNotebook,
)
from core.services.jupyter_server import (
    starter_notebook,
)


@override_settings(
    FORCE_SCRIPT_NAME=None,
    BIOBANK_JUPYTER_PARTITION="basic",
    BIOBANK_JUPYTER_PARTITIONS=(
        "basic",
        "max50",
    ),
)
class OfficialJupyterViewTests(TestCase):
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
            username="official-view-owner",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="official-view-other",
            password="test-password",
        )

        self.notebook = JupyterNotebook.objects.create(
            title="Official view notebook",
            owner=self.owner,
            updated_by=self.owner,
            notebook_json=starter_notebook(
                "Official view notebook",
                self.owner.get_username(),
            ),
        )

        self.session = self.notebook.sessions.create(
            started_by=self.owner,
            job_id="51001",
            run_id=(
                "20260720T212000Z_5678_1234"
            ),
            status="running",
            partition="basic",
            cpus=2,
            memory_mb=8192,
            time_minutes=60,
            run_directory=(
                "/protected/runtime/"
                "20260720T212000Z_5678_1234"
            ),
            ready_at=timezone.now(),
            kernel_info={
                "official_server": True,
                "server": {
                    "host": "gn03",
                    "port": 45679,
                    "base_url": (
                        "/node/gn03/45679/"
                    ),
                },
                "token": (
                    "must-never-reach-client"
                ),
            },
        )

        self.client.force_login(self.owner)

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "connection_redirect_path",
        return_value=(
            "/node/gn03/45679/"
            "tree/notebook.ipynb"
            "?token=protected-connect-token"
        ),
    )
    @patch(
        "core.views.internal.lab_tools.jupyter."
        "active_session_for_notebook"
    )
    def test_connect_redirect_is_private_and_no_store(
        self,
        mocked_active,
        mocked_connection,
    ):
        mocked_active.return_value = self.session

        response = self.client.get(
            reverse(
                "jupyter_connect",
                args=[self.notebook.id],
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            response["Location"],
            (
                "/node/gn03/45679/"
                "tree/notebook.ipynb"
                "?token=protected-connect-token"
            ),
        )
        self.assertIn(
            "no-store",
            response["Cache-Control"],
        )
        self.assertEqual(
            response["Referrer-Policy"],
            "no-referrer",
        )
        self.assertEqual(
            response["X-Robots-Tag"],
            "noindex, nofollow",
        )

        mocked_connection.assert_called_once_with(
            self.session
        )

    def test_other_user_cannot_use_connect_route(self):
        self.client.force_login(
            self.other_user
        )

        response = self.client.get(
            reverse(
                "jupyter_connect",
                args=[self.notebook.id],
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "refresh_session"
    )
    def test_status_api_never_exposes_token_or_document(
        self,
        mocked_refresh,
    ):
        mocked_refresh.return_value = self.session

        response = self.client.get(
            reverse(
                "jupyter_session_status_api",
                args=[self.session.id],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        payload = response.json()
        serialized = json.dumps(payload)

        self.assertNotIn(
            "must-never-reach-client",
            serialized,
        )
        self.assertNotIn(
            "token",
            serialized.lower(),
        )
        self.assertNotIn(
            "document",
            payload,
        )
        self.assertTrue(
            payload["execution"]["ready"]
        )

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "active_session_for_notebook"
    )
    def test_workspace_contains_connect_url_not_token(
        self,
        mocked_active,
    ):
        mocked_active.return_value = self.session

        response = self.client.get(
            reverse(
                "jupyter_workspace",
                args=[self.notebook.id],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            reverse(
                "jupyter_connect",
                args=[self.notebook.id],
            ),
        )
        self.assertNotContains(
            response,
            "must-never-reach-client",
        )
        self.assertNotContains(
            response,
            "protected-connect-token",
        )

    def test_old_cell_execution_endpoint_is_retired(
        self,
    ):
        response = self.client.post(
            reverse(
                "jupyter_execute_api",
                args=[self.notebook.id],
            ),
            data=json.dumps(
                {
                    "cell_index": 0,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            410,
        )
        self.assertIn(
            "official Jupyter Notebook server",
            response.json()["message"],
        )

    @patch(
        "core.views.internal.lab_tools.jupyter."
        "load_notebook_document"
    )
    def test_download_uses_filesystem_document(
        self,
        mocked_load,
    ):
        document = starter_notebook(
            self.notebook.title,
            self.owner.get_username(),
        )
        document["cells"] = [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "filesystem_value = 42\n",
                ],
            }
        ]

        mocked_load.return_value = document

        response = self.client.get(
            reverse(
                "jupyter_download",
                args=[self.notebook.id],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            json.loads(
                response.content.decode("utf-8")
            )["cells"][0]["source"],
            ["filesystem_value = 42\n"],
        )

        mocked_load.assert_called_once_with(
            self.notebook
        )
