from django.utils import timezone

from core.models import (
    Shipment,
    ShipmentDocument,
    ShipmentChecklistItem,
    ShipmentEvent,
)


DOCUMENT_LABELS = {
    "content_declaration": "Content declaration",
    "sender_declaration": "Sender declaration",
    "external_package_identification": "External package identification",
    "triple_packaging_checklist": "Triple packaging checklist",
    "ogm_transport_notification": "OGM transport notification",
    "mta_ttm": "MTA/TTM",
    "shipment_invoice": "Shipment invoice",
    "receipt_confirmation": "Receipt confirmation",
}


def sync_shipment_requirements(shipment, actor=None):
    """
    Recalculate transport requirements based on the shipment classification.

    This function creates missing ShipmentDocument and ShipmentChecklistItem
    records, but does not delete existing records.
    """
    classification = getattr(shipment, "classification", None)

    if classification is None:
        return {
            "documents_created": 0,
            "checklist_created": 0,
            "message": "Shipment has no classification yet.",
        }

    classification.apply_default_rules(save=True)

    documents_created = 0
    checklist_created = 0

    required_documents = classification.required_document_types()

    for document_type in required_documents:
        _, created = ShipmentDocument.objects.get_or_create(
            shipment=shipment,
            document_type=document_type,
            defaults={
                "status": "draft",
                "requires_signature": document_type in [
                    "content_declaration",
                    "sender_declaration",
                    "ogm_transport_notification",
                    "mta_ttm",
                    "shipment_invoice",
                ],
            },
        )
        if created:
            documents_created += 1

    base_items = [
        ("data", "Origin and destination information reviewed"),
        ("data", "Shipment items reviewed"),
        ("data", "Responsible sender and recipient identified"),
    ]

    for document_type in required_documents:
        base_items.append(
            ("document", f"Required document available: {DOCUMENT_LABELS.get(document_type, document_type)}")
        )

    if classification.requires_triple_packaging:
        base_items.append(("packaging", "Triple packaging confirmed"))

    if classification.requires_biohazard_label:
        base_items.append(("label", "Biohazard label required"))

    if classification.requires_un3373_label:
        base_items.append(("label", "UN3373 label required"))

    if classification.requires_external_package_identification:
        base_items.append(("label", "External package identification required"))

    if classification.requires_cibio_notification:
        base_items.append(("authorization", "CIBio notification required"))

    if classification.requires_ctnbio_authorization:
        base_items.append(("authorization", "CTNBio authorization required"))

    if classification.requires_sisgen:
        base_items.append(("authorization", "SisGen information required"))

    for checklist_type, label in base_items:
        _, created = ShipmentChecklistItem.objects.get_or_create(
            shipment=shipment,
            checklist_type=checklist_type,
            label=label,
            defaults={
                "is_required": True,
                "is_completed": False,
            },
        )
        if created:
            checklist_created += 1

    ShipmentEvent.objects.create(
        shipment=shipment,
        event_type="classified",
        actor=actor,
        notes=(
            f"Requirements synchronized. "
            f"Documents created: {documents_created}. "
            f"Checklist items created: {checklist_created}."
        ),
    )

    return {
        "documents_created": documents_created,
        "checklist_created": checklist_created,
        "message": "Shipment requirements synchronized.",
    }


def mark_shipment_status(shipment, status, actor=None, notes=""):
    old_status = shipment.status
    shipment.status = status
    shipment.updated_at = timezone.now()
    shipment.save(update_fields=["status", "updated_at"])

    ShipmentEvent.objects.create(
        shipment=shipment,
        event_type="updated",
        actor=actor,
        notes=notes or f"Status changed from {old_status} to {status}.",
    )

    return shipment
