from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[1]


class StorageContextualV7Tests(SimpleTestCase):
    def test_sample_options_expose_identity_and_path(self):
        html = (
            ROOT / "interfaces/internal/storage/_sample_preview.html"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'data-b3-sample-pk="{{ assignment.sample.pk }}"',
            html,
        )
        self.assertIn(
            'data-b3-location-path="{{ assignment.location.full_path }}"',
            html,
        )

    def test_controller_is_loaded(self):
        html = (
            ROOT / "interfaces/internal/storage/index.html"
        ).read_text(encoding="utf-8")

        self.assertIn("storage_operations_v6.js", html)
        self.assertIn("storage_contextual_v7.js", html)

    def test_actions_use_existing_transfer_previews(self):
        js = (
            ROOT / "static/internal/storage/storage_contextual_v7.js"
        ).read_text(encoding="utf-8")

        self.assertIn('"preview-container"', js)
        self.assertIn('"preview-sample-assignment"', js)
        self.assertIn('"b3-spatial-v5-box"', js)
        self.assertIn('transfersTab.click()', js)
        self.assertIn('sample.legacy', js)
        self.assertIn('assignments.length !== 1', js)

        self.assertNotIn(".submit(", js)
        self.assertNotIn(".requestSubmit(", js)
        self.assertNotIn('fetch(', js)
