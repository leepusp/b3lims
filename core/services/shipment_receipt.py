from django.utils import timezone

from core.models import (
    Shipment,
    ShipmentEvent,
    ShipmentReceipt,
    SampleImportBatch,
    SampleIntakeRecord,
)


def mark_shipment_received(shipment, user=None, notes=""):
    receipt, _ = ShipmentReceipt.objects.get_or_create(
        shipment=shipment,
        defaults={
            "received_by": user,
            "received_at": timezone.now(),
            "package_condition": "intact",
            "package_integrity_confirmed": True,
            "documents_received": False,
            "items_checked": False,
            "notes": notes,
        },
    )

    shipment.status = "received_pending_qc"
    shipment.received_at = timezone.now()
    shipment.save(update_fields=["status", "received_at", "updated_at"])

    ShipmentEvent.objects.create(
        shipment=shipment,
        event_type="received",
        actor=user,
        notes=notes or "Shipment marked as received and pending QC.",
    )

    return receipt


def create_intake_records_from_shipment(shipment, user=None):
    receipt = getattr(shipment, "receipt", None)

    if receipt is None or shipment.status != "received_pending_qc":
        return {
            "batch": None,
            "created": 0,
            "skipped": shipment.items.count(),
            "blocked": True,
            "message": "Shipment receipt must be confirmed before generating intake records.",
        }

    batch = None
    if receipt and receipt.created_intake_batch:
        batch = receipt.created_intake_batch

    if batch is None:
        batch = SampleImportBatch.objects.create(
            uploaded_by=user,
            original_filename=f"{shipment.shipment_code}_shipment_receipt",
            total_rows=shipment.items.count(),
            valid_rows=0,
            invalid_rows=0,
            notes=f"Generated from shipment {shipment.shipment_code}.",
        )

    created = 0
    skipped = 0

    for index, item in enumerate(shipment.items.all(), start=1):
        # If the item is already linked to an existing Sample, it does not need
        # an intake record.
        if item.sample_id:
            skipped += 1
            continue

        # If this item already has an intake record, do not duplicate it.
        if item.intake_record_id:
            skipped += 1
            continue

        imported_sample_id = item.imported_sample_id or f"{shipment.shipment_code}-ITEM-{index:03d}"
        sample_type = item.sample_type or "Other"
        organism_name = item.material_name or imported_sample_id

        normalized_data = {
            "sample_id": imported_sample_id,
            "sample_type": sample_type,
            "organism_name": organism_name,
            "biobank": shipment.destination_biobank.name if shipment.destination_biobank else "",
            "collection": "",
            "storage_location": item.storage_condition or "",
            "provider": shipment.sender_institution or shipment.sender_responsible_name or "",
            "is_public": "False",
            "scientific_notes": item.notes or shipment.notes or "",
        }

        record = SampleIntakeRecord.objects.create(
            batch=batch,
            row_number=index,
            imported_sample_id=imported_sample_id,
            sample_type=sample_type,
            organism_name=organism_name,
            biobank_name=normalized_data["biobank"],
            collection_name="",
            matched_biobank=shipment.destination_biobank,
            storage_location=item.storage_condition or "",
            provider=normalized_data["provider"],
            is_public=False,
            scientific_notes=normalized_data["scientific_notes"],
            raw_data=normalized_data,
            normalized_data=normalized_data,
            validation_errors={},
            validation_warnings={},
            status="ready",
        )

        item.intake_record = record
        item.save(update_fields=["intake_record"])

        created += 1

    batch.valid_rows = batch.records.filter(status="ready").count()
    batch.invalid_rows = batch.records.exclude(status="ready").count()
    batch.total_rows = batch.records.count()
    batch.save(update_fields=["valid_rows", "invalid_rows", "total_rows"])

    if receipt:
        receipt.created_intake_batch = batch
        receipt.items_checked = True
        receipt.save(update_fields=["created_intake_batch", "items_checked", "updated_at"])

    ShipmentEvent.objects.create(
        shipment=shipment,
        event_type="qc_checked",
        actor=user,
        notes=f"Intake generation completed. Created: {created}. Skipped: {skipped}.",
    )

    return {
        "batch": batch,
        "created": created,
        "skipped": skipped,
        "blocked": False,
        "message": "Intake records generated.",
    }
