"""Regression tests for private ELN broker policies.

Tests inspect versioned broker source without running
privileged actions or accessing researcher files.
"""

import ast
import re
import subprocess

from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]

SHELL_PATH = (
    ROOT / "deploy/sbin/biobank-user-storage"
)

PYTHON_PATH = (
    ROOT / "deploy/sbin/biobank-user-storage-broker"
)

ENTRY = (
    "550e8400-e29b-41d4-a716-446655440000"
)

DIRECTORY = (
    f"eln/projects/T2SS/entries/{ENTRY}/revisions"
)

FILE = DIRECTORY + "/r000001.json"


def python_broker_pattern(name):
    source = ast.parse(
        PYTHON_PATH.read_text(encoding="utf-8")
    )

    for node in source.body:
        if not isinstance(node, ast.Assign):
            continue

        targets = [
            target.id
            for target in node.targets
            if isinstance(target, ast.Name)
        ]

        if name not in targets:
            continue

        call = node.value

        if not isinstance(call, ast.Call):
            raise AssertionError(
                "Unexpected broker regex structure."
            )

        pattern = ast.literal_eval(
            call.args[0]
        )

        return re.compile(pattern)

    raise AssertionError(
        f"Missing broker pattern: {name}"
    )


def shell_function(name):
    source = SHELL_PATH.read_text(
        encoding="utf-8"
    )

    marker = name + "() {"

    if source.count(marker) != 1:
        raise AssertionError(
            f"Missing Shell broker function: {name}"
        )

    start = source.index(marker)
    remaining = source[start:]

    end = remaining.find("\n}\n")

    if end < 0:
        raise AssertionError(
            "Unexpected Shell function boundary."
        )

    return remaining[:end + 3]


def shell_accepts(function_name, path):
    function = shell_function(function_name)

    script = (
        "fail() { exit 2; }\n"
        + function
        + "\n"
        + function_name
        + ' "$1"\n'
    )

    result = subprocess.run(
        ["bash", "-c", script, "_", path],
        capture_output=True,
        text=True,
        timeout=5,
    )

    return result.returncode == 0


class PrivateElnBrokerPolicyTests(SimpleTestCase):

    def assert_policy(
        self,
        path,
        *,
        directory,
        allowed,
    ):
        python_name = (
            "LAB_DIRECTORY_RE"
            if directory
            else "LAB_FILE_RE"
        )

        shell_name = (
            "validate_relative_directory"
            if directory
            else "validate_relative_file"
        )

        python_matches = bool(
            python_broker_pattern(
                python_name
            ).fullmatch(path)
        )

        shell_matches = shell_accepts(
            shell_name,
            path,
        )

        self.assertEqual(
            python_matches,
            allowed,
            f"Python broker: {path}",
        )

        self.assertEqual(
            shell_matches,
            allowed,
            f"Shell broker: {path}",
        )

    def test_private_revision_directory(self):
        self.assert_policy(
            DIRECTORY,
            directory=True,
            allowed=True,
        )

    def test_private_revision_files(self):
        for revision in (
            "r000001.json",
            "r000010.json",
            "r999999.json",
        ):
            with self.subTest(revision=revision):
                self.assert_policy(
                    DIRECTORY + "/" + revision,
                    directory=False,
                    allowed=True,
                )

    def test_legacy_attachment_directory(self):
        self.assert_policy(
            "eln/entries/123/attachments",
            directory=True,
            allowed=True,
        )

    def test_legacy_attachment_file(self):
        self.assert_policy(
            "eln/entries/123/attachments/raw.dat",
            directory=False,
            allowed=True,
        )

    def test_new_parent_directories_not_claimable(self):
        for path in (
            "eln/projects",
            "eln/projects/T2SS",
            "eln/projects/T2SS/entries",
            f"eln/projects/T2SS/entries/{ENTRY}",
        ):
            with self.subTest(path=path):
                self.assert_policy(
                    path,
                    directory=True,
                    allowed=False,
                )

    def test_invalid_revision_files_rejected(self):
        for path in (
            DIRECTORY + "/notes.txt",
            DIRECTORY + "/r1.json",
            DIRECTORY + "/r000001.json.bak",
            DIRECTORY + "/r000001.json/extra",
            DIRECTORY + "/../r000001.json",
            DIRECTORY + "/r000001.JSON",
        ):
            with self.subTest(path=path):
                self.assert_policy(
                    path,
                    directory=False,
                    allowed=False,
                )

    def test_invalid_entry_identifiers_rejected(self):
        for invalid in (
            "123",
            ENTRY.upper(),
            "550e8400-e29b-11d4-a716-446655440000",
            "550e8400-e29b-41d4-7716-446655440000",
        ):
            path = (
                "eln/projects/T2SS/entries/"
                + invalid
                + "/revisions"
            )

            with self.subTest(entry=invalid):
                self.assert_policy(
                    path,
                    directory=True,
                    allowed=False,
                )

    def test_project_traversal_rejected(self):
        for path in (
            "../eln/projects/T2SS",
            "/eln/projects/T2SS",
            "eln/projects/../entries",
            (
                "eln/projects/T2SS/entries/"
                + ENTRY
                + "/../../revisions"
            ),
        ):
            with self.subTest(path=path):
                self.assert_policy(
                    path,
                    directory=True,
                    allowed=False,
                )

    def test_unrelated_paths_remain_denied(self):
        for path in (
            "eln/unapproved/file.json",
            "projects/T2SS/revisions/r000001.json",
            "tmp/../eln/private.json",
        ):
            with self.subTest(path=path):
                self.assert_policy(
                    path,
                    directory=False,
                    allowed=False,
                )
