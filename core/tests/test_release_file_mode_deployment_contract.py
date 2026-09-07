from pathlib import Path
import subprocess

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]

DEPLOY = (
    ROOT
    / "deploy"
    / "operations"
    / "deploy_independent_jupyter.sh"
)


class ReleaseFileModeDeploymentContractTests(
    SimpleTestCase
):
    def test_git_executable_modes_are_restored_before_publish(
        self,
    ):
        source = DEPLOY.read_text()

        for marker in (
            'repo_git ls-tree',
            '-rz',
            '"$TARGET_COMMIT"',
            'test "$git_mode" = "100755"',
            'chmod 0750 --',
            '"$release_path"',
            'git_executable_mode_contract=PASS',
        ):
            self.assertIn(
                marker,
                source,
            )

    def test_restricted_release_policy_precedes_exec_restore(
        self,
    ):
        source = DEPLOY.read_text()

        regular_index = source.index(
            "-exec chmod 0640 {} +"
        )

        executable_tree_index = source.index(
            "RELEASE_GIT_EXECUTABLE_COUNT=0"
        )

        executable_mode_index = source.index(
            "chmod 0750 --"
        )

        publish_index = source.index(
            'mv \\\n'
            '    "$STAGE_RELEASE" \\\n'
            '    "$TARGET_RELEASE"'
        )

        self.assertLess(
            regular_index,
            executable_tree_index,
        )

        self.assertLess(
            executable_tree_index,
            executable_mode_index,
        )

        self.assertLess(
            executable_mode_index,
            publish_index,
        )

    def test_release_mode_mapping_is_documented(
        self,
    ):
        source = DEPLOY.read_text()

        self.assertIn(
            "Git 100644 -> release 0640",
            source,
        )

        self.assertIn(
            "Git 100755 -> release 0750",
            source,
        )

    def test_git_tree_paths_are_nul_delimited(
        self,
    ):
        source = DEPLOY.read_text()

        self.assertIn(
            'while IFS= read -r -d "" record',
            source,
        )

        self.assertIn(
            "Unsafe executable path in Git tree",
            source,
        )

        # ls-tree separates metadata and pathname with a real TAB.
        # The shell source must therefore contain $'\\t', not a
        # doubly escaped literal backslash+t sequence.
        self.assertIn(
            "$'\\t'",
            source,
        )

        self.assertNotIn(
            "$'\\\\t'",
            source,
        )

    def test_git_tree_inventory_failure_cannot_be_swallowed(
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

    def test_executable_counter_runs_as_arithmetic_expansion(
        self,
    ):
        source = DEPLOY.read_text()

        expected = (
            "RELEASE_GIT_EXECUTABLE_COUNT="
            "$((RELEASE_GIT_EXECUTABLE_COUNT + 1))"
        )

        self.assertIn(
            expected,
            source,
        )

        self.assertNotIn(
            "RELEASE_GIT_EXECUTABLE_COUNT=$(\n"
            "        (",
            source,
        )

        completed = subprocess.run(
            [
                "bash",
                "-c",
                (
                    "set -euo pipefail\n"
                    "RELEASE_GIT_EXECUTABLE_COUNT=0\n"
                    f"{expected}\n"
                    'test "$RELEASE_GIT_EXECUTABLE_COUNT" -eq 1\n'
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=completed.stderr,
        )
