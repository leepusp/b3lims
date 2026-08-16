from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models.shipments.shipment import (
    Shipment,
    ShipmentChecklistItem,
    ShipmentEvent,
)
from core.services.shipment_requirements_engine import (
    evaluate_shipment_requirements,
)


def request_path(name, args=None):
    return reverse(name, args=args).removeprefix("/biobank")


@override_settings(FORCE_SCRIPT_NAME=None)
class ShipmentTransportGuidanceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()

        self.requester = user_model.objects.create_user(
            username="shipment-requester",
            password="test-password",
        )
        self.reviewer = user_model.objects.create_user(
            username="shipment-reviewer",
            password="test-password",
        )
        self.staff = user_model.objects.create_user(
            username="shipment-staff",
            password="test-password",
            is_staff=True,
        )

        self.shipment = Shipment.objects.create(
            requested_by=self.requester,
            reviewed_by=self.reviewer,
            flow_type="outgoing_shipment",
        )

        self.detail_path = request_path(
            "shipment_detail",
            [self.shipment.id],
        )

    def active_guidance(self):
        requirements = evaluate_shipment_requirements(self.shipment)
        self.assertTrue(requirements["guidance"])
        return requirements["guidance"][0]

    def create_guidance_item(self, requirement=None, **overrides):
        requirement = requirement or self.active_guidance()

        values = {
            "shipment": self.shipment,
            "checklist_type": requirement.category,
            "label": requirement.label,
            "is_required": True,
        }
        values.update(overrides)

        return ShipmentChecklistItem.objects.create(**values)

    def post_guidance(self, item, completed=True):
        payload = {
            "action": "toggle_transport_guidance",
            "guidance_item_id": str(item.id),
        }

        if completed:
            payload["is_completed"] = "1"

        return self.client.post(self.detail_path, payload)

    def test_engine_separates_guidance_from_documents(self):
        requirements = evaluate_shipment_requirements(self.shipment)

        document_codes = {
            requirement.code
            for requirement in requirements["documents"]
        }
        guidance_codes = {
            requirement.code
            for requirement in requirements["guidance"]
        }

        self.assertIn("content_declaration", document_codes)
        self.assertIn("mta_ttm", document_codes)
        self.assertIn(
            "external_package_identification",
            guidance_codes,
        )
        self.assertTrue(document_codes.isdisjoint(guidance_codes))

    def test_detail_renders_separate_document_and_guidance_tabs(self):
        guidance = self.active_guidance()
        self.create_guidance_item(guidance)
        self.client.force_login(self.requester)

        response = self.client.get(self.detail_path)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="documents-approvals-tab"',
        )
        self.assertContains(
            response,
            'id="documents-approvals"',
        )
        self.assertContains(
            response,
            'id="transport-guidance-tab"',
        )
        self.assertContains(
            response,
            'id="transport-guidance"',
        )
        self.assertContains(
            response,
            "Documents & approvals",
        )
        self.assertContains(
            response,
            "Transport guidance",
        )
        self.assertContains(
            response,
            "Operational preparation checklist",
        )
        self.assertContains(
            response,
            guidance.label,
        )
        self.assertContains(
            response,
            'value="toggle_transport_guidance"',
        )
        self.assertTrue(
            response.context["can_update_transport_guidance"]
        )

    def test_requester_can_confirm_active_guidance(self):
        item = self.create_guidance_item()
        self.client.force_login(self.requester)

        response = self.post_guidance(
            item,
            completed=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.endswith("#transport-guidance")
        )

        item.refresh_from_db()

        self.assertTrue(item.is_completed)
        self.assertEqual(
            item.completed_by,
            self.requester,
        )
        self.assertIsNotNone(item.completed_at)

        event = ShipmentEvent.objects.get(
            shipment=self.shipment,
            event_type="updated",
        )

        self.assertEqual(
            event.actor,
            self.requester,
        )
        self.assertIn(
            item.label,
            event.notes,
        )
        self.assertIn(
            "confirmed",
            event.notes,
        )

    def test_requester_can_remove_guidance_confirmation(self):
        item = self.create_guidance_item(
            is_completed=True,
            completed_by=self.requester,
            completed_at=timezone.now(),
        )
        self.client.force_login(self.requester)

        response = self.post_guidance(
            item,
            completed=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.endswith("#transport-guidance")
        )

        item.refresh_from_db()

        self.assertFalse(item.is_completed)
        self.assertIsNone(item.completed_by)
        self.assertIsNone(item.completed_at)

        event = ShipmentEvent.objects.get(
            shipment=self.shipment,
            event_type="updated",
        )

        self.assertIn(
            "confirmation removed",
            event.notes,
        )

    def test_non_guidance_checklist_item_cannot_be_toggled(self):
        item = ShipmentChecklistItem.objects.create(
            shipment=self.shipment,
            checklist_type="document",
            label="Documents signed",
            is_required=True,
        )
        self.client.force_login(self.requester)

        response = self.post_guidance(
            item,
            completed=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.endswith("#transport-guidance")
        )

        item.refresh_from_db()

        self.assertFalse(item.is_completed)
        self.assertFalse(
            ShipmentEvent.objects.filter(
                shipment=self.shipment,
                event_type="updated",
            ).exists()
        )

    def test_reviewer_can_view_but_cannot_update_guidance(self):
        item = self.create_guidance_item()
        self.client.force_login(self.reviewer)

        response = self.client.get(self.detail_path)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            response.context["can_update_transport_guidance"]
        )
        self.assertContains(
            response,
            "Only the shipment requester or an administrator "
            "can change this confirmation.",
        )

        response = self.post_guidance(
            item,
            completed=True,
        )

        self.assertEqual(response.status_code, 403)

        item.refresh_from_db()

        self.assertFalse(item.is_completed)
        self.assertFalse(
            ShipmentEvent.objects.filter(
                shipment=self.shipment,
            ).exists()
        )

    def test_staff_can_update_guidance(self):
        item = self.create_guidance_item()
        self.client.force_login(self.staff)

        response = self.post_guidance(
            item,
            completed=True,
        )

        self.assertEqual(response.status_code, 302)

        item.refresh_from_db()

        self.assertTrue(item.is_completed)
        self.assertEqual(
            item.completed_by,
            self.staff,
        )
