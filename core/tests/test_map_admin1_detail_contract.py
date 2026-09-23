import json
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

B3_CSS = (
    ROOT
    / "core"
    / "static"
    / "common"
    / "b3_map.css"
)

ADMIN1 = (
    ROOT
    / "core"
    / "static"
    / "maps"
    / "brazil_admin1.js"
)

ASSETS_JS = (
    ROOT
    / "core"
    / "interfaces"
    / "common"
    / "map_assets_js.html"
)

ASSETS_CSS = (
    ROOT
    / "core"
    / "interfaces"
    / "common"
    / "map_assets_css.html"
)


class MapAdmin1DetailContractTests(
    unittest.TestCase
):
    def test_brazil_admin1_has_27_features(self):
        source = ADMIN1.read_text(
            encoding="utf-8"
        )

        prefix = "window.B3_BRAZIL_ADMIN1="

        self.assertTrue(
            source.startswith(prefix)
        )

        self.assertTrue(
            source.rstrip().endswith(";")
        )

        payload = source[
            len(prefix):
        ].strip()[:-1]

        data = json.loads(payload)

        self.assertEqual(
            data["type"],
            "FeatureCollection",
        )

        self.assertEqual(
            len(data["features"]),
            27,
        )

        names = {
            feature["properties"]["name"]
            for feature in data["features"]
        }

        self.assertIn(
            "São Paulo",
            names,
        )

        self.assertIn(
            "Minas Gerais",
            names,
        )

        self.assertIn(
            "Distrito Federal",
            names,
        )

    def test_b3map_adds_admin1_detail(self):
        source = B3_MAP.read_text(
            encoding="utf-8"
        )

        for needle in [
            "B3_BRAZIL_ADMIN1",
            "addRegionalDetail",
            "REGION_LABEL_MIN_ZOOM = 4",
            "b3-map-show-region-labels",
            "b3-map-region-label",
        ]:
            self.assertIn(
                needle,
                source,
            )

    def test_remote_tiles_stay_opt_in(self):
        source = B3_MAP.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "config.remote !== true",
            source,
        )

    def test_admin1_asset_loads_before_b3map(self):
        source = ASSETS_JS.read_text(
            encoding="utf-8"
        )

        admin1_pos = source.index(
            "maps/brazil_admin1.js"
        )

        b3map_pos = source.index(
            "common/b3_map.js"
        )

        self.assertLess(
            admin1_pos,
            b3map_pos,
        )

        self.assertIn(
            "20260923-map-detail1",
            source,
        )

    def test_css_contains_region_label_contract(self):
        source = B3_CSS.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            ".b3-map-region-label",
            source,
        )

        self.assertIn(
            ".b3-map-show-region-labels "
            ".b3-map-region-label",
            source,
        )

        css_assets = ASSETS_CSS.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "20260923-map-detail1",
            css_assets,
        )


if __name__ == "__main__":
    unittest.main()
