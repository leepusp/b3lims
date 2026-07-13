from dataclasses import dataclass


@dataclass(frozen=True)
class Requirement:
    code: str
    label: str
    category: str
    reason: str = ""
    requires_signature: bool = False


DOCUMENTS = {
    "content_declaration": {
        "label": "Content declaration and traceability",
        "category": "document",
        "reason": "Required consolidated content, traceability, compliance, and sender responsibility document.",
        "requires_signature": True,
    },
    "sender_declaration": {
        "label": "Legacy ANTT sender declaration",
        "category": "document",
        "reason": "Required sender responsibility declaration.",
        "requires_signature": True,
    },
    "external_package_identification": {
        "label": "External package identification",
        "category": "document",
        "reason": "Required for external package identification.",
        "requires_signature": False,
    },
    "mta_ttm": {
        "label": "MTA / TTM",
        "category": "document",
        "reason": "Required for material transfer, including OGM and non-OGM materials.",
        "requires_signature": True,
    },
    "cibio_authorization": {
        "label": "Autorização de transporte CIBio para OGM",
        "category": "document",
        "reason": "Required when the shipment contains OGM material.",
        "requires_signature": True,
    },
    "triple_packaging_checklist": {
        "label": "Triple packaging checklist",
        "category": "document",
        "reason": "Required for Risk Class 2 or NB2 shipments.",
        "requires_signature": False,
    },
    "traceability_report": {
        "label": "Legacy traceability record",
        "category": "document",
        "reason": "Internal traceability record for controlled biological shipments.",
        "requires_signature": False,
    },
}


LABELS = {
    "fragile": {
        "label": "Label: Fragile",
        "category": "label",
        "reason": "Recommended for biological sample package handling.",
    },
    "external_package_identification": {
        "label": "Label: external sender/recipient identification",
        "category": "label",
        "reason": "Required for package identification.",
    },
    "package_qr": {
        "label": "Shipment tracking QR code",
        "category": "label",
        "reason": "Internal package traceability.",
    },
    "biohazard": {
        "label": "Label: risco biológico",
        "category": "label",
        "reason": "Required for controlled biological material when applicable.",
    },
    "un3373": {
        "label": "Label UN 3373",
        "category": "label",
        "reason": "Required for Risk Class 2 or NB2 biological substances.",
    },
    "restricted_opening": {
        "label": "Aviso: abertura restrita ao recipient",
        "category": "label",
        "reason": "Required for controlled biological material packages.",
    },
}


CHECKLIST = {
    "review_route": {
        "label": "Sender and recipient data reviewed",
        "category": "data",
        "reason": "Route and responsible parties must be reviewed.",
    },
    "review_items": {
        "label": "Shipment items and quantities reviewed",
        "category": "data",
        "reason": "Shipment items and quantities must be reviewed.",
    },
    "review_classification": {
        "label": "Risk Class / NB classification reviewed",
        "category": "data",
        "reason": "Risk Class, biosafety level and OGM status must be reviewed.",
    },
    "documents_signed": {
        "label": "Required documents signed/uploaded",
        "category": "document",
        "reason": "Required signed documents must be uploaded.",
    },
    "documents_approved": {
        "label": "Required documents internally approved",
        "category": "document",
        "reason": "Required documents must pass internal review.",
    },
    "labels_printed": {
        "label": "Required labels printed",
        "category": "label",
        "reason": "Required labels must be printed before shipment.",
    },
    "triple_packaging": {
        "label": "Package tripla conferida",
        "category": "data",
        "reason": "Triple packaging must be checked for Risk Class 2 or NB2 shipments.",
    },
}


def _make_requirement(catalog, code, reason=None):
    data = catalog[code]

    return Requirement(
        code=code,
        label=data["label"],
        category=data["category"],
        reason=reason or data.get("reason", ""),
        requires_signature=bool(data.get("requires_signature", False)),
    )


def _add_requirement(target, seen, catalog, code, reason=None):
    if code in seen:
        return

    target.append(_make_requirement(catalog, code, reason=reason))
    seen.add(code)


def _value(obj, *names):
    for name in names:
        if obj is None:
            continue

        try:
            value = getattr(obj, name)
        except Exception:
            value = None

        if value not in [None, ""]:
            return value

    return ""


def _truthy(value):
    if isinstance(value, bool):
        return value

    raw = str(value or "").strip().lower()

    return raw in {"1", "true", "yes", "sim", "y", "s", "ogm"}


def _normalize_risk_class(value):
    raw = str(value or "").strip().lower()

    if not raw:
        return ""

    if "4" in raw:
        return "risk_class_4"
    if "3" in raw:
        return "risk_class_3"
    if "2" in raw:
        return "risk_class_2"
    if "1" in raw:
        return "risk_class_1"

    return raw


