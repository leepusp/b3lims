from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import RequestFactory, TestCase

from core.models import Shipment, ShipmentItem
from core.services.shipment_document_generator import (
    get_initial_values_from_shipment,
)
from core.shipment_forms import (
    ShipmentItemSetupForm,
    ShipmentSetupForm,
)
from core.views.internal.shipments.views import (
    _shipment_document_workspace_template,
)


class DynamicShipmentSetupTests(TestCase):
    def test_setup_exposes_sender_and_recipient_responsibility(self):
        form = ShipmentSetupForm()

        expected_fields = {
            "sender_responsible_name",
            "sender_group_researcher",
            "recipient_responsible_name",
            "recipient_group_researcher",
        }

        self.assertTrue(expected_fields.issubset(form.fields))

        self.assertEqual(
            form.fields["sender_responsible_name"].label,
            "Sender Responsible Person",
        )
        self.assertEqual(
            form.fields["sender_group_researcher"].label,
            "Sender Group / Laboratory / Researcher",
        )
        self.assertEqual(
            form.fields["recipient_responsible_name"].label,
            "Recipient Responsible Person",
        )
        self.assertEqual(
            form.fields["recipient_group_researcher"].label,
            "Recipient Group / Laboratory / Researcher",
        )

    def test_quantity_default_is_rendered_as_one(self):
        item = ShipmentItem(quantity=Decimal("1.000"))
        form = ShipmentItemSetupForm(instance=item)
        html = str(form["quantity"])

        self.assertIn('value="1"', html)
        self.assertNotIn('value="1.000"', html)
        self.assertIn('step="0.001"', html)

    def test_fractional_quantity_keeps_precision(self):
        item = ShipmentItem(quantity=Decimal("0.500"))
        form = ShipmentItemSetupForm(instance=item)
        html = str(form["quantity"])

        self.assertIn('value="0.5"', html)

    def test_shipment_contacts_populate_dynamic_document(self):
        shipment = Shipment.objects.create(
            sender_institution="Sender Institute",
            sender_responsible_name="Sender Person",
            sender_group_researcher="Sender Laboratory",
            recipient_institution="Recipient Institute",
            recipient_responsible_name="Recipient Person",
            recipient_group_researcher="Recipient Laboratory",
        )

        values = get_initial_values_from_shipment(
            shipment,
            "content_declaration",
        )

        self.assertEqual(values["sender_name"], "Sender Person")
        self.assertEqual(
            values["sender_lab_cqb"],
            "Sender Laboratory",
        )
        self.assertEqual(values["recipient_name"], "Recipient Person")
        self.assertEqual(
            values["recipient_lab_cqb"],
            "Recipient Laboratory",
        )


class DynamicShipmentDocumentWorkspaceTests(TestCase):
    def test_default_request_uses_dynamic_wizard(self):
        request = RequestFactory().get("/shipments/1/documents/1/")

        self.assertEqual(
            _shipment_document_workspace_template(request),
            "internal/shipments/document_workspace_wizard.html",
        )

    def test_legacy_classic_query_uses_dynamic_wizard(self):
        request = RequestFactory().get(
            "/shipments/1/documents/1/?ui=classic"
        )

        self.assertEqual(
            _shipment_document_workspace_template(request),
            "internal/shipments/document_workspace_wizard.html",
        )

    def test_dynamic_wizard_has_no_classic_layout_control(self):
        wizard_path = (
            Path(settings.BASE_DIR)
            / "core"
            / "interfaces"
            / "internal"
            / "shipments"
            / "document_workspace_wizard.html"
        )

        source = wizard_path.read_text()

        self.assertNotIn("Classic Layout", source)
        self.assertNotIn("?ui=classic", source)
