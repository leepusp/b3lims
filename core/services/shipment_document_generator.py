from html import escape

from django.utils import timezone

from core.services.cqb_registry import format_institution_cqb


REGULATORY_COMPLIANCE_TEXT = """This shipment is in full compliance with applicable transport, biosafety, and institutional rules, including ANTT Resolution No. 5.998/2022 when applicable, CTNBio Normative Resolution No. 26/2020 when applicable, and any additional institutional requirements for biological material handling and shipment."""

PACKAGING_STATEMENT_TEXT = """The material was packed using packaging appropriate to the shipment classification, including a sealed primary container, resistant secondary packaging, absorbent material when required, and rigid external packaging when applicable."""

TRANSPORT_CONDITION_STATEMENT_TEXT = """Appropriate transport and conservation conditions were adopted to preserve sample integrity and shipment safety throughout handling and transport."""

RESPONSIBILITY_STATEMENT_TEXT = """The sender declares responsibility for the accuracy of the information provided, the correct classification of the material, and compliance with applicable documentation, packaging, labeling, and transport requirements."""

TRACEABILITY_STATEMENT_TEXT = """The shipment will be internally registered for traceability, including origin, destination, responsible person, material identification, transport condition, dispatch date, and receipt date."""




def _normalize_risk_class_label(value):
    raw = str(value or "").strip()
    low = raw.lower()

    if not raw:
        return ""

    if "4" in low:
        return "Risk Class 4"
    if "3" in low:
        return "Risk Class 3"
    if "2" in low:
        return "Risk Class 2"
    if "1" in low:
        return "Risk Class 1"

    return raw


def _normalize_biosafety_level_label(value):
    raw = str(value or "").strip()
    low = raw.lower()

    if not raw:
        return ""

    if "4" in low:
        return "NB4"
    if "3" in low:
        return "NB3"
    if "2" in low:
        return "NB2"
    if "1" in low:
        return "NB1"

    return raw



def _shipment_declaration(shipment):
    try:
        return shipment.declaration
    except Exception:
        return None


def _join_contact(*values):
    return " / ".join(
        str(value).strip()
        for value in values
        if str(value or "").strip()
    )


def _format_document_date(value):
    if not value:
        return ""

    if hasattr(value, "hour") and timezone.is_aware(value):
        value = timezone.localtime(value)

    try:
        return value.strftime("%d/%m/%Y")
    except Exception:
        return str(value)



def render_document_html(document, shipment, schema, values):
    title = schema["title"]

    section_html = []

    for section in schema.get("sections", []):
        rows = []

        for name, label, _field_type in section.get("fields", []):
            value = values.get(name, "")

            if isinstance(value, bool):
                value = "Yes" if value else "No"

            rows.append(
                "<tr>"
                f"<th>{escape(str(label))}</th>"
                f"<td>{escape(str(value or ''))}</td>"
                "</tr>"
            )

        section_html.append(
            f"<h2>{escape(section.get('title', 'Section'))}</h2>"
            "<table>"
            + "".join(rows)
            + "</table>"
        )

    item_rows = []

    for item in shipment.items.all():
        item_rows.append(
            "<tr>"
            f"<td>{escape(str(item.imported_sample_id or ''))}</td>"
            f"<td>{escape(str(item.material_name or ''))}</td>"
            f"<td>{escape(str(item.sample_type or ''))}</td>"
            f"<td>{escape(str(item.quantity or ''))} {escape(str(item.quantity_unit or ''))}</td>"
            "</tr>"
        )

    if not item_rows:
        item_rows.append("<tr><td colspan='4'>No items registered.</td></tr>")

    generated_at = timezone.now().strftime("%d/%m/%Y %H:%M")

    signature_name = str(
        values.get("signer_name")
        or values.get("sender_name")
        or ""
    )
    signature_place = str(
        values.get("declaration_place")
        or ""
    )
    signature_date = str(
        values.get("declaration_date")
        or ""
    )
    signature_document = str(
        values.get("signer_document")
        or values.get("sender_document")
        or ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{
    font-family: Arial, sans-serif;
    margin: 32px;
    font-size: 12pt;
    color: #111;
}}
.no-print {{
    margin-bottom: 18px;
    padding: 10px;
    border: 1px solid #ccc;
    background: #f7f7f7;
}}
h1 {{
    text-align: center;
    font-size: 18pt;
    margin-bottom: 6px;
}}
h2 {{
    margin-top: 24px;
    font-size: 13pt;
    border-bottom: 1px solid #ccc;
    padding-bottom: 4px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 10px;
}}
th, td {{
    border: 1px solid #999;
    padding: 7px;
    vertical-align: top;
}}
th {{
    width: 34%;
    background: #f2f2f2;
    text-align: left;
}}
.signature {{
    margin-top: 60px;
}}
.small {{
    color: #555;
    font-size: 10pt;
}}
@media print {{
    .no-print {{ display: none; }}
    body {{ margin: 20mm; }}
}}
</style>
</head>
<body>
<div class="no-print">
    <button onclick="window.print()">Print / save as PDF</button>
    <span class="small">Use this option to generate the PDF and sign it outside the platform.</span>
