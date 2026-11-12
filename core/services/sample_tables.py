"""Column definitions for Sample tables: one model per Sample type, used by the import template, the validation
of uploaded tables and the export, so the three always agree on names, data types and allowed values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

BACTERIUM, PHAGE, PLASMID, OTHER = "Bacterium (Host)", "Phage (Virus)", "Plasmid", "Other"
SAMPLE_TYPES = [BACTERIUM, PHAGE, PLASMID, OTHER]
TYPE_SLUGS = {"bacterium": BACTERIUM, "phage": PHAGE, "plasmid": PLASMID, "other": OTHER}
SLUG_OF = {v: k for k, v in TYPE_SLUGS.items()}

TEXT, INTEGER, DECIMAL, BOOLEAN, CHOICE, DATE, LIST = "text", "integer", "decimal", "boolean", "choice", "date", "list"
KIND_LABELS = {
    TEXT: "Text", INTEGER: "Whole number", DECIMAL: "Decimal number (use a dot)", BOOLEAN: "Yes / No",
    CHOICE: "Choose from the list", DATE: "Date (YYYY-MM-DD)", LIST: "List separated by commas",
}
TRUE_WORDS = {"1", "true", "yes", "y", "sim", "public", "público", "publico"}
FALSE_WORDS = {"0", "false", "no", "n", "não", "nao", "private", "privado"}

ID_PREFIXES = {BACTERIUM: "BAC-", PHAGE: "PHA-", PLASMID: "PLA-", OTHER: "SMP-"}
BIOSAFETY = ["NB-1", "NB-2", "NB-3", "NB-4"]
TEMPERATURES = ["Ambient", "2-8 °C", "-20 °C", "-80 °C", "Dry ice", "Liquid nitrogen"]
STATUSES = ["pending", "qc", "available", "rejected", "depleted"]


@dataclass(frozen=True)
class Column:
    key: str
    group: str
    kind: str = TEXT
    required: bool = False
    choices: tuple = ()
    help: str = ""
    example: dict = field(default_factory=dict)
    strict: bool = True  # False: the list is a suggestion, other values are accepted
    minimum: float | None = None
    maximum: float | None = None
    width: int = 20


IDENT, ORG, BIO, LOGISTICS = "Identification", "Organization", "Biological data", "Receipt and logistics"

COMMON = [
    Column("sample_id", IDENT, required=True, width=22, help="Your unique identifier for this Sample. Keep it as text so leading zeros are preserved.",
           example={BACTERIUM: "BAC-EXAMPLE-001", PHAGE: "PHA-EXAMPLE-001", PLASMID: "PLA-EXAMPLE-001", OTHER: "SMP-EXAMPLE-001"}),
    Column("sample_type", IDENT, CHOICE, required=True, choices=tuple(SAMPLE_TYPES), width=18, help="Type of Sample; decides which biological columns apply."),
    Column("organism_name", IDENT, width=30, help="Display name of the organism or material. When empty it is built from the biological columns.",
           example={BACTERIUM: "Escherichia coli BL21", PHAGE: "Escherichia phage T4", PLASMID: "pET28a-GFP", OTHER: "Soil extract"}),
    Column("biosafety_level", IDENT, CHOICE, choices=tuple(BIOSAFETY), width=14, help="Biosafety level needed to handle the Sample.", example={BACTERIUM: "NB-1", PHAGE: "NB-1", PLASMID: "NB-1"}),
    Column("biobank", ORG, CHOICE, strict=False, width=24, help="Biobank that will hold the Sample. Pick from the list."),
    Column("research_group", ORG, width=22, help="Research group or laboratory."),
    Column("is_public", ORG, BOOLEAN, width=12, help="Yes when basic metadata may be public. Empty means private.", example={BACTERIUM: "false", PHAGE: "false"}),
    Column("provider", LOGISTICS, width=24, help="Collaborator or person who isolated or sent the Sample.", example={BACTERIUM: "Maria Souza", PHAGE: "Maria Souza"}),
    Column("expected_arrival_date", LOGISTICS, DATE, width=18, help="Expected arrival of the physical Sample.", example={BACTERIUM: "2026-12-01", PHAGE: "2026-12-01"}),
    Column("temperature_condition", LOGISTICS, CHOICE, choices=tuple(TEMPERATURES), strict=False, width=18, help="Temperature of the shipment or storage."),
    Column("movement_notes", LOGISTICS, width=28, help="Anything the receiving team should know about the transport."),
    Column("scientific_notes", BIO, width=34, help="Scientific observations.", example={BACTERIUM: "Isolated from a hospital effluent sample."}),
]

BACTERIUM_COLUMNS = [
    Column("genus", BIO, help="Genus.", example={BACTERIUM: "Escherichia"}),
    Column("species", BIO, help="Scientific species name.", example={BACTERIUM: "Escherichia coli"}),
    Column("strain", BIO, help="Strain designation.", example={BACTERIUM: "BL21"}),
    Column("genotype", BIO, width=28, help="Genetic markers.", example={BACTERIUM: "F- ompT hsdSB(rB- mB-) gal dcm"}),
    Column("isolation_source", BIO, width=26, help="Where it was isolated from.", example={BACTERIUM: "Hospital effluent"}),
    Column("resistance_markers", BIO, LIST, width=26, help="Antibiotic resistance markers separated by commas.", example={BACTERIUM: "AmpR, KanR"}),
]

PHAGE_COLUMNS = [
    Column("phage_name", BIO, help="Phage name.", example={PHAGE: "T4"}),
    Column("strain", BIO, help="Phage isolate or strain.", example={PHAGE: "T4 wild type"}),
    Column("genus", BIO, help="Genus.", example={PHAGE: "Tequatrovirus"}),
    Column("taxonomy", BIO, help="Family (or the lowest known rank).", example={PHAGE: "Straboviridae"}),
    Column("morphotype", BIO, CHOICE, choices=("myovirus", "siphovirus", "podovirus", "other"), help="Virion morphology.", example={PHAGE: "myovirus"}),
    Column("lifestyle", BIO, CHOICE, choices=("lytic", "lysogenic"), help="Life cycle.", example={PHAGE: "lytic"}),
    Column("genome_type", BIO, CHOICE, choices=("dsDNA", "ssDNA", "dsRNA", "ssRNA"), help="Genome type.", example={PHAGE: "dsDNA"}),
    Column("genome_size_bp", BIO, INTEGER, minimum=1, help="Genome size in base pairs, digits only.", example={PHAGE: "168903"}),
    Column("temp_C", BIO, DECIMAL, minimum=-10, maximum=120, width=14, help="Optimal growth temperature in °C.", example={PHAGE: "37"}),
    Column("isolation_source", BIO, width=26, help="Where it was isolated from.", example={PHAGE: "Sewage"}),
    Column("isolation_method", BIO, width=22, help="How it was isolated.", example={PHAGE: "Enrichment"}),
    Column("ncbi_accession", BIO, help="GenBank accession, if there is one.", example={PHAGE: "AF158101"}),
]

PLASMID_COLUMNS = [
    Column("backbone_name", BIO, required=True, help="Backbone (vector) name.", example={PLASMID: "pET28a(+)"}),
    Column("vector_type", BIO, CHOICE, choices=("expression", "suicide", "conjugation", "cloning"), help="Vector type.", example={PLASMID: "expression"}),
    Column("induction_system", BIO, help="For example T7, lac, araBAD.", example={PLASMID: "T7"}),
    Column("origin_of_replication", BIO, help="For example pBR322 or pUC.", example={PLASMID: "pBR322"}),
    Column("backbone_size_bp", BIO, INTEGER, minimum=0, help="Backbone size in base pairs, digits only.", example={PLASMID: "5369"}),
    Column("backbone_resistance_markers", BIO, LIST, width=26, help="Backbone resistance markers separated by commas.", example={PLASMID: "KanR"}),
    Column("is_empty_vector", BIO, BOOLEAN, width=14, help="Yes when it is an empty backbone, no when it carries an insert.", example={PLASMID: "false"}),
    Column("construction_name", BIO, help="Name of the construct.", example={PLASMID: "pET28a-GFP"}),
    Column("insert_name", BIO, help="Name of the insert.", example={PLASMID: "eGFP"}),
    Column("purpose", BIO, width=26, help="Function of the insert.", example={PLASMID: "Fluorescent reporter"}),
    Column("insert_size_bp", BIO, INTEGER, minimum=0, help="Insert size in base pairs, digits only.", example={PLASMID: "720"}),
    Column("insert_resistance_markers", BIO, LIST, width=26, help="Insert resistance markers separated by commas."),
]

SPECIFIC = {BACTERIUM: BACTERIUM_COLUMNS, PHAGE: PHAGE_COLUMNS, PLASMID: PLASMID_COLUMNS, OTHER: []}


def columns_for(sample_type: str | None) -> list[Column]:
    """Columns of the template of one Sample type; every type at once for ``None``."""
    if sample_type in SPECIFIC:
        return COMMON + SPECIFIC[sample_type]

    seen, merged = set(), []

    for column in COMMON + BACTERIUM_COLUMNS + PHAGE_COLUMNS + PLASMID_COLUMNS:
        if column.key not in seen:
            seen.add(column.key)
            merged.append(column)

    return merged


def by_key() -> dict[str, Column]:
    return {c.key: c for c in columns_for(None)}


def types_using(key: str) -> list[str]:
    return [t for t in SAMPLE_TYPES if any(c.key == key for c in SPECIFIC[t])]


def example_row(sample_type: str, columns: list[Column]) -> dict:
    row = {}

    for column in columns:
        value = column.example.get(sample_type, "")

        if column.key == "sample_type":
            value = sample_type

        row[column.key] = value

    return row


def type_label(column: Column) -> str:
    return KIND_LABELS[column.kind] + (f" ({int(column.minimum)} or more)" if column.kind == INTEGER and column.minimum is not None else "")


def normalize_value(column: Column, raw) -> tuple[str, str]:
    """``(value, error)`` for one cell: the canonical text to store, or a message in plain words."""
    text = "" if raw is None else str(raw).strip()

    if text == "":
        return "", ""

    if column.kind == INTEGER:
        try:
            number = Decimal(text.replace(" ", "").replace("_", ""))
        except InvalidOperation:
            return text, f"{column.key} must be a whole number, got “{text}”."

        if number != number.to_integral_value():
            return text, f"{column.key} must be a whole number, got “{text}”."

        if column.minimum is not None and number < Decimal(str(column.minimum)):
            return text, f"{column.key} must be {int(column.minimum)} or more."

        return str(int(number)), ""

    if column.kind == DECIMAL:
        try:
            number = Decimal(text.replace(",", "."))
        except InvalidOperation:
            return text, f"{column.key} must be a number, got “{text}”."

        if (column.minimum is not None and number < Decimal(str(column.minimum))) or (column.maximum is not None and number > Decimal(str(column.maximum))):
            return text, f"{column.key} is outside the expected range ({column.minimum} to {column.maximum})."

        return format(number.normalize(), "f"), ""

    if column.kind == BOOLEAN:
        low = text.casefold()

        if low in TRUE_WORDS:
            return "true", ""

        if low in FALSE_WORDS:
            return "false", ""

        return text, f"{column.key} must be yes or no (true or false), got “{text}”."

    if column.kind == DATE:
        match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?$", text)
        parsed = None

        try:
            if match:
                parsed = date(int(match[1]), int(match[2]), int(match[3]))
            else:
                match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", text)

                if match:
                    parsed = datetime.strptime(text, "%d/%m/%Y").date()
        except ValueError:
            parsed = None

        return (parsed.isoformat(), "") if parsed else (text, f"{column.key} must be a date like 2026-12-01, got “{text}”.")

    if column.kind == LIST:
        items = [i.strip() for i in re.split(r"[;,]", text) if i.strip()]

        return ", ".join(items), ""

    if column.kind == CHOICE and column.choices:
        for choice in column.choices:
            if text.casefold() == choice.casefold():
                return choice, ""

        if column.strict:
            return text, f"{column.key}: “{text}” is not one of {', '.join(column.choices)}."

    return text, ""