def _normalize_biosafety_level(value):
    raw = str(value or "").strip().lower()

    if not raw:
        return ""

    if "4" in raw:
        return "nb4"
    if "3" in raw:
        return "nb3"
    if "2" in raw:
        return "nb2"
    if "1" in raw:
        return "nb1"

    return raw


def _classification(shipment):
    return getattr(shipment, "classification", None)


def _items(shipment):
    try:
        return list(shipment.items.all())
    except Exception:
        return []


def _collect_text(shipment):
    parts = []

    for obj in [shipment, _classification(shipment), *_items(shipment)]:
        for name in [
            "material_type",
            "sample_type",
            "material_name",
            "description",
            "risk_class",
            "biosafety_level",
            "nb_level",
            "containment_level",
            "notes",
        ]:
            value = _value(obj, name)
            if value:
                parts.append(str(value))

    return " ".join(parts).lower()


def _is_ogm(shipment):
    cls = _classification(shipment)

    direct = _value(cls, "is_ogm", "ogm")
    if direct not in ["", None]:
        return _truthy(direct)

    text = _collect_text(shipment)

    return any(token in text for token in ["ogm", "gmo", "geneticamente modificado"])


def _risk_class(shipment):
    cls = _classification(shipment)

    value = _value(cls, "risk_class", "risk_group")

    if not value:
        for item in _items(shipment):
            value = _value(item, "risk_class", "risk_group")
            if value:
                break

    return _normalize_risk_class(value)


def _biosafety_level(shipment):
    cls = _classification(shipment)

    value = _value(cls, "biosafety_level", "nb_level", "containment_level")

    if not value:
        for item in _items(shipment):
            value = _value(item, "biosafety_level", "nb_level", "containment_level")
            if value:
                break

    return _normalize_biosafety_level(value)


def _is_risk_class_2_or_higher(risk_class):
    return risk_class in {"risk_class_2", "risk_class_3", "risk_class_4"}


def _is_nb2_or_higher(biosafety_level):
    return biosafety_level in {"nb2", "nb3", "nb4"}


def evaluate_shipment_requirements(shipment):
    risk_class = _risk_class(shipment)
    biosafety_level = _biosafety_level(shipment)
    is_ogm = _is_ogm(shipment)

    is_risk_class_2_or_higher = _is_risk_class_2_or_higher(risk_class)
    is_nb2_or_higher = _is_nb2_or_higher(biosafety_level)

    needs_un3373 = is_risk_class_2_or_higher or is_nb2_or_higher
    needs_controlled_biohazard_label = is_ogm or needs_un3373

    documents = []
    labels = []
    checklist = []

    seen_documents = set()
    seen_labels = set()
    seen_checklist = set()

    for code in [
        "content_declaration",
        "external_package_identification",
        "mta_ttm",
    ]:
        _add_requirement(documents, seen_documents, DOCUMENTS, code)

    for code in [
        "fragile",
        "external_package_identification",
        "package_qr",
    ]:
        _add_requirement(labels, seen_labels, LABELS, code)

    for code in [
        "review_route",
        "review_items",
        "review_classification",
        "documents_signed",
        "documents_approved",
        "labels_printed",
    ]:
        _add_requirement(checklist, seen_checklist, CHECKLIST, code)

    if is_ogm:
        _add_requirement(
            documents,
            seen_documents,
            DOCUMENTS,
            "cibio_authorization",
            reason="OGM shipment requires CIBio transport authorization.",
        )

    if needs_un3373:
        _add_requirement(
            documents,
            seen_documents,
            DOCUMENTS,
            "triple_packaging_checklist",
            reason="Risk Class 2 or NB2 shipment requires triple packaging checklist.",
        )
        _add_requirement(
            labels,
            seen_labels,
            LABELS,
            "un3373",
            reason="Risk Class 2 or NB2 shipment requires UN 3373 label.",
        )
        _add_requirement(checklist, seen_checklist, CHECKLIST, "triple_packaging")

    if needs_controlled_biohazard_label:
        _add_requirement(labels, seen_labels, LABELS, "biohazard")
        _add_requirement(labels, seen_labels, LABELS, "restricted_opening")

    summary = {
        "risk_class": risk_class,
        "biosafety_level": biosafety_level,
        "is_ogm": is_ogm,
        "is_risk_class_2_or_higher": is_risk_class_2_or_higher,
        "is_nb2_or_higher": is_nb2_or_higher,
        "needs_un3373": needs_un3373,
        "needs_controlled_biohazard_label": needs_controlled_biohazard_label,
    }

    return {
        "summary": summary,
        "documents": documents,
        "labels": labels,
        "checklist": checklist,
    }
