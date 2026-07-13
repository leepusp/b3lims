from html import escape

from django.utils import timezone

from core.services.cqb_registry import (
    find_cqb_by_institution,
    format_institution_cqb,
)


REGULATORY_COMPLIANCE_TEXT = """This shipment is in full compliance with applicable transport, biosafety, and institutional rules, including ANTT Resolution No. 5.998/2022 when applicable, CTNBio Normative Resolution No. 26/2020 when applicable, and any additional institutional requirements for biological material handling and shipment."""

PACKAGING_STATEMENT_TEXT = """The material was packed using packaging appropriate to the shipment classification, including a sealed primary container, resistant secondary packaging, absorbent material when required, and rigid external packaging when applicable."""

TRANSPORT_CONDITION_STATEMENT_TEXT = """Appropriate transport and conservation conditions were adopted to preserve sample integrity and shipment safety throughout handling and transport."""

RESPONSIBILITY_STATEMENT_TEXT = """The sender declares responsibility for the accuracy of the information provided, the correct classification of the material, and compliance with applicable documentation, packaging, labeling, and transport requirements."""

TRACEABILITY_STATEMENT_TEXT = """The shipment will be internally registered for traceability, including origin, destination, responsible person, material identification, transport condition, dispatch date, and receipt date."""

CIBIO_NORMATIVE_REFERENCE_TEXT = (
    "CTNBio Normative Resolution No. 26 of 22 May 2020, "
    "and any complementary institutional biosafety requirements."
)

CIBIO_PACKAGING_DESCRIPTION_TEXT = (
    "The GMO material must be transported in a sealed and leakproof "
    "primary container, resistant secondary packaging, sufficient "
    "absorbent material when applicable, and rigid outer packaging. "
    "The outer package must identify the sender and recipient and must "
    "display all required biohazard, fragile and restricted-access notices."
)

CIBIO_AUTHORIZATION_STATEMENT_TEXT = (
    "This document records the awareness and authorization of the "
    "CIBio committees involved in the transport and transfer of the "
    "GMO or AnGM described in this request."
)

CIBIO_INSTITUTION_PROFILES = {
    "IQ-USP": {
        "legal_name": (
            "Instituto de Química / Universidade de São Paulo — IQ-USP"
        ),
        "address": (
            "Av. Prof. Lineu Prestes, 748, CEP 05508-000, "
            "Cidade Universitária, Butantã, São Paulo, SP"
        ),
        "cibio_name": (
            "CIBio IQ-USP — Instituto de Química "
            "da Universidade de São Paulo"
        ),
        "cibio_phone": "(11) 3091-3811",
        "cibio_email": "cibio@iq.usp.br",
        "cqb": "0029/97",
    },
}




def _cibio_profile(institution):
    record = find_cqb_by_institution(institution)

    canonical_name = (
        record["institution"]
        if record
        else str(institution or "").strip()
    )

    profile = dict(
        CIBIO_INSTITUTION_PROFILES.get(
            canonical_name,
            {},
        )
    )

    profile.setdefault(
        "legal_name",
        canonical_name,
    )
    profile.setdefault(
        "address",
        "",
    )
    profile.setdefault(
        "cibio_name",
        f"CIBio — {canonical_name}" if canonical_name else "",
    )
    profile.setdefault(
        "cibio_phone",
        "",
    )
    profile.setdefault(
        "cibio_email",
        "",
    )
    profile.setdefault(
        "cqb",
        record["cqb"] if record else "",
    )

    return profile


def _cibio_transport_mode(value):
    raw = str(value or "").strip()
    low = raw.lower()

    if not raw:
        return ""

    if "personal" in low:
        return "Personal delivery"

    if "postal" in low or "correio" in low:
        return "Postal service"

    if (
        "carrier" in low
        or "transportadora" in low
        or "courier" in low
    ):
        return "Carrier"

    return "Other"


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

    if document.document_type == "cibio_authorization":
        sender_cibio_president_name = str(
            values.get("sender_cibio_president_name")
            or ""
        )
        sender_cibio_president_title = str(
            values.get("sender_cibio_president_title")
            or ""
        )
        recipient_cibio_president_name = str(
            values.get("recipient_cibio_president_name")
            or ""
        )
        recipient_cibio_president_title = str(
            values.get("recipient_cibio_president_title")
            or ""
        )

        sender_institution_label = str(
            values.get("sender_institution")
            or ""
        )
        recipient_institution_label = str(
            values.get("recipient_institution")
            or ""
        )

        sender_cqb_code = str(
            values.get("sender_cqb_code")
            or ""
        )
        recipient_cqb_code = str(
            values.get("recipient_cqb_code")
            or ""
        )

        signature_html = f"""
        <div class="cibio-authorization-signatures">
            <p class="cibio-signature-meta">
                <strong>Place:</strong>
                {escape(signature_place)}
                &nbsp;&nbsp;
                <strong>Date:</strong>
                {escape(signature_date)}
            </p>

            <div class="cibio-requester-signature">
                <div class="signature-line"></div>

                <strong>{escape(signature_name)}</strong><br>
                Requesting Researcher<br>
                {escape(sender_institution_label)}<br>
                Document / ID: {escape(signature_document)}
            </div>

            <div class="cibio-approval-grid">
                <div class="cibio-signature-box">
                    <strong>
                        Authorized — Sender Institution
                    </strong>

                    <div class="signature-line"></div>

                    <strong>
                        {escape(sender_cibio_president_name)}
                    </strong><br>

                    {escape(sender_cibio_president_title)}<br>
                    {escape(sender_institution_label)}<br>
                    CQB: {escape(sender_cqb_code)}
                </div>

                <div class="cibio-signature-box">
                    <strong>
                        Authorized — Recipient Institution
                    </strong>

                    <div class="signature-line"></div>

                    <strong>
                        {escape(recipient_cibio_president_name)}
                    </strong><br>

                    {escape(recipient_cibio_president_title)}<br>
                    {escape(recipient_institution_label)}<br>
                    CQB: {escape(recipient_cqb_code)}
                </div>
            </div>
        </div>
        """
    else:
        signature_html = f"""
        <div class="signature">
            <p>
                I certify that the information provided in this
                declaration is true and correct.
            </p>

            <p>__________________________________________</p>
            <p>Signature</p>

            <p>
                <strong>Name:</strong>
                {escape(signature_name)}
            </p>

            <p>
                <strong>Place:</strong>
                {escape(signature_place)}
            </p>

            <p>
                <strong>Date:</strong>
                {escape(signature_date)}
            </p>

            <p>
                <strong>Document / ID:</strong>
                {escape(signature_document)}
            </p>
        </div>
        """

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

