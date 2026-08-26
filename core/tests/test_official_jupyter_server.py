import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models.lab_tools.notebook import (
    JupyterNotebook,
)
from core.services.jupyter_server import (
    _validate_resources,
    connection_target,
    delete_notebook_workspace,
    load_notebook_document,
    notebook_file_for_notebook,
    refresh_session,
    start_session,
    starter_notebook,
    stop_session,
    workspace_for_notebook,
)


class OfficialJupyterServerTests(TestCase):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.addCleanup(
            self.temporary_directory.cleanup
        )

        temporary_root = Path(
            self.temporary_directory.name
        )

        self.owner_home = temporary_root / "owner-home"
        self.other_home = temporary_root / "other-home"
        self.owner_home.mkdir()
        self.other_home.mkdir()

        def fake_user_home(username):
            return {
                "official-server-owner": self.owner_home,
                "official-server-other": self.other_home,
            }[username]

        self.home_patch = patch(
            "core.services.lab_tools_storage."
            "user_home_for_username",
            side_effect=fake_user_home,
        )
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)

        self.settings_override = override_settings(
            BIOBANK_LAB_TOOLS_RELATIVE_ROOT=(
                "biobank/lab_tools"
            ),
            BIOBANK_JUPYTER_PARTITION="basic",
            BIOBANK_JUPYTER_PARTITIONS=(
                "basic",
                "max50",
            ),
            BIOBANK_JUPYTER_NODES=(
                "n01",
                "gn01",
                "gn02",
                "gn03",
            ),
            BIOBANK_JUPYTER_PARTITION_MAX_HOURS={
                "basic": 72,
                "max50": 168,
            },
        )
        self.settings_override.enable()
        self.addCleanup(
            self.settings_override.disable
        )

        User = get_user_model()

        self.user = User.objects.create_user(
            username="official-server-owner",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="official-server-other",
            password="test-password",
        )

        self.notebook = JupyterNotebook.objects.create(
            title="Official server test",
            owner=self.user,
            updated_by=self.user,
            notebook_json=starter_notebook(
                "Official server test",
                self.user.get_username(),
            ),
        )
        self.storage_root = (
            self.owner_home
            / "biobank/lab_tools/jupyter/notebooks"
        )
        self.job_root = (
            self.owner_home
            / "biobank/lab_tools/jupyter/jobs"
            / f"notebook_{self.notebook.id}"
        )

    def test_workspace_isolated_by_application_user(self):
        other_notebook = JupyterNotebook.objects.create(
            title="Other workspace",
            owner=self.other_user,
            updated_by=self.other_user,
            notebook_json=starter_notebook(
                "Other workspace",
                self.other_user.get_username(),
            ),
        )

        owner_workspace = workspace_for_notebook(
            self.notebook
        )
        other_workspace = workspace_for_notebook(
            other_notebook
        )

        self.assertNotEqual(
            owner_workspace,
            other_workspace,
        )
        self.assertTrue(
            str(owner_workspace).startswith(
                str(self.owner_home)
            )
        )
        self.assertEqual(
            owner_workspace,
            self.storage_root
            / f"notebook_{self.notebook.id}",
        )
        self.assertTrue(
            str(other_workspace).startswith(
                str(self.other_home)
            )
        )

    @patch(
        "core.services.jupyter_server."
        "_run_server_runner"
    )
    def test_start_session_writes_official_notebook(
        self,
        mocked_runner,
    ):
        workspace = workspace_for_notebook(
            self.notebook
        )
        workspace.mkdir(
            parents=True,
            exist_ok=True,
        )

        run_directory = (
            self.job_root
            / "20260720T210000Z_1234_5678"
        )
        run_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        notebook_file = (
            workspace / "notebook.ipynb"
        )

        # The protected runner creates the initial
        # notebook file before returning to Django.
        notebook_file.write_text(
            json.dumps(
                starter_notebook(
                    self.notebook.title,
                    self.user.get_username(),
                )
            )
        )

        mocked_runner.return_value = {
            "status": "submitted",
            "job_id": "50001",
            "notebook_id": self.notebook.id,
            "run_id": (
                "20260720T210000Z_1234_5678"
            ),
            "run_dir": str(run_directory),
            "workspace": str(workspace),
            "notebook_file": str(notebook_file),
            "partition": "basic",
            "requested_node": "gn03",
            "slurm_user": self.user.get_username(),
        }

        session = start_session(
            self.notebook,
            self.user,
            cpus=3,
            memory_mb=12288,
            time_minutes=180,
            partition="basic",
            node="gn03",
        )

        self.assertEqual(
            session.job_id,
            "50001",
        )
        self.assertEqual(
            session.status,
            "submitted",
        )
        self.assertEqual(
            session.cpus,
            3,
        )
        self.assertEqual(
            session.memory_mb,
            12288,
        )
        self.assertEqual(
            session.time_minutes,
            180,
        )
        self.assertTrue(
            notebook_file.exists()
        )

        document = json.loads(
            notebook_file.read_text()
        )

        self.assertEqual(
            document["cells"],
            [],
        )
        self.assertEqual(
            document["nbformat"],
            4,
        )
        # Ownership remains authoritative in
        # PostgreSQL and in the isolated workspace path.
        mocked_runner.assert_called_once_with(
            "server-start",
            self.notebook.id,
            self.user.id,
            self.user.get_username(),
            3,
            12288,
            180,
            "basic",
            "gn03",
        )

        self.assertEqual(
            session.kernel_info["requested_node"],
            "gn03",
        )

    def test_resource_validation_accepts_interface_limits(self):
        resources = _validate_resources(
            cpus=128,
            memory_mb=1048576,
            time_minutes=10080,
            partition="max50",
            node="n01",
        )

        self.assertEqual(resources["cpus"], 128)
        self.assertEqual(resources["memory_mb"], 1048576)
        self.assertEqual(resources["node"], "n01")

    def test_resource_validation_rejects_unknown_node(self):
        with self.assertRaisesMessage(
            ValueError,
            "Invalid compute node.",
        ):
            _validate_resources(
                cpus=2,
                memory_mb=8192,
                time_minutes=60,
                partition="basic",
                node="n01;id",
            )

    def test_basic_partition_enforces_72_hour_limit(self):
        with self.assertRaisesMessage(
            ValueError,
            "60 and 4320 minutes for basic",
        ):
            _validate_resources(
                cpus=2,
                memory_mb=8192,
                time_minutes=4380,
                partition="basic",
                node="auto",
            )

    def test_disk_notebook_is_authoritative(self):
        notebook_file = notebook_file_for_notebook(
            self.notebook
        )
        notebook_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        document = starter_notebook(
            self.notebook.title,
            self.user.get_username(),
        )
        document["cells"] = [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": [
                    "value = 42\n",
                ],
            }
        ]

        notebook_file.write_text(
            json.dumps(document)
        )

        loaded = load_notebook_document(
            self.notebook
        )

        self.assertEqual(
            loaded["cells"][0]["source"],
            "value = 42\n",
        )

        self.notebook.refresh_from_db()

        self.assertEqual(
            self.notebook.notebook_json[
                "cells"
            ][0]["source"],
            "value = 42\n",
        )

    def test_connection_token_is_read_only_at_connect_time(
        self,
    ):
        run_directory = (
            self.job_root
            / "20260720T211000Z_4321_8765"
        )
        run_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        connection_file = (
            run_directory
            / "connection.json"
        )

        connection_file.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "host": "gn03",
                    "port": 45678,
                    "base_url": (
                        f"/biobank/internal/lab-tools/"
                        f"jupyter/{self.notebook.id}/"
                        "node/gn03/45678/"
                    ),
                    "default_url": (
                        "/tree/notebook.ipynb"
                    ),
                    "token": (
                        "protected-token-value-"
                        "abcdefghijklmnopqrstuvwxyz123456"
                    ),
                }
            )
        )

        session = self.notebook.sessions.create(
            started_by=self.user,
            job_id="50002",
            run_id=(
                "20260720T211000Z_4321_8765"
            ),
            status="running",
            partition="basic",
            cpus=2,
            memory_mb=4096,
            time_minutes=60,
            run_directory=str(
                run_directory
            ),
            ready_at=timezone.now(),
            kernel_info={
                "official_server": True,
                "server": {
                    "host": "gn03",
                    "port": 45678,
                    "base_url": (
                        f"/biobank/internal/lab-tools/"
                        f"jupyter/{self.notebook.id}/"
                        "node/gn03/45678/"
                    ),
                },
            },
        )

        with patch(
            "core.services.jupyter_server."
            "refresh_session",
            return_value=session,
        ):
            target = connection_target(
                session
            )
            lab_target = connection_target(
                session,
                interface="lab",
            )

        expected_base = (
            f"/biobank/internal/lab-tools/"
            f"jupyter/{self.notebook.id}/"
            "node/gn03/45678/"
        )

        self.assertEqual(
            target.redirect_path,
            (
                expected_base
                + "tree/notebook.ipynb"
            ),
        )
        self.assertEqual(
            lab_target.redirect_path,
            (
                expected_base
                + "lab/tree/notebook.ipynb"
            ),
        )
        self.assertEqual(
            target.cookie_path,
            expected_base,
        )
        self.assertEqual(
            target.token,
            (
                "protected-token-value-"
                "abcdefghijklmnopqrstuvwxyz123456"
            ),
        )
        self.assertNotIn(
            "?token=",
            target.redirect_path,
        )

        session.refresh_from_db()

        database_payload = json.dumps(
            session.kernel_info
        )

        self.assertNotIn(
            "protected-token-value",
            database_payload,
        )

    @patch(
        "core.services.jupyter_server._run_server_runner"
    )
    def test_delete_uses_protected_exact_workspace(
        self,
        runner_mock,
    ):
        runner_mock.return_value = {
            "status": "ok",
            "workspace_removed": True,
        }

        removed = delete_notebook_workspace(
            self.notebook
        )

        self.assertTrue(removed)

        runner_mock.assert_called_once_with(
            "workspace-delete",
            self.notebook.id,
            self.notebook.owner_id,
            self.notebook.owner.get_username(),
        )

    @patch(
        "core.services.jupyter_server._run_server_runner"
    )
    def test_status_is_queried_for_real_unix_owner(
        self,
        runner_mock,
    ):
        session = self.notebook.sessions.create(
            started_by=self.user,
            job_id="50003",
            run_id="owner_status_run",
            status="submitted",
            partition="basic",
            cpus=2,
            memory_mb=4096,
            time_minutes=60,
            run_directory=str(
                self.job_root / "owner_status_run"
            ),
        )
        runner_mock.return_value = {
            "status": "ok",
            "job_id": "50003",
            "state": "PENDING",
            "ready": False,
            "slurm_user": self.user.get_username(),
            "server": {},
        }

        refreshed = refresh_session(session)

        self.assertEqual(refreshed.status, "pending")
        runner_mock.assert_called_once_with(
            "server-status",
            self.notebook.id,
            self.user.get_username(),
            "owner_status_run",
        )

    @patch(
        "core.services.jupyter_server._run_server_runner"
    )
    def test_stop_is_scoped_to_real_unix_owner(
        self,
        runner_mock,
    ):
        session = self.notebook.sessions.create(
            started_by=self.user,
            job_id="50004",
            run_id="owner_stop_run",
            status="running",
            partition="basic",
            cpus=2,
            memory_mb=4096,
            time_minutes=60,
            run_directory=str(
                self.job_root / "owner_stop_run"
            ),
        )
        runner_mock.return_value = {
            "status": "stopped",
            "job_id": "50004",
            "slurm_user": self.user.get_username(),
        }

        stopped = stop_session(session, self.user)

        self.assertEqual(stopped.status, "cancelled")
        runner_mock.assert_called_once_with(
            "server-stop",
            self.notebook.id,
            self.user.get_username(),
            "owner_stop_run",
        )
