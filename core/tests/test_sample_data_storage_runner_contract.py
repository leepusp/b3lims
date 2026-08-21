from pathlib import Path
import subprocess

from django.conf import settings
from django.test import SimpleTestCase


class SampleDataStorageRunnerContractTests(SimpleTestCase):
    def runner_source(self):
        return Path(
            settings.BASE_DIR,
            "deploy/sbin/biobank-user-storage",
        )

    def test_runner_shell_syntax_is_valid(self):
        runner = self.runner_source()

        result = subprocess.run(
            ["bash", "-n", str(runner)],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.returncode,
            0,
            result.stderr,
        )

    def test_runner_keeps_lab_tools_structure_support(self):
        source = self.runner_source().read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "molecular/records/[0-9]+/structures",
            source,
        )
        self.assertIn(
            (
                "molecular/records/[0-9]+/"
                "structures/[A-Za-z0-9_.-]+"
            ),
            source,
        )

    def test_ensure_provisions_separate_data_root(self):
        source = self.runner_source().read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'DATA_RELATIVE_ROOT="biobank/data"',
            source,
        )
        self.assertIn(
            '"$DATA_ROOT/samples"',
            source,
        )
        self.assertIn(
            '"$LAB_ROOT"',
            source,
        )

    def test_sample_data_directory_is_strictly_scoped(self):
        source = self.runner_source().read_text(
            encoding="utf-8"
        )

        self.assertIn(
            (
                "^samples/sample_[0-9]+_"
                "[A-Za-z0-9._-]+/files$"
            ),
            source,
        )

        self.assertNotIn(
            "samples/.*",
            source,
        )

    def test_sample_data_file_is_strictly_scoped(self):
        source = self.runner_source().read_text(
            encoding="utf-8"
        )

        self.assertIn(
            (
                "^samples/sample_[0-9]+_"
                "[A-Za-z0-9._-]+/files/"
            ),
            source,
        )

        self.assertIn(
            "claim-data-file",
            source,
        )

    def test_legacy_lab_tools_actions_remain_available(self):
        source = self.runner_source().read_text(
            encoding="utf-8"
        )

        for action in (
            "ensure)",
            "prepare-directory)",
            "claim-file)",
        ):
            self.assertIn(action, source)

    def test_sample_data_has_distinct_actions(self):
        source = self.runner_source().read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "prepare-data-directory)",
            source,
        )
        self.assertIn(
            "claim-data-file)",
            source,
        )

    def test_data_paths_are_resolved_below_data_root(self):
        source = self.runner_source().read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'realpath -m -- "$DATA_ROOT/$relative"',
            source,
        )
        self.assertIn(
            '"$candidate" == "$DATA_ROOT/"*',
            source,
        )