.cibio-authorization-signatures {{
    margin-top: 55px;
    page-break-inside: avoid;
}}

.cibio-signature-meta {{
    margin-bottom: 45px;
    text-align: right;
}}

.cibio-requester-signature {{
    max-width: 480px;
    margin: 0 auto 65px;
    text-align: center;
    line-height: 1.45;
}}

.cibio-approval-grid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 45px;
}}

.cibio-signature-box {{
    min-height: 150px;
    text-align: center;
    line-height: 1.45;
}}

.signature-line {{
    margin: 55px 0 10px;
    border-top: 1px solid #111;
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

{signature_html}
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

    sender_cibio_profile = _cibio_profile(
        sender_institution
    )
    recipient_cibio_profile = _cibio_profile(
        recipient_institution
    )

    transport_method = str(
        getattr(shipment, "transport_method", "") or ""
    )
    transport_mode = _cibio_transport_mode(
        transport_method
    )

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

        # CIBio sender institution and researcher.
        "sender_legal_name": (
            sender_cibio_profile.get("legal_name")
            or sender_institution
        ),
        "sender_cibio_name": (
            sender_cibio_profile.get("cibio_name")
            or ""
        ),
        "sender_cibio_phone": (
            sender_cibio_profile.get("cibio_phone")
            or ""
        ),
        "sender_cibio_email": (
            sender_cibio_profile.get("cibio_email")
            or ""
        ),
        "sender_cqb_code": str(
            getattr(shipment, "sender_cqb_code", "")
            or sender_cibio_profile.get("cqb")
            or ""
        ),
        "sender_researcher_address": sender_address,
        "sender_phone": str(
            getattr(shipment, "sender_phone", "") or ""
        ),
        "sender_email": str(
            getattr(shipment, "sender_email", "") or ""
        ),
        "ogm_project_title": "",
        "sender_cibio_project_protocol": "",

        # CIBio recipient institution and researcher.
        "recipient_legal_name": (
            recipient_cibio_profile.get("legal_name")
            or recipient_institution
        ),
        "recipient_cibio_name": (
            recipient_cibio_profile.get("cibio_name")
            or ""
        ),
        "recipient_cibio_phone": (
            recipient_cibio_profile.get("cibio_phone")
            or ""
        ),
        "recipient_cibio_email": (
            recipient_cibio_profile.get("cibio_email")
            or ""
        ),
        "recipient_cqb_code": (
            recipient_cibio_profile.get("cqb")
            or ""
        ),
        "recipient_researcher_address": recipient_address,
        "recipient_phone": str(
            getattr(shipment, "recipient_phone", "") or ""
        ),
        "recipient_email": str(
            getattr(shipment, "recipient_email", "") or ""
        ),
        "request_purpose": str(
            getattr(declaration, "purpose", "") or ""
        ),

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
        "transport_method": transport_method,

        # CIBio transport and packaging.
        "transport_mode": transport_mode,
        "transport_mode_other": (
            transport_method
            if transport_mode == "Other"
            else ""
        ),
        "transport_company": str(
            getattr(shipment, "carrier_name", "") or ""
        ),
        "packaging_description": (
            CIBIO_PACKAGING_DESCRIPTION_TEXT
        ),
        "carrier_incident_acknowledged": False,
        "restricted_access_label_confirmed": bool(
            getattr(
                declaration,
                "confirms_sender_recipient_identification",
                False,
            )
        ),
        "animal_gmo": "No",
        "animal_transport_procedures": "",

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

        # CIBio authorization and signatures.
        "normative_reference": (
            CIBIO_NORMATIVE_REFERENCE_TEXT
        ),
        "authorization_statement": (
            CIBIO_AUTHORIZATION_STATEMENT_TEXT
        ),
        "sender_cibio_president_name": "",
        "sender_cibio_president_title": "",
        "recipient_cibio_president_name": "",
        "recipient_cibio_president_title": "",

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

            # First GMO entry is prefilled from the first shipment item.
            "ogm_1_common_name": str(
                first_item.material_name or ""
            ),
            "ogm_1_scientific_name": "",
            "ogm_1_gene_source_species": "",
            "ogm_1_modified_sequences": "",
            "ogm_1_vector": "",
            "ogm_1_gene_functions": "",
            "ogm_1_identification_method": "",
            "ogm_1_origin_institution": sender_institution,
            "ogm_1_risk_class": values.get(
                "risk_class",
                "",
            ),
            "ogm_1_quantity": values.get(
                "quantity_volume",
                "",
            ),
        })

    return values