</div>

<h1>{escape(title)}</h1>
<p class="small">
    Shipment: {escape(str(shipment.shipment_code))} ·
    Document: {escape(str(document.document_type))} ·
    Generated at: {escape(generated_at)}
</p>

{''.join(section_html)}

<h2>Shipment items</h2>
<table>
<thead>
<tr>
<th>Sample ID</th>
<th>Material</th>
<th>Type</th>
<th>Quantity</th>
</tr>
</thead>
<tbody>
{''.join(item_rows)}
</tbody>
</table>

<div class="signature">
    <p>I certify that the information provided in this declaration is true and correct.</p>
    <p>__________________________________________</p>
    <p>Signature</p>
    <p><strong>Name:</strong> {escape(signature_name)}</p>
    <p><strong>Place:</strong> {escape(signature_place)}</p>
    <p><strong>Date:</strong> {escape(signature_date)}</p>
    <p><strong>Document / ID:</strong> {escape(signature_document)}</p>
</div>

</body>
</html>"""


def get_initial_values_from_shipment(shipment, document_type):
    classification = getattr(shipment, "classification", None)
    declaration = _shipment_declaration(shipment)
    first_item = shipment.items.first()

    sender_name = str(
        getattr(declaration, "sender_full_name", "")
        or getattr(shipment, "sender_responsible_name", "")
        or ""
    )

    sender_address = str(
        getattr(declaration, "sender_address", "")
        or getattr(shipment, "sender_address", "")
        or ""
    )

    sender_contact = str(
        getattr(declaration, "sender_phone_email", "")
        or _join_contact(
            getattr(shipment, "sender_phone", ""),
            getattr(shipment, "sender_email", ""),
        )
    )

    recipient_name = str(
        getattr(declaration, "recipient_name", "")
        or getattr(shipment, "recipient_responsible_name", "")
        or ""
    )

    recipient_institution = str(
        getattr(declaration, "recipient_institution", "")
        or getattr(shipment, "recipient_institution", "")
        or getattr(
            getattr(shipment, "destination_biobank", None),
            "name",
            "",
        )
        or ""
    )

    recipient_address = str(
        getattr(declaration, "recipient_address", "")
        or getattr(shipment, "recipient_address", "")
        or ""
    )

    recipient_contact = str(
        getattr(declaration, "recipient_phone_email", "")
        or _join_contact(
            getattr(shipment, "recipient_phone", ""),
            getattr(shipment, "recipient_email", ""),
        )
    )

    declaration_place = str(
        getattr(declaration, "declaration_place", "")
        or ""
    )

    declaration_date = (
        _format_document_date(
            getattr(declaration, "submitted_at", None)
        )
        or timezone.localdate().strftime("%d/%m/%Y")
    )

    signer_name = str(
        getattr(declaration, "signer_name", "")
        or sender_name
    )

    signer_document = str(
        getattr(declaration, "signer_document", "")
        or getattr(declaration, "sender_document", "")
        or ""
    )

    sender_institution = str(
        getattr(shipment, "sender_institution", "")
        or getattr(declaration, "sender_institution", "")
        or getattr(
            getattr(shipment, "origin_biobank", None),
            "name",
            "",
        )
        or ""
    )

    material_type = str(
        getattr(declaration, "material_type", "")
        or (
            getattr(classification, "material_type", "")
            if classification
            else ""
        )
    )

    is_ogm = (
        getattr(declaration, "is_ogm", None)
        if declaration is not None
        else None
    )

    if is_ogm is None:
        is_ogm = getattr(classification, "is_ogm", False)

    values = {
        "sender_name": sender_name,
        "sender_institution": format_institution_cqb(
            sender_institution,
            getattr(shipment, "sender_cqb_code", "") or "",
        ),
        "sender_lab_cqb": str(
            getattr(shipment, "sender_group_researcher", "") or ""
        ),
        "sender_address": sender_address,
        "sender_contact": sender_contact,
        "sender_document": signer_document,

        "recipient_name": recipient_name,
        "recipient_institution": recipient_institution,
        "recipient_lab_cqb": "",
        "recipient_address": recipient_address,
        "recipient_contact": recipient_contact,

        "material_type": material_type,
        "risk_class": _normalize_risk_class_label(
            getattr(declaration, "risk_class", "")
            or (
                getattr(classification, "risk_class", "")
                if classification
                else ""
            )
        ),
        "biosafety_level": _normalize_biosafety_level_label(
            getattr(declaration, "biosafety_level", "")
            or (
                getattr(classification, "biosafety_level", "")
                if classification
                else ""
            )
            or (
                getattr(classification, "nb_level", "")
                if classification
                else ""
            )
        ),
        "is_ogm": "Yes" if is_ogm else "No",

        "material_description": str(
            getattr(declaration, "content_description", "")
            or getattr(declaration, "additional_description", "")
            or ""
        ),
        "quantity_volume": str(
            getattr(declaration, "quantity_volume", "")
            or ""
        ),
        "purpose": str(
            getattr(declaration, "purpose", "")
            or ""
        ),
        "transport_conditions": str(
            getattr(declaration, "transport_conditions", "")
            or getattr(shipment, "temperature_condition", "")
            or ""
        ),
        "transport_method": str(
            getattr(shipment, "transport_method", "") or ""
        ),

        "shipment_code": str(
            getattr(shipment, "shipment_code", "") or ""
        ),
        "dispatch_date": _format_document_date(
            getattr(shipment, "dispatched_at", None)
            or getattr(shipment, "expected_dispatch_date", None)
        ),
        "expected_arrival": _format_document_date(
            getattr(shipment, "expected_arrival_date", None)
        ),
        "carrier_name": str(
            getattr(shipment, "carrier_name", "") or ""
        ),
        "tracking_code": str(
            getattr(shipment, "tracking_code", "") or ""
        ),

        "regulatory_compliance": REGULATORY_COMPLIANCE_TEXT,
        "packaging_statement": PACKAGING_STATEMENT_TEXT,
        "transport_condition_statement": TRANSPORT_CONDITION_STATEMENT_TEXT,
        "responsibility_statement": RESPONSIBILITY_STATEMENT_TEXT,
        "traceability_statement": TRACEABILITY_STATEMENT_TEXT,

        "declaration_place": declaration_place,
        "declaration_date": declaration_date,
        "signer_name": signer_name,
        "signer_document": signer_document,

        # Compatibility values for legacy schemas.
        "local_date": ", ".join(
            value
            for value in [
                declaration_place,
                declaration_date,
            ]
            if value
        ),
        "notes": str(getattr(shipment, "notes", "") or ""),
    }

    if first_item:
        if not values["material_description"]:
            values["material_description"] = str(
                first_item.material_name or ""
            )

        if not values["material_type"]:
            values["material_type"] = str(
                first_item.sample_type or ""
            )

        if not values["quantity_volume"]:
            values["quantity_volume"] = (
                f"{first_item.quantity or ''} "
                f"{first_item.quantity_unit or ''}"
            ).strip()

        values.update({
            "organism_name": str(first_item.material_name or ""),
            "container_quantity": str(
                getattr(first_item, "container_count", "") or ""
            ),
            "container_type": str(
                getattr(first_item, "container_type", "") or ""
            ),
            "storage_temperature": str(
                getattr(first_item, "storage_condition", "") or ""
            ),
        })

    return values

