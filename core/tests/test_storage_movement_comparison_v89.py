from django.template.loader import render_to_string
from django.test import SimpleTestCase


TEMPLATE = (
    "internal/storage/_movement_comparison_v89.html"
)


def render_comparison(kind, preview):
    return render_to_string(
        TEMPLATE,
        {
            "movement_kind": kind,
            "movement_preview": preview,
        },
    )


class StorageMovementComparisonV89Tests(SimpleTestCase):

    def test_container_before_after_and_impact(self):
        html = render_comparison(
            "container",
            {
                "old_path": (
                    "Room 1 > Freezer A > Box 001"
                ),
                "new_path": (
                    "Room 2 > Freezer B > Box 001"
                ),
                "affected_location_count": 4,
                "active_assignment_count": 12,
                "active_sample_count": 10,
            },
        )

        self.assertIn("Before", html)
        self.assertIn("After", html)
        self.assertIn(
            "Room 1 &gt; Freezer A &gt; Box 001",
            html,
        )
        self.assertIn(
            "Room 2 &gt; Freezer B &gt; Box 001",
            html,
        )
        self.assertIn("locations in affected subtree", html)
        self.assertIn("distinct Samples", html)
        self.assertIn("Preview only", html)

    def test_sample_position_before_after(self):
        html = render_comparison(
            "sample",
            {
                "affected_sample_count": 1,
                "affected_assignment_count": 1,
                "moves": [
                    {
                        "sample_identifier": "SAMPLE-001",
                        "origin_path": "Room 1 > Box A",
                        "destination_path": "Room 2 > Box B",
                        "position_before": "A01",
                        "position_after": "B05",
                    },
                ],
            },
        )

        self.assertIn("SAMPLE-001", html)
        self.assertIn("A01", html)
        self.assertIn("B05", html)
        self.assertIn("Room 2 &gt; Box B", html)
        self.assertIn("Preview only", html)

    def test_bulk_comparison_renders_each_sample(self):
        html = render_comparison(
            "bulk",
            {
                "affected_sample_count": 2,
                "affected_assignment_count": 2,
                "moves": [
                    {
                        "sample_identifier": "SAMPLE-A",
                        "origin_path": "Room > Box A",
                        "destination_path": "Room > Box B",
                        "position_before": "A01",
                        "position_after": "B01",
                    },
                    {
                        "sample_identifier": "SAMPLE-B",
                        "origin_path": "Room > Box B",
                        "destination_path": "Room > Box A",
                        "position_before": "B01",
                        "position_after": "A01",
                    },
                ],
            },
        )

        self.assertIn("SAMPLE-A", html)
        self.assertIn("SAMPLE-B", html)
        self.assertEqual(
            html.count('data-b3-v89-movement-row'),
            2,
        )

    def test_comparison_is_escaped_and_read_only(self):
        html = render_comparison(
            "sample",
            {
                "affected_sample_count": 1,
                "affected_assignment_count": 1,
                "moves": [
                    {
                        "sample_identifier": (
                            '<img src=x onerror=alert(1)>'
                        ),
                        "origin_path": "Room A",
                        "destination_path": "Room B",
                        "position_before": "",
                        "position_after": "",
                    },
                ],
            },
        )

        self.assertIn("&lt;img", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("<form", html)
        self.assertNotIn('type="submit"', html)
        self.assertNotIn('name="action"', html)
