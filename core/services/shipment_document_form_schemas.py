from core.services.cqb_registry import get_institution_cqb_select_options


RISK_CLASS_OPTIONS = [
    "",
    "Risk Class 1",
    "Risk Class 2",
    "Risk Class 3",
    "Risk Class 4",
]

BIOSAFETY_LEVEL_OPTIONS = [
    "",
    "NB1",
    "NB2",
    "NB3",
    "NB4",
]

YES_NO_OPTIONS = [
    "",
    "Yes",
    "No",
]

TRANSPORT_MODE_OPTIONS = [
    "",
    "Personal delivery",
    "Postal service",
    "Carrier",
    "Other",
]

INSTITUTION_CQB_OPTIONS = [""] + get_institution_cqb_select_options()


def select(options):
    return "select:" + "|".join(options)


def gmo_material_fields(prefix):
    return [
        (
            f"{prefix}_common_name",
            "Common Name of the GMO",
            "text",
        ),
        (
            f"{prefix}_scientific_name",
            "Scientific Name of the GMO",
            "text",
        ),
        (
            f"{prefix}_gene_source_species",
            "Species of Origin of the Gene",
            "text",
        ),
        (
            f"{prefix}_modified_sequences",
            "Introduced or Modified Gene / Sequences",
            "textarea",
        ),
        (
            f"{prefix}_vector",
            "Vector",
            "text",
        ),
        (
            f"{prefix}_gene_functions",
            "Gene Functions",
            "textarea",
        ),
        (
            f"{prefix}_identification_method",
            "Method Used to Identify the GMO",
            "textarea",
        ),
        (
            f"{prefix}_origin_institution",
            "GMO Origin / Institution",
            "text",
        ),
        (
            f"{prefix}_risk_class",
            "GMO Risk Class",
            select(RISK_CLASS_OPTIONS),
        ),
        (
            f"{prefix}_quantity",
            "GMO Quantity",
            "text",
        ),
    ]


