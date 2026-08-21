from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Sample
from core.models.samples.relationship import SampleRelationship


class SampleNetworkV2Tests(TestCase):

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="networkowner",
            password="test-password",
        )

        self.other = User.objects.create_user(
            username="networkother",
            password="test-password",
        )

        self.visible_a = Sample.objects.create(
            sample_id="NET-VISIBLE-A",
            sample_type="Bacterium (Host)",
            organism_name="Visible organism A",
            owner=self.owner,
            status="available",
            is_public=False,
            is_active=True,
        )

        self.visible_b = Sample.objects.create(
            sample_id="NET-VISIBLE-B",
            sample_type="Plasmid",
            organism_name="Visible organism B",
            owner=self.owner,
            status="available",
            is_public=False,
            is_active=True,
        )

        self.hidden = Sample.objects.create(
            sample_id="NET-HIDDEN",
            sample_type="Bacterium (Host)",
            organism_name="Hidden organism",
            owner=self.other,
            status="available",
            is_public=False,
            is_active=True,
        )

        self.visible_relation = (
            SampleRelationship.objects.create(
                source_sample=self.visible_a,
                target_sample=self.visible_b,
                relationship_type="aliquot",
                created_by=self.owner,
                notes="Visible relationship",
            )
        )

        self.hidden_relation = (
            SampleRelationship.objects.create(
                source_sample=self.visible_a,
                target_sample=self.hidden,
                relationship_type="other",
                created_by=self.owner,
                notes="Must not leak",
            )
        )

        self.client.force_login(
            self.owner
        )

    @staticmethod
    def client_path(url):
        prefix = str(
            getattr(
                settings,
                "FORCE_SCRIPT_NAME",
                "",
            )
            or ""
        )

        if (
            prefix
            and url.startswith(
                prefix
            )
        ):
            return (
                url[len(prefix):]
                or "/"
            )

        return url

    def get_network(self):
        return self.client.get(
            self.client_path(
                reverse(
                    "samples_network"
                )
            )
        )

    def test_network_only_serializes_visible_nodes(self):
        response = self.get_network()

        self.assertEqual(
            response.status_code,
            200,
        )

        nodes = response.context[
            "network_nodes"
        ]

        sample_ids = {
            node["sample_id"]
            for node in nodes
        }

        self.assertIn(
            "NET-VISIBLE-A",
            sample_ids,
        )

        self.assertIn(
            "NET-VISIBLE-B",
            sample_ids,
        )

        self.assertNotIn(
            "NET-HIDDEN",
            sample_ids,
        )

    def test_network_excludes_edges_with_hidden_endpoint(self):
        response = self.get_network()

        edges = response.context[
            "network_edges"
        ]

        relationship_ids = {
            edge["id"]
            for edge in edges
        }

        self.assertIn(
            (
                f"relationship-"
                f"{self.visible_relation.pk}"
            ),
            relationship_ids,
        )

        self.assertNotIn(
            (
                f"relationship-"
                f"{self.hidden_relation.pk}"
            ),
            relationship_ids,
        )

        self.assertNotIn(
            "Must not leak",
            str(edges),
        )

    def test_network_serializes_filter_and_inspector_metadata(self):
        response = self.get_network()

        nodes = response.context[
            "network_nodes"
        ]

        node = next(
            item
            for item in nodes
            if item["sample_id"]
            == "NET-VISIBLE-A"
        )

        self.assertEqual(
            node["node_type"],
            "bacteria",
        )

        self.assertEqual(
            node["status_label"],
            self.visible_a.get_status_display(),
        )

        self.assertEqual(
            node["owner"],
            "networkowner",
        )

        self.assertEqual(
            node["degree"],
            1,
        )

        self.assertTrue(
            node["detail_url"].endswith(
                (
                    f"/samples/"
                    f"{self.visible_a.pk}/"
                )
            )
        )

    def test_network_template_exposes_v2_controls(self):
        response = self.get_network()

        for token in (
            "Network Filters",
            "network-filter-biosafety",
            "network-filter-owner",
            "network-filter-biobank",
            "network-filter-group",
            "network-filter-collection",
            "network-connected-only",
            "network-layout",
            "network-cluster-by",
            "Inspector",
        ):
            self.assertContains(
                response,
                token,
            )
