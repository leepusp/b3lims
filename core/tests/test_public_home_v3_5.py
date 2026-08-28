from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import (
    Bacteria,
    Sample,
    SampleTaxonomyAssignment,
)
from core.services.public_catalog import (
    public_home_context,
    public_taxonomy_records,
)


class PublicHomeV35Tests(
    TestCase
):
    @classmethod
    def setUpTestData(
        cls,
    ):
        cls.owner = User.objects.create_user(
            username="V35-OWNER",
        )


        cls.pa14 = Bacteria.objects.create(
            sample_id="V35-PA14",
            sample_type="Bacterium (Host)",
            organism_name="P. aeruginosa PA14",
            owner=cls.owner,
            is_public=True,
            is_embargoed=False,
            is_active=True,
            genus="Pseudomonas",
            species="aeruginosa",
            strain="PA14",
        )


        cls.pama = Bacteria.objects.create(
            sample_id="V35-PAMA",
            sample_type="Bacterium (Host)",
            organism_name="P. aeruginosa PAMA I",
            owner=cls.owner,
            is_public=True,
            is_embargoed=False,
            is_active=True,
            genus="Pseudomonas",
            species="Pseudomonas aeruginosa",
            strain="PAMA I",
        )


        cls.private = Sample.objects.create(
            sample_id="V35-PRIVATE",
            sample_type="PRIVATE-TYPE",
            organism_name="PRIVATE-CANDIDATE-SENTINEL",
            owner=cls.owner,
            is_public=False,
            is_embargoed=False,
            is_active=True,
        )


        cls.embargoed = Sample.objects.create(
            sample_id="V35-EMBARGO",
            sample_type="EMBARGO-TYPE",
            organism_name="EMBARGO-CANDIDATE-SENTINEL",
            owner=cls.owner,
            is_public=True,
            is_embargoed=True,
            is_active=True,
        )


        SampleTaxonomyAssignment.objects.create(
            sample=cls.pa14,
            source="ncbi",
            taxon_id="287",
            scientific_name=(
                "Pseudomonas aeruginosa"
            ),
            rank="species",
            domain_or_realm="Bacteria",
            phylum="Pseudomonadota",
            class_name="Gammaproteobacteria",
            order_name="Pseudomonadales",
            family="Pseudomonadaceae",
            genus="Pseudomonas",
            species="Pseudomonas aeruginosa",
            match_status=(
                SampleTaxonomyAssignment.STATUS_VERIFIED
            ),
            is_current=True,
        )


        SampleTaxonomyAssignment.objects.create(
            sample=cls.pama,
            source="gtdb",
            taxon_id="gtdb-pa",
            scientific_name=(
                "Pseudomonas aeruginosa"
            ),
            rank="species",
            domain_or_realm="Bacteria",
            phylum="Pseudomonadota",
            class_name="Gammaproteobacteria",
            order_name="Pseudomonadales",
            family="Pseudomonadaceae",
            genus="Pseudomonas",
            species="Pseudomonas aeruginosa",
            match_status=(
                SampleTaxonomyAssignment.STATUS_CANDIDATE
            ),
            is_current=True,
        )


        SampleTaxonomyAssignment.objects.create(
            sample=cls.private,
            source="ncbi",
            taxon_id="private-tax",
            scientific_name="PRIVATE-TAXON-SENTINEL",
            rank="species",
            genus="Private",
            species="Private sentinel",
            match_status=(
                SampleTaxonomyAssignment.STATUS_VERIFIED
            ),
            is_current=True,
        )


        SampleTaxonomyAssignment.objects.create(
            sample=cls.embargoed,
            source="ncbi",
            taxon_id="embargo-tax",
            scientific_name="EMBARGO-TAXON-SENTINEL",
            rank="species",
            genus="Embargo",
            species="Embargo sentinel",
            match_status=(
                SampleTaxonomyAssignment.STATUS_VERIFIED
            ),
            is_current=True,
        )


    def test_curated_species_normalizes_genus_and_species(
        self,
    ):
        rows = [
            row
            for row in public_taxonomy_records()
            if (
                row["source"]
                ==
                "curated"
            )
        ]


        labels = {
            row["species"]
            for row in rows
        }


        self.assertEqual(
            labels,
            {
                "Pseudomonas aeruginosa",
            },
        )


    def test_curated_species_preserves_public_candidates(
        self,
    ):
        rows = [
            row
            for row in public_taxonomy_records()
            if (
                row["source"]
                ==
                "curated"
            )
        ]


        candidates = {
            row["candidate"]
            for row in rows
        }


        self.assertEqual(
            candidates,
            {
                "P. aeruginosa PA14",
                "P. aeruginosa PAMA I",
            },
        )


    def test_verified_current_external_taxonomy_is_available(
        self,
    ):
        rows = public_taxonomy_records()


        ncbi_rows = [
            row
            for row in rows
            if (
                row["source"]
                ==
                "ncbi"
            )
        ]


        self.assertEqual(
            len(
                ncbi_rows
            ),
            1,
        )


        self.assertEqual(
            ncbi_rows[
                0
            ][
                "species"
            ],
            "Pseudomonas aeruginosa",
        )


        self.assertEqual(
            ncbi_rows[
                0
            ][
                "phylum"
            ],
            "Pseudomonadota",
        )


    def test_candidate_external_assignment_is_not_public_taxonomy_evidence(
        self,
    ):
        rows = public_taxonomy_records()


        self.assertFalse(
            any(
                row["source"]
                ==
                "gtdb"
                for row in rows
            )
        )


    def test_private_and_embargoed_taxonomy_cannot_contribute(
        self,
    ):
        serialized = repr(
            public_taxonomy_records()
        )


        for sentinel in (
            "PRIVATE-CANDIDATE-SENTINEL",
            "PRIVATE-TAXON-SENTINEL",
            "PRIVATE-TYPE",
            "EMBARGO-CANDIDATE-SENTINEL",
            "EMBARGO-TAXON-SENTINEL",
            "EMBARGO-TYPE",
        ):
            self.assertNotIn(
                sentinel,
                serialized,
            )


    def test_public_taxonomy_payload_contains_no_sample_identifier(
        self,
    ):
        rows = public_taxonomy_records()


        expected = {
            "source",
            "sample_type",
            "domain_or_realm",
            "kingdom",
            "phylum",
            "class_name",
            "order_name",
            "family",
            "genus",
            "species",
            "candidate",
            "total",
        }


        for row in rows:
            self.assertEqual(
                set(
                    row
                ),
                expected,
            )


    def test_home_context_contains_taxonomy_records(
        self,
    ):
        context = (
            public_home_context()
        )


        self.assertIn(
            "taxonomy_records",
            context,
        )


    def test_network_filters_are_present(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()


        for token in (
            "publicNetworkSearch",
            "publicNetworkSampleType",
            "publicNetworkMinimum",
            "publicNetworkLayout",
            "publicNetworkLabels",
            "publicNetworkReset",
            "filteredNetworkRows",
        ):
            self.assertIn(
                token,
                source,
            )


    def test_network_supports_force_and_circular_layouts(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()


        self.assertIn(
            'value="force"',
            source,
        )

        self.assertIn(
            'value="circular"',
            source,
        )


    def test_ranking_defaults_to_species(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()


        self.assertIn(
            '<option value="species" selected>',
            source,
        )

        self.assertIn(
            "buildRankingGroups",
            source,
        )


    def test_ranking_supports_multiple_taxonomic_levels(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()


        for token in (
            'value="species"',
            'value="genus"',
            'value="family"',
            'value="phylum"',
            'value="candidate"',
        ):
            self.assertIn(
                token,
                source,
            )


    def test_ranking_supports_multiple_chart_styles(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()


        for token in (
            'value="horizontal"',
            'value="vertical"',
            'value="donut"',
            'value="treemap"',
        ):
            self.assertIn(
                token,
                source,
            )


    def test_ranking_candidate_drilldown_is_present(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()


        for token in (
            "publicRankingDetails",
            "publicRankingDetailsList",
            "renderRankingDetails",
            "candidate.candidate",
            "candidate.sample_type",
        ):
            self.assertIn(
                token,
                source,
            )


    def test_bubbles_are_removed(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()


        for forbidden in (
            "publicViewBubbleTab",
            "publicViewBubble",
            "publicBubbleChart",
            "initializeBubbleMatrix",
            'type: "scatter"',
            "Bubbles",
        ):
            self.assertNotIn(
                forbidden,
                source,
            )


    def test_taxonomy_flow_uses_sankey(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()


        for token in (
            "publicViewSankeyTab",
            "Taxonomy Flow",
            "publicSankeySource",
            "publicSankeyDepth",
            "publicSankeyChart",
            "buildSankeyModel",
            'type: "sankey"',
        ):
            self.assertIn(
                token,
                source,
            )


    def test_taxonomy_payload_uses_json_script(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()


        self.assertIn(
            (
                "taxonomy_records"
                '|json_script:'
                '"public-taxonomy-data"'
            ),
            source,
        )


    def test_public_explorer_still_performs_no_client_data_fetch(
        self,
    ):
        source = Path(
            "core/interfaces/public/index.html"
        ).read_text()


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
