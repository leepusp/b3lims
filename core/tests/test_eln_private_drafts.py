"""Private ELN tests without filesystem or database writes."""

from io import BytesIO
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase

from core.services.eln_private_drafts import (
    PrivateDraftRepository,
    DraftConflict,
    DraftNotFound,
    DraftValidationError,
    logical_revision_path,
)


class MemoryStorage:
    def __init__(self):
        self.files = {}

    def _save(self, name, content):
        if name in self.files:
            raise FileExistsError(name)

        self.files[name] = content.read()
        return name

    def _open(self, name, mode="rb"):
        if name not in self.files:
            raise FileNotFoundError(name)

        return BytesIO(self.files[name])

    def listdir(self, path):
        prefix = path.rstrip("/") + "/"

        matches = [
            name[len(prefix):]
            for name in self.files
            if name.startswith(prefix)
        ]

        if not matches:
            raise FileNotFoundError(path)

        directories = set()
        files = set()

        for name in matches:
            head, separator, _tail = name.partition("/")

            if separator:
                directories.add(head)
            else:
                files.add(head)

        return sorted(directories), sorted(files)


def user(username="analyst"):
    return SimpleNamespace(
        is_authenticated=True,
        is_active=True,
        get_username=lambda: username,
    )


class PrivateDraftRepositoryTests(SimpleTestCase):
    def setUp(self):
        self.storage = MemoryStorage()
        self.repo = PrivateDraftRepository(
            self.storage
        )
        self.owner = user()

    def create(self, **overrides):
        values = {
            "title": "Experiment A",
            "content": "Initial observation",
            "protocol": "Protocol v1",
        }
        values.update(overrides)

        return self.repo.create(
            self.owner,
            "T2SS",
            **values,
        )

    def test_create_and_read_private_entry(self):
        entry = self.create()

        self.assertEqual(entry["revision"], 1)
        self.assertEqual(entry["owner"], "analyst")
        self.assertEqual(entry["project"], "T2SS")
        self.assertEqual(entry["status"], "draft")

        loaded = self.repo.latest(
            self.owner, "T2SS", entry["entry_id"]
        )

        self.assertEqual(loaded, entry)
        self.assertEqual(len(self.storage.files), 1)

    def test_revision_is_immutable(self):
        entry = self.create()

        updated = self.repo.revise(
            self.owner,
            "T2SS",
            entry["entry_id"],
            expected_revision=1,
            title="Experiment A revised",
            content="Second observation",
        )

        original = self.repo.read_revision(
            self.owner, "T2SS",
            entry["entry_id"], 1
        )

        self.assertEqual(original["title"], "Experiment A")
        self.assertEqual(
            updated["title"], "Experiment A revised"
        )
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(len(self.storage.files), 2)

    def test_stale_revision_cannot_overwrite(self):
        entry = self.create()

        self.repo.revise(
            self.owner, "T2SS",
            entry["entry_id"],
            expected_revision=1,
            title="Version 2",
        )

        with self.assertRaises(DraftConflict):
            self.repo.revise(
                self.owner, "T2SS",
                entry["entry_id"],
                expected_revision=1,
                title="Stale edit",
            )

        self.assertEqual(len(self.storage.files), 2)

    def test_project_listing(self):
        self.create(title="First")
        self.create(title="Second")

        entries = self.repo.list_entries(
            self.owner, "T2SS"
        )

        self.assertEqual(len(entries), 2)

    def test_other_user_cannot_read_owner_entry(self):
        entry = self.create()

        with self.assertRaises(DraftNotFound):
            self.repo.latest(
                user("another"),
                "T2SS",
                entry["entry_id"],
            )

    def test_unauthenticated_user_rejected(self):
        anonymous = SimpleNamespace(
            is_authenticated=False,
            is_active=False,
            get_username=lambda: "analyst",
        )

        with self.assertRaises(PermissionDenied):
            self.repo.create(
                anonymous,
                "T2SS",
                title="Unauthorized",
            )

    def test_project_traversal_rejected(self):
        for project in (
            "../private",
            "T..SS",
            "/tmp",
            "project/subdir",
            ".",
            "..",
        ):
            with self.subTest(project=project):
                with self.assertRaises(
                    DraftValidationError
                ):
                    self.repo.create(
                        self.owner,
                        project,
                        title="Invalid",
                    )

    def test_material_links_require_authorization(self):
        with self.assertRaises(
            DraftValidationError
        ):
            self.create(sample_ids=[123])

        self.assertEqual(len(self.storage.files), 0)

    def test_authorized_material_links(self):
        calls = []

        def authorize(who, samples, chemicals):
            calls.append((who, samples, chemicals))
            return True

        entry = self.create(
            sample_ids=[123],
            chemical_ids=[456],
            material_authorizer=authorize,
        )

        self.assertEqual(entry["sample_ids"], [123])
        self.assertEqual(entry["chemical_ids"], [456])
        self.assertEqual(len(calls), 1)

    def test_denied_material_links(self):
        with self.assertRaises(PermissionDenied):
            self.create(
                sample_ids=[123],
                material_authorizer=lambda *_: False,
            )

        self.assertEqual(len(self.storage.files), 0)

    def test_revision_name_contract(self):
        entry = self.create()

        path = logical_revision_path(
            "analyst",
            "T2SS",
            entry["entry_id"],
            1,
        )

        self.assertEqual(
            path,
            (
                f"users/analyst/eln/projects/T2SS/"
                f"entries/{entry['entry_id']}/"
                "revisions/r000001.json"
            ),
        )

    def test_duplicate_revision_cannot_replace_file(self):
        entry = self.create()

        name = logical_revision_path(
            "analyst",
            "T2SS",
            entry["entry_id"],
            1,
        )

        before = self.storage.files[name]

        with self.assertRaises(FileExistsError):
            self.repo._write(
                self.owner,
                "T2SS",
                entry["entry_id"],
                1,
                title="Overwrite attempt",
                content="",
                protocol="",
                results="",
                sample_ids=(),
                chemical_ids=(),
                material_authorizer=None,
            )

        self.assertEqual(
            self.storage.files[name],
            before,
        )
