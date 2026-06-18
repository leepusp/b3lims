from core.services.cqb_registry import get_lab_cqb_select_options


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
    "Sim",
    "Não",
]

LAB_CQB_OPTIONS = [""] + get_lab_cqb_select_options()


def select(options):
    return "select:" + "|".join(options)


DOCUMENT_FORM_SCHEMAS = {
    "content_declaration": {
        "title": "Content declaration",
        "description": "Required document for GMO and non-GMO biological material shipments, Risk Class 1/2 and NB1/NB2.",
        "sections": [
            {
                "title": "Sender",
                "fields": [
                    ("sender_name", "Nome do responsável sender", "text"),
                    ("sender_institution", "Instituição sender", "text"),
                    ("sender_lab_cqb", "Laboratório sender / CQB", select(LAB_CQB_OPTIONS)),
                    ("sender_address", "Endereço do sender", "textarea"),
                    ("sender_contact", "Contato do sender", "text"),
                ],
            },
            {
                "title": "Recipient",
                "fields": [
                    ("recipient_name", "Nome do responsável recipient", "text"),
                    ("recipient_institution", "Instituição destinatária", "text"),
                    ("recipient_lab_cqb", "Laboratório recipient / CQB", select(LAB_CQB_OPTIONS)),
                    ("recipient_address", "Endereço do recipient", "textarea"),
                    ("recipient_contact", "Contato do recipient", "text"),
                ],
            },
            {
                "title": "Classificação do material",
                "fields": [
                    ("material_description", "Descrição do material", "textarea"),
                    ("material_type", "Tipo de material", "text"),
                    ("risk_class", "Risk Class", select(RISK_CLASS_OPTIONS)),
                    ("biosafety_level", "Nível de biossegurança", select(BIOSAFETY_LEVEL_OPTIONS)),
                    ("is_ogm", "OGM", select(YES_NO_OPTIONS)),
                    ("quantity_volume", "Quantidade / volume", "text"),
                    ("transport_conditions", "Condições de transporte", "textarea"),
                    ("purpose", "Finalidade", "textarea"),
                ],
            },
            {
                "title": "Conformidade e responsabilidade",
                "fields": [
                    ("regulatory_compliance", "Conformidade com normas vigentes", "textarea"),
                    ("packaging_statement", "Acondicionamento e package", "textarea"),
                    ("transport_condition_statement", "Condições de transporte", "textarea"),
                    ("responsibility_statement", "Responsabilidade", "textarea"),
                    ("local_date", "Local e data", "text"),
                    ("sender_document", "Responsible person's document/ID", "text"),
                ],
            },
        ],
    },
    "sender_declaration": {
        "title": "ANTT sender declaration",
        "description": "Sender responsibility declaration for biological material transport, when applicable.",
        "sections": [
            {
                "title": "Sender",
                "fields": [
                    ("sender_name", "Nome do responsável sender", "text"),
                    ("sender_institution", "Instituição sender", "text"),
                    ("sender_lab_cqb", "Laboratório sender / CQB", select(LAB_CQB_OPTIONS)),
                    ("sender_address", "Endereço do sender", "textarea"),
                    ("sender_contact", "Contato do sender", "text"),
                ],
            },
            {
                "title": "Shipment identification",
                "fields": [
                    ("material_description", "Content description", "textarea"),
                    ("risk_class", "Risk Class", select(RISK_CLASS_OPTIONS)),
                    ("biosafety_level", "Nível de biossegurança", select(BIOSAFETY_LEVEL_OPTIONS)),
                    ("is_ogm", "OGM", select(YES_NO_OPTIONS)),
                    ("quantity_volume", "Quantidade / volume", "text"),
                    ("transport_conditions", "Condições de transporte", "textarea"),
                ],
            },
            {
                "title": "Declarações obrigatórias",
                "fields": [
                    ("regulatory_compliance", "Conformidade com normas vigentes", "textarea"),
                    ("packaging_statement", "Acondicionamento e package", "textarea"),
                    ("transport_condition_statement", "Condições de transporte", "textarea"),
                    ("responsibility_statement", "Responsabilidade", "textarea"),
                    ("local_date", "Local e data", "text"),
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
                    ("sender_name", "Responsável sender", "text"),
                    ("sender_institution", "Instituição sender", "text"),
                    ("sender_lab_cqb", "Laboratório sender / CQB", select(LAB_CQB_OPTIONS)),
                    ("sender_address", "Endereço", "textarea"),
                    ("sender_contact", "Telefone/e-mail", "text"),
                ],
            },
            {
                "title": "Recipient",
                "fields": [
                    ("recipient_name", "Responsável recipient", "text"),
                    ("recipient_institution", "Instituição destinatária", "text"),
                    ("recipient_lab_cqb", "Laboratório recipient / CQB", select(LAB_CQB_OPTIONS)),
                    ("recipient_address", "Endereço", "textarea"),
                    ("recipient_contact", "Telefone/e-mail", "text"),
                ],
            },
            {
                "title": "Classificação externa",
                "fields": [
                    ("risk_class", "Risk Class", select(RISK_CLASS_OPTIONS)),
                    ("biosafety_level", "Nível de biossegurança", select(BIOSAFETY_LEVEL_OPTIONS)),
                    ("is_ogm", "OGM", select(YES_NO_OPTIONS)),
                    ("transport_conditions", "Condições de transporte", "text"),
                ],
            },
        ],
    },
    "mta_ttm": {
        "title": "MTA / TTM",
        "description": "Material Transfer Agreement / Material Transfer Term for GMO and non-GMO shipments, Risk Class 1/2 and NB1/NB2.",
        "sections": [
            {
                "title": "Parte sender",
                "fields": [
                    ("sender_name", "Responsável sender", "text"),
                    ("sender_institution", "Instituição sender", "text"),
                    ("sender_lab_cqb", "Laboratório sender / CQB", select(LAB_CQB_OPTIONS)),
                    ("sender_address", "Endereço", "textarea"),
                    ("sender_contact", "Contato", "text"),
                ],
            },
            {
                "title": "Parte recebedora",
                "fields": [
                    ("recipient_name", "Responsável recebedor", "text"),
                    ("recipient_institution", "Instituição recebedora", "text"),
                    ("recipient_lab_cqb", "Laboratório recebedor / CQB", select(LAB_CQB_OPTIONS)),
                    ("recipient_address", "Endereço", "textarea"),
                    ("recipient_contact", "Contato", "text"),
                ],
            },
            {
                "title": "Material transferido",
                "fields": [
                    ("material_description", "Descrição do material", "textarea"),
                    ("material_type", "Tipo de material", "text"),
                    ("risk_class", "Risk Class", select(RISK_CLASS_OPTIONS)),
                    ("biosafety_level", "Nível de biossegurança", select(BIOSAFETY_LEVEL_OPTIONS)),
                    ("is_ogm", "OGM", select(YES_NO_OPTIONS)),
                    ("quantity_volume", "Quantidade / volume", "text"),
                    ("purpose", "Finalidade da transferência", "textarea"),
                ],
            },
            {
                "title": "Condições e responsabilidade",
                "fields": [
                    ("transport_conditions", "Condições de transporte", "textarea"),
                    ("regulatory_compliance", "Conformidade com normas vigentes", "textarea"),
                    ("responsibility_statement", "Responsabilidade", "textarea"),
                    ("local_date", "Local e data", "text"),
                ],
            },
        ],
    },
    "cibio_authorization": {
        "title": "Autorização de transporte CIBio para OGM",
        "description": "Required document for shipments containing genetically modified organisms.",
        "sections": [
            {
                "title": "Instituição sender",
                "fields": [
                    ("sender_name", "Responsável sender", "text"),
                    ("sender_institution", "Instituição sender", "text"),
                    ("sender_lab_cqb", "Laboratório sender / CQB", select(LAB_CQB_OPTIONS)),
                    ("sender_cibio_approval", "Autorização/anuência CIBio sender", "textarea"),
                ],
            },
            {
                "title": "Instituição destinatária",
                "fields": [
                    ("recipient_name", "Responsável recipient", "text"),
                    ("recipient_institution", "Instituição destinatária", "text"),
                    ("recipient_lab_cqb", "Laboratório recipient / CQB", select(LAB_CQB_OPTIONS)),
                    ("recipient_cibio_approval", "Autorização/anuência CIBio destinatária", "textarea"),
                ],
            },
            {
                "title": "Material OGM",
                "fields": [
                    ("organism_name", "Organismo / construção / linhagem", "textarea"),
                    ("risk_class", "Risk Class", select(RISK_CLASS_OPTIONS)),
                    ("biosafety_level", "Nível de biossegurança", select(BIOSAFETY_LEVEL_OPTIONS)),
                    ("is_ogm", "OGM", select(YES_NO_OPTIONS)),
                    ("container_quantity", "Número de recipientes", "text"),
                    ("container_type", "Tipo de recipiente", "text"),
                    ("storage_temperature", "Temperatura de armazenamento/transporte", "text"),
                    ("transport_method", "Método de transporte", "textarea"),
                ],
            },
            {
                "title": "Package e traceability",
                "fields": [
                    ("packaging_statement", "Sistema de package", "textarea"),
                    ("traceability_statement", "Registro de traceability", "textarea"),
                    ("local_date", "Local e data", "text"),
                ],
            },
        ],
    },
    "triple_packaging_checklist": {
        "title": "Triple packaging checklist",
        "description": "Required checklist for Risk Class 2 or NB2, and recommended for controlled biological shipments.",
        "sections": [
            {
                "title": "Sistema de package",
                "fields": [
                    ("primary_container_ok", "Recipiente primário estanque e vedado", "checkbox"),
                    ("secondary_container_ok", "Package secundária resistente e estanque", "checkbox"),
                    ("absorbent_material_ok", "Material absorvente suficiente", "checkbox"),
                    ("rigid_outer_package_ok", "Package externa rígida", "checkbox"),
                    ("labeling_ok", "Adequate external identification", "checkbox"),
                    ("temperature_condition_ok", "Condição de temperatura adequada", "checkbox"),
                    ("notes", "Observações", "textarea"),
                ],
            },
        ],
    },
    "traceability_report": {
        "title": "Registro de traceability",
        "description": "Internal shipment traceability record.",
        "sections": [
            {
                "title": "Traceability",
                "fields": [
                    ("shipment_code", "Shipment code", "text"),
                    ("material_description", "Material", "textarea"),
                    ("sender_lab_cqb", "Laboratório sender / CQB", select(LAB_CQB_OPTIONS)),
                    ("recipient_lab_cqb", "Laboratório recipient / CQB", select(LAB_CQB_OPTIONS)),
                    ("dispatch_date", "Data de envio", "text"),
                    ("carrier_name", "Transportador", "text"),
                    ("tracking_code", "Código de rastreio", "text"),
                    ("notes", "Observações", "textarea"),
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
                    "title": "Dados do documento",
                    "fields": [
                        ("notes", "Observações", "textarea"),
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
