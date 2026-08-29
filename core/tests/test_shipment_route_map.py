from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models.biobanks.biobank import Biobank
from core.models.shipments.shipment import (
    Shipment,
    ShipmentEvent,
    ShipmentItem,
)
from core.services.shipment_route_map import (
    build_shipment_route_map_context,
)


class ShipmentRouteMapTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="route-map-user",
            password="test-password",
            is_staff=True,
        )

        self.origin = Biobank.objects.create(
            name="São Paulo Biobank",
            owner=self.user,
            location_label="São Paulo, SP, Brazil",
            latitude=Decimal("-23.550520"),
            longitude=Decimal("-46.633308"),
        )

        self.destination = Biobank.objects.create(
            name="Recife Biobank",
            owner=self.user,
            location_label="Recife, PE, Brazil",
            latitude=Decimal("-8.047562"),
            longitude=Decimal("-34.877000"),
        )

        self.no_coordinates = Biobank.objects.create(
            name="Unmapped Biobank",
            owner=self.user,
            location_label="Coordinate pending",
        )

        self.mapped = Shipment.objects.create(
            requested_by=self.user,
            origin_biobank=self.origin,
            destination_biobank=self.destination,
            flow_type="outgoing_shipment",
            status="in_transit",
            carrier_name="Example Carrier",
            tracking_code="TRACK-001",
            temperature_condition="2-8 C",
        )

        ShipmentItem.objects.create(
            shipment=self.mapped,
            imported_sample_id="SAMPLE-ROUTE-001",
            material_name="Example material",
            sample_type="bacteria",
            quantity=1,
            quantity_unit="vial",
        )

        ShipmentEvent.objects.create(
            shipment=self.mapped,
            event_type="dispatched",
            actor=self.user,
            notes="Handed to carrier.",
        )

        self.partial = Shipment.objects.create(
            requested_by=self.user,
            origin_biobank=self.origin,
            destination_biobank=self.no_coordinates,
            flow_type="internal_transfer",
            status="ready_for_dispatch",
        )

        self.unmapped = Shipment.objects.create(
            requested_by=self.user,
            sender_institution="External Origin",
            sender_address="External address",
            recipient_institution="External Destination",
            recipient_address="Another external address",
            flow_type="external_transfer",
            status="draft",
        )

    def route_context(self):
        qs = (
            Shipment.objects
            .select_related(
                "origin_biobank",
                "destination_biobank",
            )
            .prefetch_related(
                "items__sample",
                "events__actor",
            )
            .order_by("id")
        )

        return build_shipment_route_map_context(
            qs
        )

    def test_route_mapping_classification(self):
        context = self.route_context()

        routes = {
            route["id"]: route
            for route
            in context[
                "shipment_route_map_data"
            ]["routes"]
        }

        self.assertEqual(
            routes[
                self.mapped.id
            ]["mapping_status"],
            "mapped",
        )

        self.assertEqual(
            routes[
                self.partial.id
            ]["mapping_status"],
            "partial",
        )

        self.assertEqual(
            routes[
                self.unmapped.id
            ]["mapping_status"],
            "unmapped",
        )

        stats = context[
            "shipment_route_map_stats"
        ]

        self.assertEqual(
            stats,
            {
                "total": 3,
                "mapped": 1,
                "partial": 1,
                "unmapped": 1,
            },
        )

    def test_payload_contains_manifest_and_timeline(self):
        context = self.route_context()

        route = next(
            route
            for route
            in context[
                "shipment_route_map_data"
            ]["routes"]
            if route["id"]
            == self.mapped.id
        )

        self.assertEqual(
            route["items"][0]["sample_id"],
            "SAMPLE-ROUTE-001",
        )

        self.assertEqual(
            route["events"][0]["event_type"],
            "dispatched",
        )

        self.assertEqual(
            route["origin"]["name"],
            "São Paulo Biobank",
        )

        self.assertEqual(
            route["destination"]["name"],
            "Recife Biobank",
        )

    def test_unmapped_external_address_is_not_geocoded(self):
        context = self.route_context()

        route = next(
            route
            for route
            in context[
                "shipment_route_map_data"
            ]["routes"]
            if route["id"]
            == self.unmapped.id
        )

        self.assertIsNone(
            route["origin"]["latitude"]
        )

        self.assertIsNone(
            route["origin"]["longitude"]
        )

        self.assertIsNone(
            route["destination"]["latitude"]
        )

        self.assertIsNone(
            route["destination"]["longitude"]
        )

        self.assertEqual(
            route["origin"]["address"],
            "External address",
        )

    def test_dashboard_exposes_route_tracking_interface(self):
        self.client.force_login(
            self.user
        )

        response = self.client.get(
            reverse(
                "shipments_dashboard"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        for expected in (
            "Shipment Route Tracking",
            'id="shipment-route-map"',
            'id="shipment-route-map-data"',
            'data-route-filter="search"',
            'data-route-filter="status"',
            'data-route-filter="flow"',
            'data-route-filter="carrier"',
            'data-route-filter="origin"',
            'data-route-filter="destination"',
            'data-route-filter="temperature"',
            'data-route-filter="mapping"',
            "SAMPLE-ROUTE-001",
        ):
            self.assertContains(
                response,
                expected,
            )

        self.assertNotContains(
            response,
            "Recent transport routes",
        )
