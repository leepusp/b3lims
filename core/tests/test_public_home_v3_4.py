import re
from pathlib import Path

from django.test import SimpleTestCase


class PublicHomeV34InteractionTests(
    SimpleTestCase
):
    @staticmethod
    def source():
        return Path(
            "core/interfaces/public/index.html"
        ).read_text()

    def test_whole_canvas_parallax_is_removed(
        self,
    ):
        source = self.source()

        for forbidden in (
            "canvas.style.transform",
            "scale(1.035)",
            "translate3d(",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )

    def test_each_organism_has_independent_interaction_state(
        self,
    ):
        source = self.source()

        for token in (
            "interactionVelocityX",
            "interactionVelocityY",
            "interactionScale",
            "applyPointerInteraction",
        ):
            self.assertIn(
                token,
                source,
            )

    def test_pointer_force_is_calculated_from_each_organism_position(
        self,
    ):
        source = self.source()

        self.assertRegex(
            source,
            (
                r"organism\.x"
                r"\s*-\s*"
                r"pointer\.x"
            ),
        )

        self.assertRegex(
            source,
            (
                r"organism\.y"
                r"\s*-\s*"
                r"pointer\.y"
            ),
        )

        for token in (
            "Math.hypot(",
            "POINTER_BASE_RADIUS = 72",
            "POINTER_FORCE = 240",
            "POINTER_DAMPING = 5.5",
        ):
            self.assertIn(
                token,
                source,
            )

    def test_nearby_organism_is_locally_scaled(
        self,
    ):
        source = self.source()

        self.assertIn(
            "POINTER_SCALE_BOOST = 0.20",
            source,
        )

        self.assertIn(
            "context.scale(",
            source,
        )

        self.assertRegex(
            source,
            (
                r"context\.scale\("
                r"\s*"
                r"organism\.interactionScale"
            ),
        )

    def test_default_microorganism_speed_is_increased_moderately(
        self,
    ):
        source = self.source()

        self.assertRegex(
            source,
            (
                r"speed:\s*"
                r"randomBetween\(\s*"
                r"5\.5,\s*"
                r"13\.5\s*"
                r"\)"
            ),
        )

    def test_phage_speed_is_increased_moderately(
        self,
    ):
        source = self.source()

        self.assertRegex(
            source,
            (
                r"organism\.speed\s*=\s*"
                r"\(\s*"
                r"randomBetween\(\s*"
                r"4,\s*"
                r"8\.5\s*"
                r"\)\s*"
                r"\)"
            ),
        )

    def test_pointer_interaction_respects_reduced_motion(
        self,
    ):
        source = self.source()

        self.assertIn(
            (
                "(prefers-reduced-motion: "
                "reduce)"
            ),
            source,
        )

        self.assertIn(
            "!reducedMotion",
            source,
        )

    def test_pointer_listeners_remain_on_hero_surface(
        self,
    ):
        source = self.source()

        for token in (
            'hero.addEventListener(',
            '"pointermove"',
            '"pointerleave"',
            '"pointercancel"',
            "updatePointerPosition",
            "clearPointer",
        ):
            self.assertIn(
                token,
                source,
            )

    def test_existing_scientific_explorers_are_preserved(
        self,
    ):
        source = self.source()

        for token in (
            "publicViewOverviewTab",
            "publicViewGeographyTab",
            "publicViewNetworkTab",
            "publicViewRankingTab",
            "publicViewBubbleTab",
            'type: "pie"',
            'type: "treemap"',
            'type: "graph"',
            'type: "bar"',
            'type: "scatter"',
        ):
            self.assertIn(
                token,
                source,
            )

    def test_animation_still_has_no_public_data_fetch(
        self,
    ):
        source = self.source()

        for forbidden in (
            "fetch(",
            "XMLHttpRequest",
            "$.ajax",
            "/public/api/",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )
