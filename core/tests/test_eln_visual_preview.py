"""Tests for synthetic-only visual preview data."""

from django.test import SimpleTestCase

from core.views.internal.lab_tools.eln_demo_data import (
    DEMO_EXPERIMENTS,
    build_demo_preview,
)


class ElnVisualPreviewTests(SimpleTestCase):

    def test_all_examples_are_synthetic(self):
        data = build_demo_preview({})

        self.assertEqual(
            len(data["entries"]),
            len(DEMO_EXPERIMENTS),
        )

        self.assertTrue(
            all(
                item["id"].startswith("DEMO-")
                for item in data["entries"]
            )
        )

    def test_category_filter(self):
        data = build_demo_preview({
            "category": "Molecular",
        })

        self.assertTrue(data["entries"])
        self.assertTrue(
            all(
                item["category"] == "Molecular"
                for item in data["entries"]
            )
        )

    def test_search_filter(self):
        data = build_demo_preview({
            "q": "protein",
        })

        self.assertEqual(len(data["entries"]), 1)
        self.assertIn(
            "Protein",
            data["entries"][0]["title"],
        )

    def test_pinned_filter(self):
        data = build_demo_preview({
            "scope": "pinned",
        })

        self.assertTrue(
            all(item["pinned"] for item in data["entries"])
        )

    def test_invalid_filters_are_normalized(self):
        data = build_demo_preview({
            "category": "invalid",
            "status": "invalid",
            "scope": "invalid",
        })

        self.assertEqual(data["scope"], "all")
        self.assertEqual(data["selected_category"], "")
        self.assertEqual(data["selected_status"], "")
