from core.models import (
    Shipment,
    ShipmentItem,
    TransportClassification,
    ShipmentEvent,
)
from core.services.shipment_workflow import sync_shipment_requirements


def infer_material_type(sample):
    sample_type = (sample.sample_type or "").lower()

    if "bacter" in sample_type or "host" in sample_type:
        return "bacteria"

    if "phage" in sample_type or "virus" in sample_type:
        return "phage"

    if "plasmid" in sample_type:
        return "plasmid"

    return "unknown"


def create_shipment_from_sample(sample, user=None, flow_type="outgoing_shipment"):
    """
    Create a draft shipment from an existing Sample.

    The shipment is intentionally created as draft because the user still needs
    to complete destination, transport, classification, documents and labels.
    """
    origin_biobank = getattr(sample, "biobank", None)

    shipment = Shipment.objects.create(
        flow_type=flow_type,
        status="draft",
        origin_biobank=origin_biobank,
        requested_by=user,
        sender_institution=origin_biobank.name if origin_biobank else "",
        notes=f"Draft shipment created from sample {sample.sample_id}.",
    )

    ShipmentItem.objects.create(
        shipment=shipment,
        sample=sample,
        quantity=1,
        quantity_unit="unit",
        container_count=1,
        container_type="tube",
        storage_condition=sample.storage_location or "",
    )

    classification = TransportClassification.objects.create(
        shipment=shipment,
        material_type=infer_material_type(sample),
        risk_class="unknown",
        biosafety_level="unknown",
        is_ogm=False,
        is_genetic_heritage=False,
        is_international=False,
    )

    classification.apply_default_rules(save=True)

    ShipmentEvent.objects.create(
        shipment=shipment,
        event_type="created",
        actor=user,
        notes=f"Shipment created from sample {sample.sample_id}.",
    )

    sync_shipment_requirements(shipment, actor=user)

    return shipment
