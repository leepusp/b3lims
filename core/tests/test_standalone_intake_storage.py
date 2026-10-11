"""Standalone intake-to-canonical-storage regression."""

from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import (
    SimpleUploadedFile,
)
from django.test import TestCase
from django.urls import reverse

from core.models.samples.intake import (
    SampleImportBatch,
    SampleIntakeRecord,
)
from core.models.samples.sample import (
    Sample,
    SampleStorageLevel,
)
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
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
    "Standalone intake storage tests require standalone settings.",
)
class StandaloneIntakeStorageTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects
            .create_user(
                username="intake-storage-user",
                password="test-password",
            )
        )

        self.client.force_login(
            self.user
        )

    def test_csv_intake_creates_canonical_storage_on_registration(
        self,
    ):
        upload = SimpleUploadedFile(
            "intake-storage.csv",
            (
                b"sample_id,sample_type,"
                b"organism_name,storage_location\n"
                b"INTAKE-STORAGE-001,Other,"
                b"Standalone intake,"
                b"Room 1 > Freezer A > "
                b"Rack 01 > Box 001 > A01\n"
            ),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse(
                "samples_import"
            ),
            {
                "sample_table": upload,
            },
            HTTP_HOST="localhost",
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        batch = (
            SampleImportBatch.objects
            .get(
                uploaded_by=self.user
            )
        )

        self.assertEqual(
            batch.status,
            "validated",
        )

        self.assertEqual(
            batch.valid_rows,
            1,
        )

        record = (
            SampleIntakeRecord.objects
            .get(
                batch=batch
            )
        )

        self.assertEqual(
            record.status,
            "ready_to_fill",
        )

        response = self.client.post(
            reverse(
                "sample_add"
            ),
            {
                "action": "add_sample",
                "sample_id": (
                    "INTAKE-STORAGE-001"
                ),
                "sample_type": "Other",
                "custom_organism_name": (
                    "Standalone intake"
                ),
                "owner": str(
                    self.user.pk
                ),
                "aliquot_count": "1",
                "intake_record_id": str(
                    record.pk
                ),
                "storage_location": (
                    "Room 1 > Freezer A > "
                    "Rack 01 > Box 001 > A01"
                ),
            },
            HTTP_HOST="localhost",
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        sample = Sample.objects.get(
            sample_id=(
                "INTAKE-STORAGE-001"
            )
        )

        record.refresh_from_db()

        self.assertEqual(
            record.sample_id,
            sample.pk,
        )

        self.assertEqual(
            record.status,
            "used_for_sample",
        )

        assignment = (
            SampleStorageAssignment.objects
            .select_related(
                "location"
            )
            .get(
                sample=sample
            )
        )

        self.assertEqual(
            assignment.location.full_path,
            (
                "Room 1 > Freezer A > "
                "Rack 01 > Box 001 > A01"
            ),
        )

        self.assertTrue(
            assignment.is_primary
        )

        self.assertEqual(
            StorageLocation.objects.count(),
            5,
        )

        self.assertEqual(
            list(
                sample.storage_levels
                .order_by(
                    "level_index"
                )
                .values_list(
                    "name",
                    flat=True,
                )
            ),
            [
                "Room 1",
                "Freezer A",
                "Rack 01",
                "Box 001",
                "A01",
            ],
        )

        sample.refresh_from_db()

        self.assertEqual(
            sample.storage_location,
            (
                "Room 1 > Freezer A > "
                "Rack 01 > Box 001 > A01"
            ),
        )

        self.assertEqual(
            SampleStorageLevel.objects
            .filter(
                sample=sample
            )
            .count(),
            5,
        )
