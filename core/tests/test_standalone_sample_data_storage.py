"""Standalone SampleFile storage regression tests."""

import tempfile
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import (
    SimpleTestCase,
    TestCase,
    override_settings,
)

from core.models.samples.sample import Sample
from core.models.samples.sample_files import SampleFile
from core.services.sample_data_storage import (
    UserHomeSampleDataStorage,
)


STANDALONE_RUNTIME = (
    getattr(
        settings,
        "BIOBANK_RUNTIME_PROFILE",
        None,
    )
    == "standalone"
)


@skipUnless(
    STANDALONE_RUNTIME,
    "Standalone Sample storage tests require standalone settings.",
)
class StandaloneSampleDataStorageTests(
    SimpleTestCase
):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        self.addCleanup(
            self.temporary_directory.cleanup
        )

        self.local_root = Path(
            self.temporary_directory.name
        )

        self.sample_data_root = (
            self.local_root
            / "storage"
            / "sample_data"
        )

        self.settings_override = (
            override_settings(
                BIOBANK_LOCAL_ROOT=(
                    self.local_root
                ),
                BIOBANK_STORAGE_ROOT=(
                    self.local_root
                    / "storage"
                ),
                BIOBANK_SAMPLE_DATA_ROOT=(
                    self.sample_data_root
                ),
            )
        )

        self.settings_override.enable()

        self.addCleanup(
            self.settings_override.disable
        )

        self.storage = (
            UserHomeSampleDataStorage()
        )

    def test_path_uses_local_sample_data_root(
        self,
    ):
        name = (
            "users/localuser/"
            "samples/"
            "sample_18_LOCAL-001/"
            "files/report.txt"
        )

        expected = (
            self.sample_data_root
            / "users"
            / "localuser"
            / "samples"
            / "sample_18_LOCAL-001"
            / "files"
            / "report.txt"
        )

        self.assertEqual(
            Path(
                self.storage.path(name)
            ),
            expected,
        )

    def test_save_does_not_require_unix_account_or_runner(
        self,
    ):
        name = (
            "users/localuser/"
            "samples/"
            "sample_18_LOCAL-001/"
            "files/report.txt"
        )

        with (
            patch(
                "core.services."
                "sample_data_storage."
                "user_home_for_username"
            ) as unix_home,
            patch(
                "core.services."
                "sample_data_storage."
                "_run_sample_data_runner"
            ) as protected_runner,
        ):
            saved = self.storage.save(
                name,
                ContentFile(
                    b"standalone-sample-data\n"
                ),
            )

        unix_home.assert_not_called()
        protected_runner.assert_not_called()

        self.assertEqual(
            saved,
            name,
        )

        physical = Path(
            self.storage.path(
                saved
            )
        )

        self.assertTrue(
            physical.is_file()
        )

        self.assertEqual(
            physical.read_bytes(),
            b"standalone-sample-data\n",
        )

    def test_local_file_remains_private_from_storage_url(
        self,
    ):
        name = (
            "users/localuser/"
            "samples/"
            "sample_18_LOCAL-001/"
            "files/report.txt"
        )

        with self.assertRaises(
            ValueError
        ):
            self.storage.url(
                name
            )



@skipUnless(
    STANDALONE_RUNTIME,
    "Standalone Sample storage tests require standalone settings.",
)
class StandaloneSampleFileModelTests(TestCase):
    def setUp(self):
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        self.addCleanup(
            self.temporary_directory.cleanup
        )

        self.sample_data_root = (
            Path(
                self.temporary_directory.name
            )
            / "sample_data"
        )

        self.settings_override = (
            override_settings(
                BIOBANK_SAMPLE_DATA_ROOT=(
                    self.sample_data_root
                ),
            )
        )

        self.settings_override.enable()

        self.addCleanup(
            self.settings_override.disable
        )

    def test_samplefile_model_upload_is_local_and_persistent(
        self,
    ):
        user = (
            get_user_model()
            .objects
            .create_user(
                username="localinventoryuser",
                password="test-password",
            )
        )

        sample = Sample.objects.create(
            sample_id="LOCAL-MODEL-001",
            sample_type="Other",
            organism_name="Standalone model smoke",
            owner=user,
        )

        record = SampleFile(
            sample=sample,
            description="Standalone model upload",
        )

        with (
            patch(
                "core.services."
                "sample_data_storage."
                "user_home_for_username"
            ) as unix_home,
            patch(
                "core.services."
                "sample_data_storage."
                "_run_sample_data_runner"
            ) as protected_runner,
        ):
            record.file.save(
                "model-test.txt",
                ContentFile(
                    b"standalone-model-file\n"
                ),
                save=True,
            )

        unix_home.assert_not_called()
        protected_runner.assert_not_called()

        record_pk = record.pk

        expected_name = (
            "users/localinventoryuser/"
            "samples/"
            f"sample_{sample.pk}_LOCAL-MODEL-001/"
            "files/model-test.txt"
        )

        self.assertEqual(
            record.file.name,
            expected_name,
        )

        physical = Path(
            record.file.path
        )

        self.assertTrue(
            physical.is_file()
        )

        self.assertEqual(
            physical.read_bytes(),
            b"standalone-model-file\n",
        )

        reloaded = (
            SampleFile.objects.get(
                pk=record_pk
            )
        )

        self.assertEqual(
            reloaded.file.name,
            expected_name,
        )

        with reloaded.file.open("rb") as handle:
            self.assertEqual(
                handle.read(),
                b"standalone-model-file\n",
            )

        expected_root = (
            self.sample_data_root
            / "users"
            / "localinventoryuser"
        )

        self.assertIn(
            expected_root,
            physical.parents,
        )
