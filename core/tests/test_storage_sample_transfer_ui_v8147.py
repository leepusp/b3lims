from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]

INDEX = (
    ROOT
    / "core/interfaces/internal/storage/index_v814.html"
)

SINGLE = (
    ROOT
    / "core/interfaces/internal/storage/_sample_preview.html"
)

BULK = (
    ROOT
    / "core/interfaces/internal/storage/_sample_bulk_preview.html"
)


class StorageSampleTransferUIContractTests(SimpleTestCase):

    def test_canonical_page_includes_both_components(self):
        html = INDEX.read_text()

        self.assertIn(
            '{% include "internal/storage/_sample_preview.html" %}',
            html,
        )

        self.assertIn(
            '{% include "internal/storage/_sample_bulk_preview.html" %}',
            html,
        )

    def test_single_transfer_confirmation_is_preserved(self):
        html = SINGLE.read_text()

        self.assertIn(
            'id="storage-sample-preview"',
            html,
        )

        self.assertIn(
            'value="confirm_sample_move"',
            html,
        )

    def test_bulk_preview_component_is_preserved(self):
        html = BULK.read_text()

        self.assertIn(
            'id="storage-sample-bulk-preview"',
            html,
        )

        self.assertIn(
            "Bulk preview only",
            html,
        )
