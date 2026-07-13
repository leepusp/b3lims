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
    <p>Name: ____________________________________</p>
    <p>Date: ____/____/________</p>
</div>

</body>
</html>"""


def get_initial_values_from_shipment(shipment, document_type):
    classification = getattr(shipment, "classification", None)
    first_item = shipment.items.first()

    values = {
        "sender_institution": format_institution_cqb(
            getattr(shipment, "sender_institution", "")
            or getattr(getattr(shipment, "origin_biobank", None), "name", "")
            or "",
            getattr(shipment, "sender_cqb_code", "") or "",
        ),
        "sender_lab_cqb": str(
            getattr(shipment, "sender_group_researcher", "") or ""
        ),
        "recipient_institution": str(
            getattr(shipment, "recipient_institution", "")
            or getattr(getattr(shipment, "destination_biobank", None), "name", "")
            or ""
        ),
        "material_type": str(getattr(classification, "material_type", "") if classification else ""),
        "risk_class": _normalize_risk_class_label(getattr(classification, "risk_class", "") if classification else ""),
        "is_ogm": "Yes" if getattr(classification, "is_ogm", False) else "No",
        "biosafety_level": _normalize_biosafety_level_label(
            getattr(classification, "biosafety_level", "")
            or getattr(classification, "nb_level", "")
            or getattr(classification, "containment_level", "")
        ),
        "transport_conditions": str(getattr(shipment, "temperature_condition", "") or ""),
        "transport_method": str(getattr(shipment, "transport_method", "") or ""),
        "carrier_name": str(getattr(shipment, "carrier_name", "") or ""),
        "expected_arrival": str(getattr(shipment, "expected_arrival_date", "") or ""),
        "regulatory_compliance": REGULATORY_COMPLIANCE_TEXT,
        "packaging_statement": PACKAGING_STATEMENT_TEXT,
        "transport_condition_statement": TRANSPORT_CONDITION_STATEMENT_TEXT,
        "responsibility_statement": RESPONSIBILITY_STATEMENT_TEXT,
        "traceability_statement": TRACEABILITY_STATEMENT_TEXT,
        "shipment_code": str(getattr(shipment, "shipment_code", "") or ""),
    }

    if first_item:
        values.update({
            "material_description": str(first_item.material_name or ""),
            "material_type": values.get("material_type") or str(first_item.sample_type or ""),
            "quantity_volume": f"{first_item.quantity or ''} {first_item.quantity_unit or ''}".strip(),
            "organism_name": str(first_item.material_name or ""),
            "container_quantity": str(getattr(first_item, "container_count", "") or ""),
            "container_type": str(getattr(first_item, "container_type", "") or ""),
            "storage_temperature": str(getattr(first_item, "storage_condition", "") or ""),
        })

    return values
