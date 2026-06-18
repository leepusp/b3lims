LAB_CQB_REGISTRY = [
    {
        "lab_name": "Laboratório de Genômica Comparativa e Evolutiva",
        "institution": "IQ-USP",
        "cqb": "0029/97",
    },
    {
        "lab_name": "Laboratório de Genética Bacteriana",
        "institution": "ICB II",
        "cqb": "0046/98",
    },
    {
        "lab_name": "Laboratório de Estrutura e Evolução de Proteínas - Biologia Estrutural",
        "institution": "ICB II",
        "cqb": "0046/98",
    },
    {
        "lab_name": "Laboratório de Genética de Bactérias",
        "institution": "IB-UNICAMP",
        "cqb": "0069/98",
    },
    {
        "lab_name": "Laboratório de Biologia Celular de Crescimento e Divisão Bacteriana",
        "institution": "IQ-USP",
        "cqb": "0029/97",
    },
    {
        "lab_name": "Laboratório de Estudos Estruturais de Macromoléculas",
        "institution": "FCFRP",
        "cqb": "solicitado por e-mail",
    },
    {
        "lab_name": "Laboratório de Genética de Bactérias",
        "institution": "IB-UNESP Rio Claro",
        "cqb": "solicitado por e-mail",
    },
    {
        "lab_name": "Laboratório de Bioinformática",
        "institution": "IQ-USP",
        "cqb": "0029/97",
    },
    {
        "lab_name": "Laboratório de Regulação da Expressão Gênica e Patogenicidade Bacteriana",
        "institution": "FMRP",
        "cqb": "solicitado por e-mail",
    },
    {
        "lab_name": "Laboratório de Bioquímica de Complexos Bacterianos",
        "institution": "IB - UNICAMP",
        "cqb": "0069/98",
    },
    {
        "lab_name": "Laboratório de Biologia Molecular Bacteriana",
        "institution": "IB - UNICAMP",
        "cqb": "0069/98",
    },
    {
        "lab_name": "Laboratório de Biologia Estrutural Aplicada",
        "institution": "ICB II",
        "cqb": "0046/98",
    },
    {
        "lab_name": "Laboratório de Biotecnologia de Citros",
        "institution": "IAC - Campinas",
        "cqb": "417/16",
    },
    {
        "lab_name": "Laboratório de Fisiologia e Genética Bacteriana",
        "institution": "ICB II",
        "cqb": "0046/98",
    },
    {
        "lab_name": "Laboratório da Regulação da Expressão Gênica em Microrganismos",
        "institution": "IQ-USP",
        "cqb": "0029/97",
    },
    {
        "lab_name": "Laboratório de Genética e Fisiologia Bacteriana",
        "institution": "ICB II",
        "cqb": "0046/98",
    },
    {
        "lab_name": "Grupo de Pesquisa em RMN de Proteínas",
        "institution": "IQ-USP",
        "cqb": "0029/97",
    },
    {
        "lab_name": "Laboratório de Estrutura e Evolução de Proteínas - Bioinformática",
        "institution": "ICB II",
        "cqb": "0046/98",
    },
    {
        "lab_name": "Laboratório de Genética Molecular Bacteriana",
        "institution": "ICB II",
        "cqb": "0046/98",
    },
    {
        "lab_name": "Laboratório de Enzimologia",
        "institution": "IQ-USP",
        "cqb": "0029/97",
    },
    {
        "lab_name": "Laboratório de Estrutura e Função de Proteínas",
        "institution": "IQ-USP",
        "cqb": "0029/97",
    },
]


def get_lab_cqb_select_options():
    return [
        f"{item['lab_name']} — {item['institution']} — CQB {item['cqb']}"
        for item in LAB_CQB_REGISTRY
    ]


def find_cqb_by_lab_name(lab_name):
    normalized = str(lab_name or "").strip().lower()

    for item in LAB_CQB_REGISTRY:
        if item["lab_name"].strip().lower() == normalized:
            return item

    return None
