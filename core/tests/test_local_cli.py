"""The `biobank-local` installer, run as a real process in a temporary folder."""

import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from unittest import TestCase

BASE = Path(__file__).resolve().parents[2]


def cli(root, *args, input_text=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BIOBANK_", "DJANGO_"))}

    return subprocess.run(
        [sys.executable, "-m", "biobank.local_cli", "--root", str(root), *args],
        cwd=BASE, env=env, input=input_text, capture_output=True, text=True, timeout=240,
    )


class LocalInstallTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # One real installation is shared (creating the database is the slow part).
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "lab"
        cls.first = cls.install("--time-zone", "America/Sao_Paulo")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        super().tearDownClass()

    @classmethod
    def install(cls, *extra):
        return cli(cls.root, "setup", "--non-interactive", "--skip-static", "--admin-user", "ana",
                   "--admin-password", "correct-horse-1", *extra)

    def setup_install(self, *extra):
        return self.install(*extra)

    def test_non_interactive_setup_creates_a_working_install(self):
        done = self.first

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("biobank-local run", done.stdout)
        config = (self.root / "config.env").read_text()
        self.assertIn("BIOBANK_SECRET_KEY=", config)
        self.assertIn("BIOBANK_TIME_ZONE=America/Sao_Paulo", config)
        self.assertTrue((self.root / "database" / "biobank.sqlite3").is_file())

        if os.name == "posix":
            self.assertEqual((self.root / "config.env").stat().st_mode & 0o777, 0o600)

        doctor = cli(self.root, "doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertIn("[ok] database (sqlite)", doctor.stdout)

    def test_secret_key_is_kept_when_setup_is_repeated(self):
        first = (self.root / "config.env").read_text().split("BIOBANK_SECRET_KEY=")[1].splitlines()[0]
        self.assertEqual(self.setup_install().returncode, 0)
        second = (self.root / "config.env").read_text().split("BIOBANK_SECRET_KEY=")[1].splitlines()[0]

        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 40)

    def test_short_password_is_refused(self):
        other = Path(self.tmp.name) / "short"
        done = cli(other, "setup", "--non-interactive", "--skip-static", "--admin-user", "ana",
                   "--admin-password", "short")

        self.assertEqual(done.returncode, 2)
        self.assertFalse((other / "config.env").exists())

    def test_the_wizard_asks_the_questions_in_order(self):
        wizard_root = Path(self.tmp.name) / "wizard"
        answers = "\n".join([
            str(wizard_root),   # data folder
            "1",              # SQLite
            "ana",            # username
            "",               # e-mail
            "n",              # single computer
            "UTC",            # time zone
        ]) + "\n"
        done = subprocess.run(
            [sys.executable, "-c",
             "import getpass,sys;getpass.getpass=lambda p='': 'correct-horse-1';"
             "from biobank import local_cli;sys.exit(local_cli.main(['--root',%r,'setup','--skip-static']))" % str(wizard_root)],
            cwd=BASE, input=answers, capture_output=True, text=True, timeout=240,
            env={k: v for k, v in os.environ.items() if not k.startswith(("BIOBANK_", "DJANGO_"))},
        )

        self.assertEqual(done.returncode, 0, done.stderr)

        for step in ("Step 1 of 4", "Step 2 of 4", "Step 3 of 4", "Step 4 of 4"):
            self.assertIn(step, done.stdout)

        self.assertTrue((wizard_root / "config.env").is_file())

    def test_run_without_setup_explains_what_to_do(self):
        done = cli(Path(self.tmp.name) / "none", "run")

        self.assertEqual(done.returncode, 2)
        self.assertIn("biobank-local setup", done.stderr)

    def test_backup_archives_database_and_config(self):
        done = cli(self.root, "backup")

        self.assertEqual(done.returncode, 0, done.stderr)
        archives = list((self.root / "backups").glob("biobank_*.tar.gz"))
        self.assertEqual(len(archives), 1)

        with tarfile.open(archives[0]) as tar:
            names = tar.getnames()

        self.assertIn("config.env", names)
        self.assertTrue(any(n.startswith("database") for n in names))

    def test_createuser_adds_another_administrator(self):
        done = cli(self.root, "createuser", "bruno", "--password", "another-pass-9")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Created administrator 'bruno'", done.stdout)

    def test_migrate_updates_an_existing_install_without_touching_accounts(self):
        done = cli(self.root, "migrate", "--skip-static")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("up to date", done.stdout)
        self.assertEqual(cli(Path(self.tmp.name) / "none", "migrate").returncode, 2)
