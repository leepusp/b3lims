import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

B3_MAP = (
    ROOT
    / "core"
    / "static"
    / "common"
    / "b3_map.js"
)

MAP_CALL_SITES = [
    ROOT
    / "core"
    / "static"
    / "public"
    / "biobanks.js",

    ROOT
    / "core"
    / "static"
    / "internal"
    / "samples"
    / "sample_origin_map.js",

    ROOT
    / "core"
    / "static"
    / "internal"
    / "biobanks"
    / "biobank.js",

    ROOT
    / "core"
    / "static"
    / "internal"
    / "shipments"
    / "route_map.js",

    ROOT
    / "core"
    / "interfaces"
    / "internal"
    / "biobanks"
    / "biobank_dashboard.html",
]


class MapLocalDefaultContractTests(
    unittest.TestCase
):
    def test_remote_tiles_are_opt_in(self):
        source = B3_MAP.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "config.remote !== true",
            source,
        )

        self.assertNotIn(
            "config.remote === false",
            source,
        )

    def test_current_map_call_sites_do_not_enable_remote_tiles(
        self,
    ):
        pattern = re.compile(
            r"\bremote\s*:\s*true\b"
        )

        offenders = []

        for path in MAP_CALL_SITES:
            self.assertTrue(
                path.is_file(),
                str(path),
            )

            source = path.read_text(
                encoding="utf-8"
            )

            if pattern.search(source):
                offenders.append(
                    str(
                        path.relative_to(ROOT)
                    )
                )

        self.assertEqual(
            offenders,
            [],
        )

    def test_remote_support_remains_explicitly_available(
        self,
    ):
        source = B3_MAP.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "global.L.tileLayer(",
            source,
        )

        self.assertIn(
            "https://tile.openstreetmap.org/"
            "{z}/{x}/{y}.png",
            source,
        )

        self.assertIn(
            'config.remote !== true',
            source,
        )


if __name__ == "__main__":
    unittest.main()
