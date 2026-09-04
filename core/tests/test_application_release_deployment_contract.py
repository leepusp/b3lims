from pathlib import Path
import stat

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]

DEPLOY = (
    ROOT
    / "deploy"
    / "operations"
    / "deploy_application_release.sh"
)


class ApplicationReleaseDeploymentContractTests(
    SimpleTestCase
):
    def test_deploy_source_is_versioned_and_executable(
        self,
    ):
        self.assertTrue(
            DEPLOY.is_file()
        )

        self.assertTrue(
            DEPLOY.stat().st_mode
            & stat.S_IXUSR
        )

    def test_shell_error_model_does_not_inherit_err_into_subshells(
        self,
    ):
        source = DEPLOY.read_text()

        self.assertIn(
            "set -euo pipefail",
            source,
        )

        self.assertNotIn(
            "set -Eeuo pipefail",
            source,
        )

    def test_read_only_preflight_precedes_manifest_and_mutation(
        self,
    ):
        source = DEPLOY.read_text()

        preflight = source.index(
            'echo "=== 1. Read-only preflight ==="'
        )

        preflight_exit = source.index(
            'if test "$MODE" = "preflight"'
        )

        manifest = source.index(
            'echo "=== 2. Create deployment manifest ==="'
        )

        mutation = source.index(
            "MUTATED=1"
        )

        self.assertLess(
            preflight,
            preflight_exit,
        )

        self.assertLess(
            preflight_exit,
            manifest,
        )

        self.assertLess(
            manifest,
            mutation,
        )

        self.assertIn(
            "production_modified=NO",
            source,
        )

    def test_exact_git_commit_and_clean_source_are_required(
        self,
    ):
        source = DEPLOY.read_text()

        for marker in (
            'repo_git rev-parse HEAD',
            'repo_git status --porcelain=v1',
            'repo_git cat-file',
            '"${TARGET_COMMIT}^{commit}"',
            '^[0-9a-f]{40}$',
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_application_only_deploy_rejects_schema_and_static_changes(
        self,
    ):
        source = DEPLOY.read_text()

        self.assertIn(
            "Generic application deploy refuses migration changes.",
            source,
        )

        self.assertIn(
            "Generic application deploy refuses static asset changes.",
            source,
        )

        self.assertIn(
            "grep -Eq '(^|/)migrations/.*\\.py$'",
            source,
        )

        self.assertIn(
            "grep -Eq '(^|/)static/'",
            source,
        )

    def test_immutable_release_preserves_git_executable_semantics(
        self,
    ):
        source = DEPLOY.read_text()

        for marker in (
            'repo_git archive "$TARGET_COMMIT"',
            "-exec chmod 0640 {} +",
            "repo_git ls-tree",
            "-rz",
            'test "$git_mode" = "100755"',
            "chmod 0750 --",
            "git_executable_mode_contract=PASS",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_git_tree_inventory_is_materialized_fail_closed(
        self,
    ):
        source = DEPLOY.read_text()

        for marker in (
            'GIT_TREE_FILE="$MANIFEST/target-tree.z"',
            'repo_git ls-tree',
            '> "$GIT_TREE_FILE"',
            'test -s "$GIT_TREE_FILE"',
            'done < "$GIT_TREE_FILE"',
        ):
            self.assertIn(
                marker,
                source,
            )

        self.assertNotIn(
            'done < <(\n'
            '    repo_git ls-tree',
            source,
        )

    def test_generated_python_artifacts_are_rejected(
        self,
    ):
        source = DEPLOY.read_text()

        for marker in (
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "Generated Python artifacts exist in committed release.",
            "Validation generated Python artifacts in staged release.",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_stage_is_validated_before_immutable_publish(
        self,
    ):
        source = DEPLOY.read_text()

        validation = source.index(
            'echo "=== 4. Validate staged application before publication ==="'
        )

        test_index = source.index(
            '"$PY" manage.py test'
        )

        publish = source.index(
            'echo "=== 5. Publish immutable release ==="'
        )

        cutover = source.index(
            'echo "=== 7. Atomic application cutover ==="'
        )

        self.assertLess(
            validation,
            test_index,
        )

        self.assertLess(
            test_index,
            publish,
        )

        self.assertLess(
            publish,
            cutover,
        )

    def test_error_and_signal_paths_converge_on_abort_and_rollback(
        self,
    ):
        source = DEPLOY.read_text()

        for marker in (
            "abort_deployment()",
            "rollback()",
            "cleanup_failed_release()",
            "on_error()",
            "on_signal()",
            "trap on_error ERR",
            "trap 'on_signal INT 130' INT",
            "trap 'on_signal TERM 143' TERM",
            "trap 'on_signal HUP 129' HUP",
            'rollback "$rc"',
            "cleanup_failed_release",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_rollback_is_idempotent_and_fail_closed(
        self,
    ):
        source = DEPLOY.read_text()

        for marker in (
            "ROLLBACK_DONE=0",
            'test "$ROLLBACK_DONE" -eq 1',
            "ROLLBACK_DONE=1",
            "rollback_safe=1",
            "rollback_safe=0",
            "rollback_contract=RESTORED",
            "rollback_contract=INCOMPLETE_FAIL_CLOSED",
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_post_cutover_contract_preserves_static_and_security_boundaries(
        self,
    ):
        source = DEPLOY.read_text()

        for marker in (
            'test "$STATIC_AFTER" = "$STATIC_BEFORE"',
            'OPTIONS "/public/"',
            '"/public/shipments/"',
            '"/workspace/"',
            "allow_header_contract=PASS",
            "normalized_allow",
            "GET, HEAD",
            "runtime_identity=PASS",
        ):
            self.assertIn(
                marker,
                source,
            )
