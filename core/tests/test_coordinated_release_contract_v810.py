from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "deploy"
    / "operations"
    / "deploy_coordinated_release.sh"
)


class CoordinatedReleaseContractV810Tests(unittest.TestCase):

    def test_source_exists_and_is_executable(self):
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(SCRIPT.stat().st_mode & 0o100)

    def test_shell_syntax(self):
        subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            check=True,
        )

    def test_activation_is_not_available(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--activate", "0" * 40],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_only_preflight_and_stage_are_supported(self):
        source = SCRIPT.read_text()
        self.assertIn("--preflight|--stage", source)
        self.assertIn("production_modified=NO", source)

    def test_production_cutover_operations_are_absent(self):
        source = SCRIPT.read_text()
        for command in (
            "systemctl restart",
            "systemctl stop",
            "mv -Tf",
            "ln -s ",
            "manage.py migrate",
        ):
            with self.subTest(command=command):
                self.assertNotIn(command, source)

    def test_database_is_isolated(self):
        source = SCRIPT.read_text()
        self.assertIn("env -u DATABASE_URL", source)
        self.assertIn("django.db.backends.sqlite3", source)
        self.assertIn('BIOBANK_MEDIA_ROOT="$BUILD/private-media"', source)

    def test_source_and_static_parity(self):
        source = SCRIPT.read_text()
        self.assertIn("collectstatic", source)
        self.assertIn('cmp -s "$SRC" "$DST"', source)
        self.assertIn("static-sha256.txt", source)
