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

    def test_storage_broker_uses_fd_anchored_mutations(self):
        source = self._source(
            "deploy/sbin/biobank-user-storage-broker"
        )

        for marker in (
            "os.O_NOFOLLOW",
            "dir_fd=parent_fd",
            "os.fchown(",
            "os.fchmod(",
            "pass_fds=(fd,)",
            '"g::---,m::rwx,o::---"',
            '"g::---,m::rw-,o::---"',
        ):
            self.assertIn(marker, source)

        self.assertNotIn(
            'install -d -o "$username"',
            source,
        )
        self.assertNotIn(
            'chown "$username:$PRIMARY_GROUP"',
            source,
        )
        self.assertNotIn(
            'chmod 0770 "$directory"',
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

        legacy_root = "/home/public" + "/biobank"

        self.assertIn(
            'RUNTIME_ROOT="/home/public/apps/biobank/runtime"',
            runner,
        )
        self.assertNotIn(
            legacy_root,
            runner,
        )
        self.assertNotIn(
            "/usr/local/libexec/biobank",
            runner,
        )

        self.assertIn(
            'APP_ROOT="/home/public/apps/biobank"',
            installer,
        )
        self.assertIn(
            'RUNTIME_ROOT="$APP_ROOT/runtime"',
            installer,
        )
        self.assertIn(
            'SHARED_RUNTIME="$RUNTIME_ROOT/notebook_server.sh"',
            installer,
        )
        self.assertIn(
            'SOURCE_RUNTIME="$SOURCE_ROOT/runtime/notebook_server.sh"',
            installer,
        )
        self.assertIn(
            '"$SOURCE_RUNTIME" \\\n'
            '    "$SHARED_RUNTIME"',
            installer,
        )
        self.assertNotIn(
            legacy_root,
            installer,
        )
        self.assertIn(
            "EXPECTED_SHARED_RUNTIME_AFTER",
            installer,
        )

    def test_shared_runtime_install_permissions_and_first_install(self):
        installer = self._source(
            "deploy/install_lab_tools_home_storage.sh"
        )

        self.assertIn(
            'APP_ROOT="/home/public/apps/biobank"',
            installer,
        )
        self.assertIn(
            'RUNTIME_ROOT="$APP_ROOT/runtime"',
            installer,
        )
        self.assertIn(
            'SHARED_RUNTIME="$RUNTIME_ROOT/notebook_server.sh"',
            installer,
        )
        self.assertIn(
            'SOURCE_RUNTIME="$SOURCE_ROOT/runtime/notebook_server.sh"',
            installer,
        )
        self.assertIn(
            'chmod 2771 "$APP_ROOT"',
            installer,
        )
        self.assertIn(
            '-m 0751 \\\n'
            '    "$RUNTIME_ROOT"',
            installer,
        )
        self.assertIn(
            'chmod 0751 "$RUNTIME_ROOT"',
            installer,
        )
        self.assertIn(
            'chmod g-s "$RUNTIME_ROOT"',
            installer,
        )
        self.assertIn(
            'install -o root -g biobank -m 0755',
            installer,
        )
        self.assertIn(
            'if test -f "$SHARED_RUNTIME"',
            installer,
        )
        self.assertNotIn(
            'test -f "$SHARED_RUNTIME" || '
            'fail "Current shared Jupyter runtime was not found."',
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

    def test_jupyter_broker_drops_root_before_user_path_mutation(self):
        source = self._source(
            "deploy/sbin/biobank-jupyter-server-broker"
        )

        for marker in (
            'write_user_file()',
            'read_user_file()',
            'remove_user_tree()',
            '/usr/sbin/runuser -u "$APP_USER" -- /usr/bin/tee',
            '/usr/bin/rm -rf --one-file-system',
            'remove_user_tree "$run_dir"',
            'remove_user_tree "$workspace"',
            '"$STORAGE_HELPER" claim-file',
            '"jupyter/notebooks/notebook_${notebook_id}/notebook.ipynb"',
        ):
            self.assertIn(marker, source)

        self.assertNotIn(
            'chown "$APP_USER:$PRIMARY_GROUP"',
            source,
        )
        self.assertNotIn(
            'write_owned_file',
            source,
        )
        self.assertNotIn(
            '} > "$job_script"',
            source,
        )
        self.assertNotIn(
            'rm -rf --one-file-system -- "$run_dir"',
            source,
        )
        self.assertNotIn(
            'rm -rf --one-file-system -- "$workspace"',
            source,
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
