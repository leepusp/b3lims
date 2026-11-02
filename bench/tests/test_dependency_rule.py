import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


IMPORT_BENCH = re.compile(r"^\s*(from\s+bench(\.|\s)|import\s+bench(\.|\s|$))", re.MULTILINE)


class DependencyRuleTests(SimpleTestCase):
    """B3 Bench may import core; core must never import bench."""

    def test_core_never_imports_bench(self):
        core_root = Path(settings.BASE_DIR) / "core"
        offenders = []
        for path in core_root.rglob("*.py"):
            if "migrations" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if IMPORT_BENCH.search(text):
                offenders.append(str(path.relative_to(settings.BASE_DIR)))

        self.assertEqual(offenders, [], f"core imports bench in: {offenders}")

    def test_bench_is_installed_after_core(self):
        apps = list(settings.INSTALLED_APPS)
        self.assertIn("bench.apps.BenchConfig", apps)
        self.assertLess(apps.index("core.apps.CoreConfig"), apps.index("bench.apps.BenchConfig"))
