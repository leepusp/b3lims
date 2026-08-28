from django.test import SimpleTestCase

from core.models.samples.relationship import (
    SampleRelationship,
)


class SampleRelationshipLabelTests(
    SimpleTestCase
):
    def test_relationship_codes_remain_stable(self):
        self.assertEqual(
            [
                value
                for (
                    value,
                    _label,
                )
                in (
                    SampleRelationship
                    .RELATIONSHIP_TYPES
                )
            ],
            [
                "aliquot",
                "passage",
                "mutated_from",
                "assembled_from",
                "extracted_from",
                "infects",
                "other",
            ],
        )

    def test_relationship_labels_are_english(self):
        self.assertEqual(
            dict(
                SampleRelationship
                .RELATIONSHIP_TYPES
            ),
            {
                "aliquot": (
                    "Aliquot "
                    "(exact copy in another tube)"
                ),
                "passage": (
                    "Passage / Subculture"
                ),
                "mutated_from": (
                    "Mutation / Modification of"
                ),
                "assembled_from": (
                    "Assembled from "
                    "(Vector + Insert)"
                ),
                "extracted_from": (
                    "Extracted from (DNA/RNA)"
                ),
                "infects": (
                    "Infects (Host Range)"
                ),
                "other": (
                    "Other Relationship"
                ),
            },
        )

    def test_relationship_help_text_is_english(self):
        self.assertEqual(
            (
                SampleRelationship
                ._meta
                .get_field(
                    "notes"
                )
                .help_text
            ),
            (
                "Protocol or derivation "
                "method details."
            ),
        )
