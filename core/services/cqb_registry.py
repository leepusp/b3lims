INSTITUTION_CQB_REGISTRY = [
    {"institution": "IQ-USP", "cqb": "0029/97"},
    {"institution": "ICB II", "cqb": "0046/98"},
    {"institution": "IB-UNICAMP", "cqb": "0069/98"},
    {"institution": "IAC - Campinas", "cqb": "417/16"},
    {"institution": "FCFRP", "cqb": ""},
    {"institution": "FMRP", "cqb": ""},
    {"institution": "IB-UNESP Rio Claro", "cqb": ""},
]


def format_institution_cqb(institution, cqb=""):
    institution = str(institution or "").strip()
    cqb = str(cqb or "").strip()

    if not institution:
        return ""

    if not cqb:
        record = find_cqb_by_institution(institution)
        if record:
            cqb = record["cqb"]

    if cqb:
        return f"{institution} — CQB {cqb}"

    record = find_cqb_by_institution(institution)
    if record:
        return f"{institution} — CQB pending"

    return institution


def get_institution_cqb_select_options():
    return [
        format_institution_cqb(item["institution"], item["cqb"])
        for item in INSTITUTION_CQB_REGISTRY
    ]


def find_cqb_by_institution(value):
    normalized = str(value or "").strip().lower()

    for item in INSTITUTION_CQB_REGISTRY:
        institution = item["institution"].strip()
        cqb = item["cqb"].strip()

        labels = {
            institution.lower(),
            f"{institution} — CQB {cqb}".lower() if cqb else "",
            f"{institution} — CQB pending".lower(),
        }

        if normalized in labels:
            return item

    return None


# Compatibility aliases for existing imports.
LAB_CQB_REGISTRY = INSTITUTION_CQB_REGISTRY


def get_lab_cqb_select_options():
    return get_institution_cqb_select_options()


def find_cqb_by_lab_name(value):
    return find_cqb_by_institution(value)
