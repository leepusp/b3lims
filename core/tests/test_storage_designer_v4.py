from pathlib import Path
from django.test import SimpleTestCase

CORE = Path(__file__).resolve().parents[1]


class StorageDesignerV4ContractTests(SimpleTestCase):
    def test_single_workspace_hosts_scene_and_detailed_explorer(self):
        index = (CORE / 'interfaces/internal/storage/index.html').read_text()
        viewer = (CORE / 'interfaces/internal/storage/_viewer_3d.html').read_text()
        self.assertEqual(index.count('{% include "internal/storage/_viewer_3d.html" %}'), 1)
        self.assertEqual(index.count('{% include "internal/storage/_explorer_v2.html" %}'), 0)
        self.assertEqual(viewer.count('{% include "internal/storage/_explorer_v2.html" %}'), 1)
        for token in ('id="storage-isometric-v813"', 'id="storage-designer-build-panel"',
                      'id="storage-designer-builder-target"', 'id="storage-designer-add-child"'):
            self.assertIn(token, viewer)

    def test_builder_reuses_existing_permission_guarded_django_form(self):
        script = (CORE / 'static/internal/storage/storage_designer_v4.js').read_text()
        self.assertIn('[name="action"]', script)
        self.assertIn('create_location', script)
        self.assertIn('createAction?.form', script)
        self.assertIn('b3-storage-location-selected', script)
        self.assertIn('b3-storage-select-request', script)
        self.assertNotIn('fetch(', script)
        self.assertNotIn('form.submit(', script)
        self.assertNotIn('form.requestSubmit(', script)
        index = (CORE / 'interfaces/internal/storage/index.html').read_text()
        self.assertIn('storage_designer_v4.js', index)
