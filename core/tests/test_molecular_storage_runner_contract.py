from pathlib import Path
import subprocess

from django.conf import settings
from django.test import SimpleTestCase


class MolecularStorageRunnerContractTests(SimpleTestCase):
    def runner_source(self):
        return Path(
            settings.BASE_DIR,
            "deploy/sbin/biobank-user-storage",
        )

    def test_runner_shell_syntax_is_valid(self):
        runner = self.runner_source()

        result = subprocess.run(
            [
                "bash",
                "-n",
                str(runner),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.returncode,
            0,
            result.stderr,
        )

    def test_runner_allows_only_managed_alignment_subdirectory(self):
        source = self.runner_source().read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "molecular/records/[0-9]+/alignments",
            source,
        )

        self.assertIn(
            (
                "molecular/records/[0-9]+/"
                "alignments/[A-Za-z0-9_.-]+"
            ),
            source,
        )

        self.assertNotIn(
            "molecular/sequences",
            source,
        )

        # Do not broaden molecular storage to arbitrary
        # record subdirectories.
        self.assertNotIn(
            (
                "molecular/records/[0-9]+/"
                "[A-Za-z0-9_.-]+/"
                "[A-Za-z0-9_.-]+"
            ),
            source,
        )
