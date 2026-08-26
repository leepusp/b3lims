from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


ROOT = Path(settings.BASE_DIR)

DEPLOY = (
    ROOT
    / "deploy"
    / "operations"
    / "deploy_independent_jupyter.sh"
)

SUDOERS = (
    ROOT
    / "deploy"
    / "sudoers"
    / "biobank-runtime-brokers"
)

MAIN_CONF = (
    ROOT
    / "deploy"
    / "apache"
    / "biobank.conf"
)

PROXY_CONF = (
    ROOT
    / "deploy"
    / "apache"
    / "biobank-jupyter.conf"
)


def normalize_shell(source):
    return " ".join(
        source.replace("\\\n", " ").split()
    )


class IndependentJupyterDeploymentContractTests(
    SimpleTestCase
):
    def test_runtime_broker_sudoers_is_versioned(self):
        source = SUDOERS.read_text()

        self.assertEqual(
            source,
            (
                "Defaults!/usr/local/sbin/"
                "biobank-user-storage-broker "
                "!requiretty\n"
                "Defaults!/usr/local/sbin/"
                "biobank-jupyter-server-broker "
                "!requiretty\n"
                "\n"
                "biobank ALL=(root) NOPASSWD: "
                "/usr/local/sbin/"
                "biobank-user-storage-broker *\n"
                "biobank ALL=(root) NOPASSWD: "
                "/usr/local/sbin/"
                "biobank-jupyter-server-broker *\n"
            ),
        )

    def test_apache_runtime_is_not_under_secret_tree(self):
        combined = (
            MAIN_CONF.read_text()
            + "\n"
            + PROXY_CONF.read_text()
        )

        self.assertNotIn(
            "/etc/biobank/apache",
            combined,
        )
        self.assertIn(
            "/etc/httpd/biobank/",
            combined,
        )

    def test_fail_returns_nonzero_for_err_trap(self):
        source = DEPLOY.read_text()

        fail_start = source.index(
            "fail() {"
        )
        fail_end = source.index(
            "}",
            fail_start,
        )
        fail_block = source[
            fail_start:fail_end + 1
        ]

        self.assertIn(
            "return 1",
            fail_block,
        )
        self.assertNotIn(
            "exit 1",
            fail_block,
        )

    def test_read_only_preflight_exits_before_manifest(self):
        source = DEPLOY.read_text()

        mode_index = source.index(
            'MODE="deploy"'
        )
        preflight_index = source.index(
            'if test "$MODE" = "preflight"'
        )
        manifest_index = source.index(
            'echo "2. CREATE DEPLOYMENT MANIFEST"'
        )

        self.assertLess(
            mode_index,
            preflight_index,
        )
        self.assertLess(
            preflight_index,
            manifest_index,
        )
        self.assertIn(
            "preflight_only=PASS",
            source,
        )
        self.assertIn(
            "production_modified=NO",
            source,
        )

    def test_rollback_restart_is_fail_closed(self):
        source = DEPLOY.read_text()

        for marker in (
            "rollback_safe=1",
            "rollback_safe=0",
            "rollback_contract=RESTORED",
            "rollback_contract=INCOMPLETE_FAIL_CLOSED",
            "rollback_biobank_restart=SKIPPED_FAIL_CLOSED",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_cutover_requires_exact_committed_source(self):
        source = DEPLOY.read_text()

        for marker in (
            'repo_git rev-parse HEAD',
            'repo_git rev-parse origin/main',
            'repo_git status --porcelain=v1',
            '[[ "$TARGET_COMMIT" =~ '
            '^[0-9a-f]{40}$ ]]',
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_cutover_requires_no_active_managed_jupyter(self):
        source = DEPLOY.read_text()

        self.assertIn(
            r"\|biobank_notebook_[0-9]+\|",
            source,
        )
        self.assertIn(
            'test -z "$ACTIVE"',
            source,
        )

    def test_cutover_stages_immutable_git_release(self):
        source = DEPLOY.read_text()

        normalized = normalize_shell(
            source
        )

        for marker in (
            'repo_git archive "$TARGET_COMMIT"',
            'TARGET_RELEASE="$RELEASE_ROOT/'
            '$TARGET_COMMIT"',
            'mv "$STAGE_RELEASE" '
            '"$TARGET_RELEASE"',
            '"releases/$TARGET_COMMIT"',
        ):
            self.assertIn(
                marker,
                normalized,
            )

    def test_cutover_installs_all_proxy_components(self):
        source = DEPLOY.read_text()

        for marker in (
            "biobank-jupyter-server-broker",
            "biobank-jupyter-proxy-reconciler",
            "biobank-runtime-brokers",
            "biobank-jupyter-proxy-reconciler.service",
            "biobank-jupyter-proxy-reconciler.timer",
            "/etc/httpd/biobank",
            "/run/biobank-jupyter-proxy",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_cutover_does_not_modify_ood_generator(self):
        source = DEPLOY.read_text()

        self.assertNotIn(
            "/etc/ood/config/ood_portal.yml",
            source,
        )
        self.assertNotIn(
            "update_ood_portal",
            source,
        )
        self.assertIn(
            'LEGACY_OOD_PROXY="/etc/ood/config/'
            'biobank-node-proxy.conf"',
            source,
        )

    def test_cutover_avoids_mixed_application_proxy_state(self):
        source = DEPLOY.read_text()

        forward_start = source.index(
            'echo "5. ENTER CONTROL-PLANE QUIESCENCE"'
        )
        stop_index = source.index(
            "systemctl stop biobank",
            forward_start,
        )
        runtime_index = source.index(
            'echo "6. INSTALL RUNTIME COMPONENTS"',
            forward_start,
        )
        link_index = source.index(
            'mv -Tf \\\n'
            '    "$TEMP_CURRENT" \\\n'
            '    "$CURRENT_LINK"'
        )
        reload_index = source.index(
            "systemctl reload httpd",
            link_index,
        )
        start_index = source.index(
            "systemctl start biobank",
            reload_index,
        )

        self.assertLess(
            stop_index,
            runtime_index,
        )
        self.assertLess(
            runtime_index,
            link_index,
        )
        self.assertLess(
            link_index,
            reload_index,
        )
        self.assertLess(
            reload_index,
            start_index,
        )

    def test_cutover_rechecks_sessions_after_stopping_control_plane(self):
        source = DEPLOY.read_text()

        stop_index = source.index(
            "systemctl stop biobank"
        )
        second_gate_index = source.index(
            'fail "A managed Jupyter session appeared before cutover."'
        )
        runtime_index = source.index(
            'echo "6. INSTALL RUNTIME COMPONENTS"'
        )

        self.assertLess(
            stop_index,
            second_gate_index,
        )
        self.assertLess(
            second_gate_index,
            runtime_index,
        )

    def test_failed_deployment_removes_owned_target_release(self):
        source = DEPLOY.read_text()
        normalized = normalize_shell(
            source
        )

        for marker in (
            "TARGET_RELEASE_CREATED=0",
            "TARGET_RELEASE_CREATED=1",
            "cleanup_failed_release()",
            'rm -rf -- "$TARGET_RELEASE"',
        ):
            self.assertIn(
                marker,
                normalized,
            )

    def test_interrupts_use_the_same_rollback_path(self):
        source = DEPLOY.read_text()

        for marker in (
            "on_signal()",
            "trap 'on_signal INT 130' INT",
            "trap 'on_signal TERM 143' TERM",
            "trap 'on_signal HUP 129' HUP",
            "rollback \"$rc\"",
            "cleanup_failed_release",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_reconciler_rollback_returns_to_absent_baseline(self):
        source = DEPLOY.read_text()
        normalized = normalize_shell(
            source
        )

        for marker in (
            'test ! -e "$LIVE_RECONCILER"',
            'test ! -e "$SERVICE_UNIT"',
            'test ! -e "$TIMER_UNIT"',
            '"$LIVE_RECONCILER" "$SERVICE_UNIT" "$TIMER_UNIT"',
        ):
            self.assertIn(
                marker,
                normalized,
            )

    def test_cutover_has_automatic_rollback(self):
        source = DEPLOY.read_text()

        for marker in (
            "rollback()",
            "on_error()",
            "trap on_error ERR",
            "biobank.conf.before",
            "biobank-node-proxy.conf.before",
            "jupyter-server-broker.before",
            "runtime-brokers.sudoers.before",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_cutover_records_manifest_and_boundary_results(self):
        source = DEPLOY.read_text()

        for marker in (
            "storage/manifests/deployment",
            "before.sha256",
            "after.sha256",
            "control_http=",
            "incomplete_tuple_http=",
            "data_plane_fake_http=",
            "result.txt",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_cutover_does_not_retire_legacy_helpers_yet(self):
        source = DEPLOY.read_text()

        self.assertNotIn(
            "rm -f -- "
            "/usr/local/sbin/"
            "biobank-jupyter-server-runner",
            source,
        )
        self.assertNotIn(
            "rm -f -- "
            "/usr/local/sbin/"
            "biobank-user-storage",
            source,
        )
        self.assertNotIn(
            "rm -f -- "
            "/etc/sudoers.d/"
            "biobank-lab-tools",
            source,
        )

    def test_cutover_does_not_change_static_current(self):
        source = DEPLOY.read_text()

        self.assertNotIn(
            'mv -Tf "$TEMP_STATIC"',
            source,
        )
        self.assertNotIn(
            'ln -s "static-releases/',
            source,
        )
        self.assertIn(
            'static_current=$(readlink '
            '"$APP_ROOT/static-current")',
            source,
        )
