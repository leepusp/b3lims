from django.template.loader import render_to_string
from django.test import SimpleTestCase


TEMPLATE = "internal/storage/_movement_comparison_v89.html"


def render_preview(kind, preview):
    return render_to_string(
        TEMPLATE,
        {"movement_kind": kind, "movement_preview": preview},
    )


class StorageMovementOverlayV810Tests(SimpleTestCase):

    def test_container_identifiers(self):
        html = render_preview("container", {
            "container_id": 12,
            "destination_id": 14,
            "old_path": "Room > Freezer > Box A",
            "new_path": "Room > Freezer > Box B > Box A",
            "affected_location_count": 2,
            "active_assignment_count": 3,
            "active_sample_count": 2,
        })

        self.assertIn('data-b3-v810-container-id="12"', html)
        self.assertIn('data-b3-v810-destination-id="14"', html)
        self.assertIn('data-b3-v89-path-before', html)
        self.assertIn('data-b3-v89-path-after', html)
        self.assertIn("Preview only", html)

    def test_sample_does_not_invent_container_identifiers(self):
        html = render_preview("sample", {
            "affected_sample_count": 1,
            "affected_assignment_count": 1,
            "moves": [{
                "sample_identifier": "SAMPLE-001",
                "origin_path": "Room > Box A",
                "destination_path": "Room > Box B",
                "position_before": "A01",
                "position_after": "B05",
            }],
        })

        self.assertIn('data-b3-v89-movement-row', html)
        self.assertNotIn('data-b3-v810-container-id=', html)
        self.assertNotIn('data-b3-v810-destination-id=', html)

    def test_identifiers_are_html_escaped(self):
        html = render_preview("container", {
            "container_id": '12" onmouseover="alert(1)',
            "destination_id": '14"><script>alert(1)</script>',
            "old_path": "Room A",
            "new_path": "Room B",
        })

        self.assertNotIn('onmouseover="alert(1)', html)
        self.assertNotIn("<script>", html)
        self.assertIn("&quot;", html)
        self.assertIn("&lt;script&gt;", html)

    def test_comparison_remains_read_only(self):
        html = render_preview("container", {
            "container_id": 12,
            "destination_id": 14,
            "old_path": "Room A",
            "new_path": "Room B",
        })

        self.assertNotIn("<form", html)
        self.assertNotIn('type="submit"', html)
        self.assertNotIn('name="action"', html)