DOCUMENT_FORM_SCHEMAS = {
    "content_declaration": {
        "title": "Content declaration and traceability",
        "description": "Consolidated content declaration, shipment traceability, regulatory compliance, and sender responsibility record.",
        "sections": [
            {
                "title": "Sender",
                "fields": [
                    ("sender_name", "Sender Responsible Person", "text"),
                    ("sender_institution", "Sender Institution / CQB", select(INSTITUTION_CQB_OPTIONS)),
                    ("sender_lab_cqb", "Sender Group / Laboratory / Researcher", "text"),
                    ("sender_address", "Sender Address", "textarea"),
                    ("sender_contact", "Sender Contact", "text"),
                ],
            },
            {
                "title": "Recipient",
                "fields": [
                    ("recipient_name", "Recipient Responsible Person", "text"),
                    ("recipient_institution", "Recipient Institution", "text"),
                    ("recipient_lab_cqb", "Recipient Group / Laboratory / Researcher", "text"),
                    ("recipient_address", "Recipient Address", "textarea"),
                    ("recipient_contact", "Recipient Contact", "text"),
                ],
            },
            {
                "title": "Material Classification",
                "fields": [
                    ("material_description", "Material Description", "textarea"),
                    ("material_type", "Material Type", "text"),
                    ("risk_class", "Risk Class", select(RISK_CLASS_OPTIONS)),
                    ("biosafety_level", "Biosafety Level", select(BIOSAFETY_LEVEL_OPTIONS)),
                    ("is_ogm", "GMO", select(YES_NO_OPTIONS)),
                    ("quantity_volume", "Quantity / Volume", "text"),
                    ("transport_conditions", "Transport Conditions", "textarea"),
                    ("purpose", "Purpose", "textarea"),
                ],
            },
            {
                "title": "Traceability",
                "fields": [
                    ("shipment_code", "Shipment Code", "text"),
                    ("dispatch_date", "Dispatch Date", "text"),
                    ("expected_arrival", "Expected Arrival Date", "text"),
                    ("carrier_name", "Carrier", "text"),
                    ("tracking_code", "Tracking Code", "text"),
                    ("traceability_statement", "Traceability Statement", "textarea"),
                ],
            },
            {
                "title": "Compliance and Responsibility",
                "fields": [
                    ("regulatory_compliance", "Compliance with Applicable Regulations", "textarea"),
                    ("packaging_statement", "Packaging", "textarea"),
                    ("transport_condition_statement", "Transport Conditions", "textarea"),
                    ("responsibility_statement", "Responsibility", "textarea"),
                    ("declaration_place", "Place", "text"),
                    ("declaration_date", "Date", "text"),
                    ("signer_name", "Signatory Name", "text"),
                    ("signer_document", "Signatory Document / ID", "text"),
                ],
            },
        ],
    },
    "sender_declaration": {
        "title": "Legacy ANTT sender declaration",
        "description": "Legacy document retained only for historical shipment records.",
        "sections": [
            {
                "title": "Sender",
                "fields": [
                    ("sender_name", "Sender Responsible Person", "text"),
                    ("sender_institution", "Sender Institution / CQB", select(INSTITUTION_CQB_OPTIONS)),
                    ("sender_lab_cqb", "Sender Group / Laboratory / Researcher", "text"),
                    ("sender_address", "Sender Address", "textarea"),
                    ("sender_contact", "Sender Contact", "text"),
                ],
            },
            {
                "title": "Shipment identification",
                "fields": [
                    ("material_description", "Content description", "textarea"),
                    ("risk_class", "Risk Class", select(RISK_CLASS_OPTIONS)),
                    ("biosafety_level", "Biosafety Level", select(BIOSAFETY_LEVEL_OPTIONS)),
                    ("is_ogm", "GMO", select(YES_NO_OPTIONS)),
                    ("quantity_volume", "Quantity / Volume", "text"),
                    ("transport_conditions", "Transport Conditions", "textarea"),
                ],
            },
            {
                "title": "Required Declarations",
                "fields": [
                    ("regulatory_compliance", "Compliance with Applicable Regulations", "textarea"),
                    ("packaging_statement", "Packaging", "textarea"),
                    ("transport_condition_statement", "Transport Conditions", "textarea"),
                    ("responsibility_statement", "Responsibility", "textarea"),
                    ("declaration_place", "Place", "text"),
                    ("declaration_date", "Date", "text"),
                    ("signer_name", "Signatory Name", "text"),
                    ("signer_document", "Signatory Document / ID", "text"),
                ],
            },
        ],
    },
    "external_package_identification": {
        "title": "External package identification",
        "description": "Sender and recipient identification for external package labeling.",
        "sections": [
            {
                "title": "Sender",
                "fields": [
                    ("sender_name", "Sender Responsible Person", "text"),
                    ("sender_institution", "Sender Institution / CQB", select(INSTITUTION_CQB_OPTIONS)),
                    ("sender_lab_cqb", "Sender Group / Laboratory / Researcher", "text"),
                    ("sender_address", "Address", "textarea"),
                    ("sender_contact", "Phone / Email", "text"),
                ],
            },
            {
                "title": "Recipient",
                "fields": [
                    ("recipient_name", "Recipient Responsible Person", "text"),
                    ("recipient_institution", "Recipient Institution", "text"),
                    ("recipient_lab_cqb", "Recipient Group / Laboratory / Researcher", "text"),
                    ("recipient_address", "Address", "textarea"),
                    ("recipient_contact", "Phone / Email", "text"),
                ],
            },
            {
                "title": "External Classification",
                "fields": [
                    ("risk_class", "Risk Class", select(RISK_CLASS_OPTIONS)),
                    ("biosafety_level", "Biosafety Level", select(BIOSAFETY_LEVEL_OPTIONS)),
                    ("is_ogm", "GMO", select(YES_NO_OPTIONS)),
                    ("transport_conditions", "Transport Conditions", "text"),
                ],
            },
        ],
    },
    "mta_ttm": {
        "title": "MTA / TTM",
        "description": "Material Transfer Agreement / Material Transfer Term for GMO and non-GMO shipments, Risk Class 1/2 and NB1/NB2.",
        "sections": [
            {
                "title": "Sender Party",
                "fields": [
                    ("sender_name", "Sender Responsible Person", "text"),
                    ("sender_institution", "Sender Institution / CQB", select(INSTITUTION_CQB_OPTIONS)),
                    ("sender_lab_cqb", "Sender Group / Laboratory / Researcher", "text"),
                    ("sender_address", "Address", "textarea"),
                    ("sender_contact", "Contato", "text"),
                ],
            },
            {
                "title": "Recipient Party",
                "fields": [
                    ("recipient_name", "Recipient Responsible Person", "text"),
                    ("recipient_institution", "Recipient Institution", "text"),
                    ("recipient_lab_cqb", "Recipient Group / Laboratory / Researcher", "text"),
                    ("recipient_address", "Address", "textarea"),
                    ("recipient_contact", "Contato", "text"),
                ],
            },
            {
                "title": "Transferred Material",
                "fields": [
                    ("material_description", "Material Description", "textarea"),
                    ("material_type", "Material Type", "text"),
                    ("risk_class", "Risk Class", select(RISK_CLASS_OPTIONS)),
                    ("biosafety_level", "Biosafety Level", select(BIOSAFETY_LEVEL_OPTIONS)),
                    ("is_ogm", "GMO", select(YES_NO_OPTIONS)),
                    ("quantity_volume", "Quantity / Volume", "text"),
                    ("purpose", "Transfer Purpose", "textarea"),
                ],
            },
            {
                "title": "Conditions and Responsibility",
                "fields": [
                    ("transport_conditions", "Transport Conditions", "textarea"),
                    ("regulatory_compliance", "Compliance with Applicable Regulations", "textarea"),
                    ("responsibility_statement", "Responsibility", "textarea"),
                    ("declaration_place", "Place", "text"),
                    ("declaration_date", "Date", "text"),
                    ("signer_name", "Signatory Name", "text"),
                    ("signer_document", "Signatory Document / ID", "text"),
                ],
            },
        ],
    },
    "cibio_authorization": {
        "title": "CIBio GMO Transport Authorization Request",
        "description": (
            "Internal authorization form for GMO transport. "
            "The form is based on the institutional CIBio transport "
            "authorization structure and must be signed by the requester "
            "and the CIBio representatives of the institutions involved."
        ),
        "sections": [
            {
                "title": "Sender Institution and CIBio",
                "fields": [
                    (
                        "sender_legal_name",
                        "Sender Legal Name",
                        "text",
                    ),
                    (
                        "sender_institution",
                        "Sender Institution / CQB",
                        select(INSTITUTION_CQB_OPTIONS),
                    ),
                    (
                        "sender_address",
                        "Sender Institution Address",
                        "textarea",
                    ),
                    (
                        "sender_cibio_name",
                        "Sender CIBio",
                        "text",
                    ),
                    (
                        "sender_cibio_phone",
                        "Sender CIBio Phone",
                        "text",
                    ),
                    (
                        "sender_cibio_email",
                        "Sender CIBio Email",
                        "text",
                    ),
                    (
                        "sender_cqb_code",
                        "Sender CQB Number",
                        "text",
                    ),
                ],
            },
            {
                "title": "Responsible Researcher — Sender",
                "fields": [
                    (
                        "sender_name",
                        "Responsible Researcher",
                        "text",
                    ),
                    (
                        "sender_researcher_address",
                        "Researcher Institutional Address",
                        "textarea",
                    ),
                    (
                        "sender_phone",
                        "Researcher Phone",
                        "text",
                    ),
                    (
                        "sender_email",
                        "Researcher Email",
                        "text",
                    ),
                    (
                        "ogm_project_title",
                        "Title of the Project Associated with the GMO",
                        "textarea",
                    ),
                    (
                        "sender_cibio_project_protocol",
                        "Sender CIBio Project Approval Protocol",
                        "text",
                    ),
                ],
            },
            {
                "title": "Recipient Institution and CIBio",
                "fields": [
                    (
                        "recipient_legal_name",
                        "Recipient Legal Name",
                        "text",
                    ),
                    (
                        "recipient_institution",
                        "Recipient Institution",
                        "text",
                    ),
                    (
                        "recipient_address",
                        "Recipient Institution Address",
                        "textarea",
                    ),
                    (
                        "recipient_cibio_name",
                        "Recipient CIBio",
                        "text",
                    ),
                    (
                        "recipient_cibio_phone",
                        "Recipient CIBio Phone",
                        "text",
                    ),
                    (
                        "recipient_cibio_email",
                        "Recipient CIBio Email",
                        "text",
                    ),
                    (
                        "recipient_cqb_code",
                        "Recipient CQB Number",
                        "text",
                    ),
                ],
            },
            {
                "title": "Responsible Researcher — Recipient",
                "fields": [
                    (
                        "recipient_name",
                        "Responsible Researcher",
                        "text",
                    ),
                    (
                        "recipient_researcher_address",
                        "Researcher Institutional Address",
                        "textarea",
                    ),
                    (
                        "recipient_phone",
                        "Researcher Phone",
                        "text",
                    ),
                    (
                        "recipient_email",
                        "Researcher Email",
                        "text",
                    ),
                    (
                        "request_purpose",
                        "Purpose and Brief Description of Use",
                        "textarea",
                    ),
                ],
            },
            {
                "title": "GMO Material 1",
                "fields": gmo_material_fields("ogm_1"),
            },
            {
                "title": "GMO Material 2 — Optional",
                "fields": gmo_material_fields("ogm_2"),
            },
            {
                "title": "GMO Material 3 — Optional",
                "fields": gmo_material_fields("ogm_3"),
            },
            {
                "title": "Transport and Packaging",
                "fields": [
                    (
                        "transport_mode",
                        "Transport Mode",
                        select(TRANSPORT_MODE_OPTIONS),
                    ),
                    (
                        "transport_mode_other",
                        "Other Transport Mode",
                        "text",
                    ),
                    (
                        "transport_company",
                        "Carrier / Qualified Transport Company",
                        "text",
                    ),
                    (
                        "packaging_description",
                        "Detailed Packaging Description",
                        "textarea",
                    ),
                    (
                        "carrier_incident_acknowledged",
                        "Carrier Was Informed About Accident and Spill Procedures",
                        "checkbox",
                    ),
                    (
                        "restricted_access_label_confirmed",
                        "Restricted-Access Warning Is Included on the Outer Package",
                        "checkbox",
                    ),
                ],
            },
            {
                "title": "Genetically Modified Animals",
                "fields": [
                    (
                        "animal_gmo",
                        "Does the Shipment Contain Genetically Modified Animals?",
                        select(YES_NO_OPTIONS),
                    ),
                    (
                        "animal_transport_procedures",
                        "Preparation, Transport and Reception Procedures for AnGM",
                        "textarea",
                    ),
                ],
            },
            {
                "title": "Authorization and Signatures",
                "fields": [
                    (
                        "normative_reference",
                        "Regulatory Reference",
                        "textarea",
                    ),
                    (
                        "authorization_statement",
                        "Authorization Statement",
                        "textarea",
                    ),
                    (
                        "declaration_place",
                        "Place",
                        "text",
                    ),
                    (
                        "declaration_date",
                        "Date",
                        "text",
                    ),
                    (
                        "signer_name",
                        "Requesting Researcher",
                        "text",
                    ),
                    (
                        "signer_document",
                        "Requesting Researcher Document / ID",
                        "text",
                    ),
                    (
                        "sender_cibio_president_name",
                        "Sender CIBio President",
                        "text",
                    ),
                    (
                        "sender_cibio_president_title",
                        "Sender CIBio President Title",
                        "text",
                    ),
                    (
                        "recipient_cibio_president_name",
                        "Recipient CIBio President",
                        "text",
                    ),
                    (
                        "recipient_cibio_president_title",
                        "Recipient CIBio President Title",
                        "text",
                    ),
                ],
            },
        ],
    },
    "triple_packaging_checklist": {
        "title": "Triple packaging checklist",
        "description": "Required checklist for Risk Class 2 or NB2, and recommended for controlled biological shipments.",
        "sections": [
            {
                "title": "Packaging System",
                "fields": [
                    ("primary_container_ok", "Primary Container Sealed and Leakproof", "checkbox"),
                    ("secondary_container_ok", "Resistant and Leakproof Secondary Packaging", "checkbox"),
                    ("absorbent_material_ok", "Sufficient Absorbent Material", "checkbox"),
                    ("rigid_outer_package_ok", "Rigid Outer Packaging", "checkbox"),
                    ("labeling_ok", "Adequate external identification", "checkbox"),
                    ("temperature_condition_ok", "Appropriate Temperature Condition", "checkbox"),
                    ("notes", "Notes", "textarea"),
                ],
            },
        ],
    },
    "traceability_report": {
        "title": "Legacy traceability record",
        "description": "Legacy record superseded by Content declaration and traceability.",
        "sections": [
            {
                "title": "Traceability",
                "fields": [
                    ("shipment_code", "Shipment Code", "text"),
                    ("material_description", "Material", "textarea"),
                    ("sender_institution", "Sender Institution / CQB", select(INSTITUTION_CQB_OPTIONS)),
                    ("recipient_institution", "Recipient Institution", "text"),
                    ("dispatch_date", "Dispatch Date", "text"),
                    ("carrier_name", "Carrier", "text"),
                    ("tracking_code", "Tracking Code", "text"),
                    ("notes", "Notes", "textarea"),
                ],
            },
        ],
    },
}


def get_document_form_schema(document_type):
    return DOCUMENT_FORM_SCHEMAS.get(
        document_type,
        {
            "title": document_type.replace("_", " ").title(),
            "description": "",
            "sections": [
                {
                    "title": "Document Data",
                    "fields": [
                        ("notes", "Notes", "textarea"),
                    ],
                },
            ],
        },
    )


def iter_schema_fields(schema):
    for section in schema.get("sections", []):
        for field in section.get("fields", []):
            yield field


def extract_form_values(schema, post_data):
    values = {}

    for name, _label, field_type in iter_schema_fields(schema):
        if field_type == "checkbox":
            values[name] = name in post_data
        else:
            values[name] = str(post_data.get(name, "")).strip()

    return values
