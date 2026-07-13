from django.utils import timezone

from core.models import ShipmentEvent


SIGNATURE_REQUIRED_DOCUMENT_TYPES = [
    "content_declaration",
    "cibio_authorization",
    "ogm_transport_notification",
    "mta_ttm",
    "shipment_invoice",
]

FINAL_OUTPUT_RELEASED_STATUSES = [
    "authorized",
    "packing",
    "ready_for_dispatch",
    "in_transit",
    "received_pending_qc",
    "accepted",
]


def _status_value_for_document(document, preferred_values):
    field = document._meta.get_field("status")
    available = [value for value, _label in field.choices]

    for value in preferred_values:
        if value in available:
            return value

    return None


def document_signed_file(document):
    """
    Return the signed file regardless of whether it was stored on the
    ShipmentDocument or on its ShipmentDocumentFormData workspace.
    """
    for field_name in ["signed_file", "uploaded_file"]:
        file_field = getattr(document, field_name, None)

        if file_field:
            return file_field

    try:
        form_data = document.form_data
    except Exception:
        form_data = None

    if form_data is not None:
        for field_name in ["signed_file", "uploaded_file"]:
            file_field = getattr(form_data, field_name, None)

            if file_field:
                return file_field

    return None


def document_has_signed_file(document):
    return bool(document_signed_file(document))


def normalize_document_signature_rules(shipment):
    updated = 0

    for document in shipment.documents.all():
        should_require_signature = (
            document.document_type in SIGNATURE_REQUIRED_DOCUMENT_TYPES
        )

        if document.requires_signature != should_require_signature:
            document.requires_signature = should_require_signature
            document.save(update_fields=["requires_signature"])
            updated += 1

    return updated


def get_pending_required_signed_documents(shipment):
    normalize_document_signature_rules(shipment)

    pending = []

    for document in shipment.documents.filter(requires_signature=True):
        if not document_has_signed_file(document):
            pending.append(document)

    return pending


def all_required_signed_documents_uploaded(shipment):
    return len(get_pending_required_signed_documents(shipment)) == 0


def can_release_final_package_outputs(shipment):
    """
    Final package outputs are released only after required signed documents
    are uploaded and the internal team authorizes the shipment.
    """
    return (
        all_required_signed_documents_uploaded(shipment)
        and shipment.status in FINAL_OUTPUT_RELEASED_STATUSES
    )


def update_status_after_public_document_upload(shipment):
    pending = get_pending_required_signed_documents(shipment)

    if pending:
        target_status = "waiting_documents"
        note = (
            "Signed document uploaded, but required signed documents "
            "are still pending."
        )
    else:
        target_status = "waiting_authorization"
        note = (
            "All required signed documents were uploaded through the public portal. "
            "Shipment is waiting for internal review and authorization."
        )

    if shipment.status != target_status:
        old_status = shipment.status
        shipment.status = target_status
        shipment.updated_at = timezone.now()
        shipment.save(update_fields=["status", "updated_at"])

        ShipmentEvent.objects.create(
            shipment=shipment,
            event_type="updated",
            actor=None,
            notes=f"{note} Status changed from {old_status} to {target_status}.",
        )

    return {
        "pending_count": len(pending),
        "pending_documents": pending,
        "status": shipment.status,
        "can_release_final_outputs": can_release_final_package_outputs(shipment),
    }


def approve_document_package(shipment, actor=None):
    """
    Approve uploaded signed documents and authorize final package outputs.
    """
    pending = get_pending_required_signed_documents(shipment)

    if pending:
        return {
            "approved": False,
            "pending_count": len(pending),
            "pending_documents": pending,
            "message": "Required signed documents are still pending.",
        }

    updated_documents = 0

    for document in shipment.documents.filter(requires_signature=True):
        approved_status = _status_value_for_document(
            document,
            ["approved", "accepted", "reviewed", "uploaded"],
        )

        if approved_status and document.status != approved_status:
            document.status = approved_status
            document.save(update_fields=["status"])
            updated_documents += 1

    old_status = shipment.status
    shipment.status = "authorized"
    shipment.updated_at = timezone.now()
    shipment.save(update_fields=["status", "updated_at"])

    ShipmentEvent.objects.create(
        shipment=shipment,
        event_type="updated",
        actor=actor,
        notes=(
            "Required signed documents approved. "
            "Final package labels and package QR were released. "
            f"Status changed from {old_status} to authorized."
        ),
    )

    return {
        "approved": True,
        "pending_count": 0,
        "pending_documents": [],
        "updated_documents": updated_documents,
        "message": "Documents approved and final package outputs released.",
    }
