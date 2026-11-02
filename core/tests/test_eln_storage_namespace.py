"""ELN private namespace contract tests.

No production database or user-home writes.
"""

from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import SuspiciousFileOperation
from django.test import SimpleTestCase

from core.services import lab_tools_storage as storage


ENTRY = "11111111-1111-4111-8111-111111111111"

RELATIVE = (
    f"eln/projects/validation/entries/{ENTRY}/"
    "revisions/r000001.json"
)


class ElnStorageNamespaceTests(SimpleTestCase):

    def test_eln_namespace_already_authorized(self):
        self.assertIn(
            "eln",
            storage.ALLOWED_AREAS,
        )

        self.assertEqual(
            storage._validated_relative_path(
                RELATIVE
            ).as_posix(),
            RELATIVE,
        )

    def test_logical_to_physical_mapping(self):
        root = Path(
            "/home/analyst/biobank/lab_tools"
        )

        logical = "users/analyst/" + RELATIVE

        with patch.object(
            storage,
            "user_lab_tools_root",
            return_value=root,
        ):
            actual = Path(
                storage.UserHomeLabToolsStorage().path(
                    logical
                )
            )

        self.assertEqual(
            actual,
            root / RELATIVE,
        )

    def test_user_roots_are_distinct(self):
        def root_for(username):
            return Path(
                f"/home/{username}/biobank/lab_tools"
            )

        with patch.object(
            storage,
            "user_lab_tools_root",
            side_effect=root_for,
        ):
            alice = storage.protected_user_path(
                "alice",
                RELATIVE,
            )

            bob = storage.protected_user_path(
                "bob",
                RELATIVE,
            )

        self.assertNotEqual(alice, bob)

        self.assertEqual(
            alice,
            Path(
                "/home/alice/biobank/lab_tools"
            ) / RELATIVE,
        )

        self.assertEqual(
            bob,
            Path(
                "/home/bob/biobank/lab_tools"
            ) / RELATIVE,
        )

    def test_path_traversal_rejected(self):
        invalid = (
            "../eln/file.json",
            "eln/../../private.json",
            "/tmp/outside.json",
            "unapproved/private.json",
            r"eln\outside.json",
        )

        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(
                    SuspiciousFileOperation
                ):
                    storage._validated_relative_path(
                        value
                    )

    def test_no_unapproved_namespace(self):
        self.assertNotIn(
            "unapproved",
            storage.ALLOWED_AREAS,
        )
