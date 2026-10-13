from django.test import SimpleTestCase

from core.services.storage_legacy_projection import (
    build_legacy_storage_projection,
)


class StorageLegacyProjectionTests(SimpleTestCase):
    def test_recovers_two_known_historical_freezers(self):
        projection = build_legacy_storage_projection([
            ("SAMPLE-1", "Freezer Chuck > Caixa 1.2 > B5"),
            ("SAMPLE-2", "Freezer Regina > Caixa 1.1 > B5"),
        ])

        self.assertEqual(len(projection["samples"]), 2)
        self.assertEqual(len(projection["nodes"]), 4)
        self.assertEqual(projection["unparsed"], 0)

        kinds = [node["kind"] for node in projection["nodes"]]
        self.assertEqual(kinds.count("freezer"), 2)
        self.assertEqual(kinds.count("box"), 2)

        self.assertTrue(
            all(node["legacy"] for node in projection["nodes"])
        )

    def test_same_box_is_not_duplicated(self):
        projection = build_legacy_storage_projection([
            ("S1", "Freezer Chuck > Caixa 1.2 > B5"),
            ("S2", "Freezer Chuck > Caixa 1.2 > B6"),
        ])

        self.assertEqual(len(projection["nodes"]), 2)
        self.assertEqual(len(projection["samples"]), 2)

    def test_unrecognized_paths_are_never_invented(self):
        projection = build_legacy_storage_projection([
            ("S1", "Unknown location"),
            ("S2", "Freezer Chuck > Caixa 1.2 > B5"),
        ])

        self.assertEqual(projection["unparsed"], 1)
        self.assertEqual(len(projection["samples"]), 1)

    def test_virtual_nodes_have_no_database_identity(self):
        projection = build_legacy_storage_projection([
            ("S1", "Freezer Chuck > Caixa 1.2 > B5"),
        ])

        self.assertTrue(
            all(
                node["id"].startswith("legacy:")
                for node in projection["nodes"]
            )
        )


class StorageHistoricalFrontendContractTests(SimpleTestCase):
    def test_virtual_selection_does_not_use_location_request(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        viewer = (
            root / "static/internal/storage/storage_viewer_3d.js"
        ).read_text(encoding="utf-8")
        designer = (
            root / "static/internal/storage/storage_designer_v4.js"
        ).read_text(encoding="utf-8")

        self.assertIn('if (node?.legacy)', viewer)
        self.assertIn('"b3-storage-legacy-selected"', viewer)
        self.assertIn('"b3-storage-legacy-selected"', designer)
        self.assertIn('selectedId = null;', designer)


class StorageLegacyIdentityV5Tests(SimpleTestCase):
    def test_historical_sample_keeps_database_identity(self):
        projection = build_legacy_storage_projection([
            (42, "SAMPLE-42", "Freezer Regina > Caixa 1.1 > B5"),
        ])

        sample = projection["samples"][0]

        self.assertEqual(sample["id"], "42")
        self.assertEqual(sample["code"], "SAMPLE-42")
        self.assertEqual(sample["position"], "B5")
        self.assertTrue(sample["legacy"])

    def test_equal_codes_do_not_replace_distinct_samples(self):
        projection = build_legacy_storage_projection([
            (42, "SAME-CODE", "Freezer Regina > Caixa 1.1 > B5"),
            (43, "SAME-CODE", "Freezer Regina > Caixa 1.1 > B6"),
        ])

        samples = projection["samples"]

        self.assertEqual(len(samples), 2)
        self.assertEqual(
            {sample["id"] for sample in samples},
            {"42", "43"},
        )

    def test_legacy_contract_supports_previous_records(self):
        projection = build_legacy_storage_projection([
            ("SAMPLE-OLD", "Freezer Chuck > Caixa 1.2 > B5"),
        ])

        self.assertIsNone(projection["samples"][0]["id"])
