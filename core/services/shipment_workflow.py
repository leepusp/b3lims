from core.models import ShipmentDocument, ShipmentChecklistItem, ShipmentEvent
from django.utils import timezone

from core.models import ShipmentChecklistItem, ShipmentDocument, ShipmentEvent
from core.services.shipment_requirements_engine import evaluate_shipment_requirements


DOCUMENT_TYPES_REQUIRING_SIGNATURE = {
    "content_declaration",
    "ogm_transport_notification",
    "cibio_authorization",
    "ctnbio_authorization",
    "mta_ttm",
}


CHECKLIST_TYPE_BY_CODE = {
    "review_route": "data",
    "review_items": "data",
    "review_classification": "data",
    "triple_packaging": "packaging",
    "documents_signed": "document",
    "documents_approved": "document",
    "labels_printed": "label",
}


def _model_field_names(model):
    return {field.name for field in model._meta.fields}


def _safe_defaults(model, values):
    fields = _model_field_names(model)
    return {key: value for key, value in values.items() if key in fields}


def _choice_values(model, field_name):
    try:
        field = model._meta.get_field(field_name)
        return [value for value, _label in field.choices]
    except Exception:
        return []


def _default_document_status():
    available = _choice_values(ShipmentDocument, "status")

    for candidate in ["required", "draft", "pending", "pending_upload"]:
        if candidate in available:
            return candidate

    return available[0] if available else "draft"


def _default_checklist_type(code):
    checklist_type = CHECKLIST_TYPE_BY_CODE.get(code, "document")
    available = _choice_values(ShipmentChecklistItem, "checklist_type")

    if not available or checklist_type in available:
        return checklist_type

    return available[0]


def _document_requires_signature(document_code):
    return document_code in DOCUMENT_TYPES_REQUIRING_SIGNATURE



def _requirement_value(requirement, key, default=None):
    if isinstance(requirement, dict):
        return requirement.get(key, default)

    return getattr(requirement, key, default)


def _model_field_names(model):
    return {field.name for field in model._meta.get_fields()}


def _field_choice_values(model, field_name):
    try:
        field = model._meta.get_field(field_name)
    except Exception:
        return []

    return [value for value, _label in getattr(field, "choices", []) or []]


def _document_default_status():
    choices = _field_choice_values(ShipmentDocument, "status")

    for candidate in ["draft", "required", "pending", "not_started"]:
        if candidate in choices:
            return candidate

    return choices[0] if choices else "draft"


def _checklist_default_type(category):
    choices = _field_choice_values(ShipmentChecklistItem, "checklist_type")

    preferred = str(category or "data")

    if preferred in choices:
        return preferred

    for candidate in ["data", "document", "label", "general"]:
        if candidate in choices:
            return candidate

    return choices[0] if choices else preferred


def _set_if_field(instance, fields, name, value, update_fields):
    if name not in fields:
        return

    if getattr(instance, name, None) != value:
        setattr(instance, name, value)
        update_fields.append(name)


def _sync_documents(shipment, requirements):
    created_count = 0
    fields = _model_field_names(ShipmentDocument)

    for requirement in requirements.get("documents", []):
        document_type = _requirement_value(requirement, "code", "")
        label = _requirement_value(requirement, "label", document_type)
        reason = _requirement_value(requirement, "reason", "")
        requires_signature = bool(_requirement_value(requirement, "requires_signature", False))

        if not document_type:
            continue

        defaults = {}

        if "status" in fields:
            defaults["status"] = _document_default_status()
        if "title" in fields:
            defaults["title"] = label
        if "label" in fields:
            defaults["label"] = label
        if "name" in fields:
            defaults["name"] = label
        if "description" in fields:
            defaults["description"] = reason
        if "notes" in fields:
            defaults["notes"] = reason
        if "requires_signature" in fields:
            defaults["requires_signature"] = requires_signature

        document, created = ShipmentDocument.objects.get_or_create(
            shipment=shipment,
            document_type=document_type,
            defaults=defaults,
        )

        if created:
            created_count += 1
            continue

        update_fields = []

        _set_if_field(document, fields, "title", label, update_fields)
        _set_if_field(document, fields, "label", label, update_fields)
        _set_if_field(document, fields, "name", label, update_fields)
        _set_if_field(document, fields, "description", reason, update_fields)
        _set_if_field(document, fields, "requires_signature", requires_signature, update_fields)

        if update_fields:
            document.save(update_fields=update_fields)

    return created_count

def _sync_checklist(shipment, requirements):
    created_count = 0
    fields = _model_field_names(ShipmentChecklistItem)

    def create_item(category, label, reason=""):
        nonlocal created_count

        checklist_type = _checklist_default_type(category)

        existing = shipment.checklist_items.filter(
            checklist_type=checklist_type,
            label=label,
        ).first()

        if existing:
            return

        kwargs = {
            "shipment": shipment,
        }

        if "checklist_type" in fields:
            kwargs["checklist_type"] = checklist_type
        if "label" in fields:
            kwargs["label"] = label
        if "is_completed" in fields:
            kwargs["is_completed"] = False
        if "notes" in fields:
            kwargs["notes"] = reason
        if "description" in fields:
            kwargs["description"] = reason

        ShipmentChecklistItem.objects.create(**kwargs)
        created_count += 1

    for requirement in requirements.get("checklist", []):
        category = _requirement_value(requirement, "category", "data")
        label = _requirement_value(requirement, "label", _requirement_value(requirement, "code", "Checklist item"))
        reason = _requirement_value(requirement, "reason", "")
        create_item(category, label, reason)

    for requirement in requirements.get("documents", []):
        label = _requirement_value(requirement, "label", _requirement_value(requirement, "code", "Document"))
        reason = _requirement_value(requirement, "reason", "")
        create_item("document", f"Required document available: {label}", reason)

    for requirement in requirements.get("labels", []):
        label = _requirement_value(requirement, "label", _requirement_value(requirement, "code", "Label"))
        reason = _requirement_value(requirement, "reason", "")
        create_item("label", f"Required label available: {label}", reason)

    return created_count

def sync_shipment_requirements(shipment, actor=None):
    """
    Synchronize required shipment documents, labels and checklist items.

    Pending checklist items are rebuilt from the requirements engine to avoid
    duplicates from older workflow versions. Completed checklist items are
    preserved.
    """
    requirements = evaluate_shipment_requirements(shipment)

    documents_created = _sync_documents(shipment, requirements)

    deleted_pending_checklist = (
        shipment.checklist_items
        .filter(is_completed=False)
        .delete()[0]
    )

    checklist_created = _sync_checklist(shipment, requirements)

    if hasattr(shipment, "updated_at"):
        shipment.updated_at = timezone.now()
        shipment.save(update_fields=["updated_at"])

    if actor is not None:
        ShipmentEvent.objects.create(
            shipment=shipment,
            event_type="updated",
            actor=actor,
            notes=(
                "Shipment requirements synchronized using requirements engine. "
                f"Documents created: {documents_created}. "
                f"Checklist items deleted: {deleted_pending_checklist}. "
                f"Checklist items created: {checklist_created}."
            ),
        )

    return {
        "documents_created": documents_created,
        "checklist_deleted": deleted_pending_checklist,
        "checklist_created": checklist_created,
        "requirements": requirements,
        "message": "Shipment requirements synchronized using requirements engine.",
    }
