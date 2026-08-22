import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile

from django.conf import settings
from django.test import SimpleTestCase


def load_broker_module():
    source = (
        Path(settings.BASE_DIR)
        / "deploy/sbin/biobank-user-storage-broker"
    )

    name = "biobank_storage_broker_security_test"

    loader = importlib.machinery.SourceFileLoader(
        name,
        str(source),
    )

    spec = importlib.util.spec_from_loader(
        name,
        loader,
    )

    module = importlib.util.module_from_spec(
        spec
    )

    loader.exec_module(module)

    return module


class StorageBrokerSecurityTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.broker = load_broker_module()

    def test_directory_open_rejects_symlink_component(self):
        broker = self.broker

        with tempfile.TemporaryDirectory() as root:
            outside = Path(root) / "outside"
            outside.mkdir()

            parent = Path(root) / "parent"
            parent.mkdir()

            (parent / "managed").symlink_to(
                outside,
                target_is_directory=True,
            )

            parent_fd = os.open(
                parent,
                broker.DIRECTORY_FLAGS,
            )

            try:
                with self.assertRaises(
                    broker.BrokerError
                ):
                    broker._open_existing_directory(
                        parent_fd,
                        "managed",
                    )
            finally:
                os.close(parent_fd)

    def test_regular_file_open_rejects_symlink(self):
        broker = self.broker

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)

            outside = root_path / "outside.txt"
            outside.write_text("outside\n")

            (root_path / "managed.txt").symlink_to(
                outside
            )

            parent_fd = os.open(
                root_path,
                broker.DIRECTORY_FLAGS,
            )

            try:
                with self.assertRaises(
                    broker.BrokerError
                ):
                    broker._open_regular_file(
                        parent_fd,
                        "managed.txt",
                        os.fstat(parent_fd).st_dev,
                    )
            finally:
                os.close(parent_fd)

    def test_directory_open_accepts_real_directory(self):
        broker = self.broker

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)

            managed = root_path / "managed"
            managed.mkdir()

            parent_fd = os.open(
                root_path,
                broker.DIRECTORY_FLAGS,
            )

            try:
                child_fd = (
                    broker._open_existing_directory(
                        parent_fd,
                        "managed",
                        os.fstat(parent_fd).st_dev,
                    )
                )
            finally:
                os.close(parent_fd)

            try:
                self.assertTrue(
                    os.path.isdir(
                        f"/proc/self/fd/{child_fd}"
                    )
                )
            finally:
                os.close(child_fd)

    def test_jupyter_notebook_is_an_explicit_claimable_file(self):
        broker = self.broker

        self.assertIsNotNone(
            broker.LAB_FILE_RE.fullmatch(
                "jupyter/notebooks/notebook_42/notebook.ipynb"
            )
        )

        self.assertIsNone(
            broker.LAB_FILE_RE.fullmatch(
                "jupyter/notebooks/notebook_42/other.txt"
            )
        )

    def test_private_acl_contract_removes_primary_group_access(self):
        broker = self.broker

        context = broker.UserContext(
            username="exampleuser",
            uid=os.getuid(),
            gid=os.getgid(),
            home="/home/exampleuser",
        )

        self.assertIn(
            "u:biobank:rwx",
            broker._directory_acl(context),
        )
        self.assertIn(
            "g::---",
            broker._directory_acl(context),
        )

        self.assertIn(
            "u:biobank:rw-",
            broker._file_acl(context),
        )
        self.assertIn(
            "g::---",
            broker._file_acl(context),
        )
