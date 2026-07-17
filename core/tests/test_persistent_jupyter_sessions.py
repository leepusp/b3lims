import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models.lab_tools.notebook import (
    JupyterNotebook,
)
from core.services.jupyter_sessions import (
    active_session_for_notebook,
    start_session,
    starter_notebook,
)


@override_settings(
    BIOBANK_JUPYTER_PARTITIONS=("basic", "max50"),
)
class PersistentJupyterSessionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="persistent-jupyter-owner",
            password="test-password",
        )
        self.notebook = JupyterNotebook.objects.create(
            title="Persistent analysis",
            owner=self.user,
            notebook_json=starter_notebook(
                "Persistent analysis",
                self.user.get_username(),
            ),
        )

    @patch(
        "core.services.jupyter_sessions."
        "_run_runner"
    )
    @patch(
        "core.services.jupyter_sessions."
        "_ensure_child"
    )
    def test_start_session_uses_selected_partition(
        self,
        ensure_child_mock,
        runner_mock,
    ):
        run_directory = Path(
            tempfile.mkdtemp()
        )
        ensure_child_mock.return_value = run_directory
        runner_mock.return_value = {
            "status": "submitted",
            "job_id": "40001",
            "run_id": "persistent_run_1",
            "run_dir": str(run_directory),
            "partition": "basic",
        }

        session = start_session(
            self.notebook,
            self.user,
            partition="basic",
            cpus=2,
            memory_mb=4096,
            time_minutes=60,
        )

        self.assertEqual(session.job_id, "40001")
        self.assertEqual(session.partition, "basic")
        self.assertEqual(session.status, "submitted")

        runner_mock.assert_called_once_with(
            "session-start",
            self.notebook.id,
            self.user.get_username(),
            2,
            4096,
            60,
            "basic",
        )

    @patch(
        "core.services.jupyter_sessions."
        "_run_runner"
    )
    def test_running_session_is_reused(
        self,
        runner_mock,
    ):
        session = self.notebook.sessions.create(
            started_by=self.user,
            job_id="40002",
            run_id="persistent_run_2",
            status="submitted",
            partition="max50",
            cpus=4,
            memory_mb=8192,
            time_minutes=120,
            run_directory="/tmp/persistent-run",
        )

        runner_mock.return_value = {
            "status": "ok",
            "job_id": session.job_id,
            "run_id": session.run_id,
            "state": "RUNNING",
            "ready": True,
            "run_dir": session.run_directory,
        }

        active = active_session_for_notebook(
            self.notebook
        )

        self.assertEqual(active.id, session.id)
        self.assertEqual(active.status, "running")
        self.assertIsNotNone(active.ready_at)


    def test_unknown_session_is_not_reused(self):
        self.notebook.sessions.create(
            job_id="999999",
            run_id="stale-session-regression",
            status="unknown",
            partition="basic",
            cpus=2,
            memory_mb=2048,
            time_minutes=60,
            run_directory="/tmp/stale-session-regression",
            started_by=self.user,
        )

        self.assertIsNone(
            active_session_for_notebook(self.notebook)
        )


@override_settings(
    BIOBANK_JUPYTER_PARTITIONS=("basic", "max50"),
)
class PersistentJupyterExecutionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="persistent-execution-owner",
            password="test-password",
        )
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(
            self.temporary_directory.cleanup
        )

        self.notebook = JupyterNotebook.objects.create(
            title="Persistent execution",
            owner=self.user,
            updated_by=self.user,
            notebook_json=starter_notebook(
                "Persistent execution",
                self.user.get_username(),
            ),
        )

        self.session = self.notebook.sessions.create(
            started_by=self.user,
            job_id="99901",
            run_id="persistent_execution_test",
            status="running",
            partition="basic",
            cpus=2,
            memory_mb=4096,
            time_minutes=60,
            run_directory=self.temporary_directory.name,
        )

    def test_new_notebook_starts_without_cells(self):
        notebook = starter_notebook(
            "Empty notebook",
            self.user.get_username(),
        )

        self.assertEqual(notebook["cells"], [])
        self.assertEqual(notebook["nbformat"], 4)

    def test_execute_cell_updates_saved_notebook(self):
        # Explicit cells for execution regression.
        notebook_data = starter_notebook(
            "Execution regression",
            self.user.get_username(),
        )
        notebook_data["cells"] = [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["seed = 40\n"],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["seed + 2\n"],
            },
        ]

        self.notebook.notebook_json = notebook_data
        self.notebook.save(
            update_fields=[
                "notebook_json",
                "updated_at",
            ]
        )

        import json
        from unittest.mock import patch

        from core.services.jupyter_sessions import (
            execute_cell,
        )

        def fake_runner(*arguments, **kwargs):
            self.assertEqual(
                arguments[0],
                "session-execute",
            )

            response_path = Path(arguments[4])
            response_path.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "execution_count": 1,
                        "outputs": [
                            {
                                "output_type": "stream",
                                "name": "stdout",
                                "text": ["persistent-result=42\n"],
                            }
                        ],
                    }
                )
            )

            return {"status": "ok"}

        with patch(
            "core.services.jupyter_sessions."
            "refresh_session",
            return_value=self.session,
        ), patch(
            "core.services.jupyter_sessions."
            "_run_runner",
            side_effect=fake_runner,
        ):
            result = execute_cell(
                self.session,
                self.user,
                1,
            )

        self.notebook.refresh_from_db()
        self.session.refresh_from_db()

        cell = self.notebook.notebook_json["cells"][1]

        self.assertEqual(
            result["execution_count"],
            1,
        )
        self.assertEqual(
            cell["execution_count"],
            1,
        )
        self.assertEqual(
            cell["outputs"][0]["text"],
            ["persistent-result=42\n"],
        )
        self.assertIsNotNone(
            self.session.last_activity_at
        )

    def test_stop_session_cancels_persistent_job(self):
        from unittest.mock import patch

        from core.services.jupyter_sessions import (
            stop_session,
        )

        with patch(
            "core.services.jupyter_sessions._run_runner",
            return_value={
                "status": "stopped",
                "state": "CANCELLED",
            },
        ) as mocked_runner:
            stopped = stop_session(
                self.session,
                self.user,
            )

        self.assertEqual(
            stopped.status,
            "cancelled",
        )
        self.assertIsNotNone(
            stopped.finished_at
        )
        mocked_runner.assert_called_once_with(
            "session-stop",
            self.notebook.id,
            self.session.run_id,
        )
