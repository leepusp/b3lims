from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class LabToolsDeploymentContractTests(SimpleTestCase):
    def _source(self, relative_path):
        return (
            Path(settings.BASE_DIR) / relative_path
        ).read_text()

    def test_storage_helper_repairs_every_nested_component(self):
        source = self._source(
            "deploy/sbin/biobank-user-storage"
        )

        self.assertIn(
            'for component in "${components[@]}"',
            source,
        )
        self.assertIn(
            'apply_directory_acl "$username" "$directory"',
            source,
        )
        self.assertIn(
            'test ! -L "$directory"',
            source,
        )

    def test_runner_validates_and_forwards_optional_node(self):
        source = self._source(
            "deploy/sbin/biobank-jupyter-server-runner"
        )

        self.assertIn("validate_node", source)
        self.assertIn(
            'auto|n01|gn01|gn02|gn03',
            source,
        )
        self.assertIn(
            'node_arguments=("--nodelist=$node")',
            source,
        )
        self.assertIn(
            '"${node_arguments[@]}"',
            source,
        )

    def test_runner_limits_match_application_contract(self):
        source = self._source(
            "deploy/sbin/biobank-jupyter-server-runner"
        )

        self.assertIn(
            '"CPU count" "$cpus" 1 128',
            source,
        )
        self.assertIn(
            '"Memory" "$memory_mb" 1024 1048576',
            source,
        )
        self.assertIn(
            '"Time" "$minutes" 60 10080',
            source,
        )

    def test_runner_cancels_job_as_authenticated_owner(self):
        source = self._source(
            "deploy/sbin/biobank-jupyter-server-runner"
        )

        self.assertIn(
            '/usr/sbin/runuser -u "$APP_USER" -- \\\n'
            '        /usr/bin/scancel "$job_id"',
            source,
        )

    def test_runtime_uses_compute_node_visible_shared_path(self):
        runner = self._source(
            "deploy/sbin/biobank-jupyter-server-runner"
        )
        installer = self._source(
            "deploy/install_lab_tools_home_storage.sh"
        )

        shared_runtime = (
            "/home/public/biobank/runtime/"
            "notebook_server.sh"
        )

        self.assertIn(
            'RUNTIME_ROOT="/home/public/biobank/runtime"',
            runner,
        )
        self.assertNotIn(
            "/usr/local/libexec/biobank",
            runner,
        )
        self.assertIn(shared_runtime, installer)
        self.assertIn(
            '"$SOURCE_ROOT/runtime/notebook_server.sh"',
            installer,
        )
        self.assertIn(
            "EXPECTED_SHARED_RUNTIME_AFTER",
            installer,
        )

    def test_runtime_exposes_authenticated_home_and_isolates_state(self):
        runtime = self._source(
            "deploy/runtime/notebook_server.sh"
        )

        self.assertIn(
            '--bind "$USER_HOME" "$USER_HOME"',
            runtime,
        )
        self.assertIn(
            '--chdir "$USER_HOME"',
            runtime,
        )
        self.assertIn(
            '--setenv HOME "$USER_HOME"',
            runtime,
        )
        self.assertIn(
            'f"c.ServerApp.root_dir = {user_home!r}"',
            runtime,
        )
        self.assertIn(
            'DEFAULT_URL="/tree/${WORKSPACE_RELATIVE}/'
            '${NOTEBOOK_NAME}"',
            runtime,
        )
        self.assertNotIn(
            "--setenv HOME /runtime/home",
            runtime,
        )
        self.assertNotIn(
            "c.ServerApp.root_dir = '/workspace'",
            runtime,
        )

        for runtime_directory in (
            "jupyter-runtime",
            "jupyter-config",
            "jupyter-data",
            "xdg-config",
            "xdg-data",
            "matplotlib",
            "cache",
            "ipython",
        ):
            self.assertIn(
                f'"$RUN_DIR/{runtime_directory}"',
                runtime,
            )

        self.assertIn(
            "--setenv JUPYTER_DATA_DIR "
            "/runtime/jupyter-data",
            runtime,
        )
        self.assertIn(
            "--setenv XDG_CONFIG_HOME "
            "/runtime/xdg-config",
            runtime,
        )
        self.assertIn(
            "--setenv XDG_DATA_HOME "
            "/runtime/xdg-data",
            runtime,
        )

    def test_terminal_sessions_remove_runtime_artifacts(self):
        runner = self._source(
            "deploy/sbin/biobank-jupyter-server-runner"
        )
        runtime = self._source(
            "deploy/runtime/notebook_server.sh"
        )

        self.assertIn(
            "is_terminal_state()",
            runner,
        )
        self.assertIn(
            "remove_run_directory()",
            runner,
        )
        self.assertIn(
            "session_cleanup()",
            runner,
        )
        self.assertIn(
            "run_directory_removed",
            runner,
        )
        self.assertIn(
            '"$RUN_DIR/jupyter-runtime"',
            runtime,
        )
        self.assertIn(
            '"$RUN_DIR/ipython"',
            runtime,
        )
        self.assertIn(
            '--setenv HOME "$USER_HOME"',
            runtime,
        )
