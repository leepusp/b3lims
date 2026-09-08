"""Regression tests for a fresh standalone/local-first installation."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.test import SimpleTestCase


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
    "Standalone first-run tests require standalone settings.",
)
class StandaloneFirstRunTests(SimpleTestCase):
    def test_fresh_root_is_bootstrapped_before_sqlite_connect(
        self,
    ):
        project_root = (
            Path(__file__)
            .resolve()
            .parents[2]
        )

        with tempfile.TemporaryDirectory() as temporary:
            local_root = (
                Path(temporary)
                / "new"
                / "biobank-local"
            )

            self.assertFalse(
                local_root.exists()
            )

            environment = os.environ.copy()

            environment[
                "BIOBANK_LOCAL_ROOT"
            ] = str(local_root)

            environment[
                "DJANGO_SETTINGS_MODULE"
            ] = "biobank.standalone_settings"

            code = r'''
from pathlib import Path

import django

django.setup()

from django.conf import settings
from django.db import connection


expected_directories = (
    Path(settings.BIOBANK_LOCAL_ROOT),
    Path(settings.BIOBANK_LOCAL_DATABASE_ROOT),
    Path(settings.BIOBANK_STORAGE_ROOT),
    Path(settings.MEDIA_ROOT),
    Path(settings.BIOBANK_BACKUP_ROOT),
    Path(settings.BIOBANK_GROUP_ROOT),
    Path(settings.BIOBANK_INVENTORY_ROOT),
    Path(settings.BIOBANK_SAMPLE_DOCS_ROOT),
    Path(settings.BIOBANK_MANIFESTS_ROOT),
    Path(settings.BIOBANK_SHARED_ROOT),
)

for directory in expected_directories:
    assert directory.is_dir(), directory

with connection.cursor() as cursor:
    cursor.execute("SELECT 1")
    assert cursor.fetchone()[0] == 1

database_path = Path(
    settings.DATABASES["default"]["NAME"]
)

assert database_path.is_file(), database_path

print("FIRST_RUN_DIRECTORIES=PASS")
print("FIRST_RUN_SQLITE_CONNECT=PASS")
print(f"DATABASE={database_path}")
'''

            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    code,
                ],
                cwd=project_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if completed.returncode != 0:
                self.fail(
                    "\n"
                    f"STDOUT:\n{completed.stdout}\n"
                    f"STDERR:\n{completed.stderr}"
                )

            self.assertIn(
                "FIRST_RUN_DIRECTORIES=PASS",
                completed.stdout,
            )

            self.assertIn(
                "FIRST_RUN_SQLITE_CONNECT=PASS",
                completed.stdout,
            )
