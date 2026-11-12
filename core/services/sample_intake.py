import os
import pandas as pd
from django.db import transaction

from core.models import Biobank, Collection, Sample
from core.models.samples.intake import SampleIntakeRecord
from core.services import sample_tables


COLUMN_ALIASES = {
    "sample_id": ["sample_id", "id", "barcode", "id_barcode", "sample code", "codigo", "código"],
    "sample_type": ["sample_type", "type", "biological_type", "tipo", "tipo_amostra"],
    "organism_name": ["organism_name", "organism", "identification", "nome", "organismo"],
    "biobank": ["biobank", "biobanco", "destination_biobank", "biobank_name"],
    "collection": ["collection", "collections", "colecao", "coleção", "collection_name"],
    "storage_location": ["storage_location", "location", "localizacao", "localização", "freezer_box"],
    "provider": ["provider", "collaborator", "sender", "fornecedor", "colaborador"],
    "research_group": ["research_group", "grupo", "laboratorio", "laboratório"],
    "is_public": ["is_public", "public", "visibilidade"],
    "scientific_notes": ["scientific_notes", "notes", "observations", "observacoes", "observações"],
    "biosafety_level": ["biosafety_level", "biosafety", "nivel_biosseguranca", "nível_biossegurança"],

    # Future movement/receipt metadata.
    "intake_type": ["intake_type", "movement_type", "tipo_recebimento"],
    "source_biobank": ["source_biobank", "origin_biobank", "biobank_origem"],
    "destination_biobank": ["destination_biobank", "target_biobank", "biobank_destino"],
    "expected_arrival_date": ["expected_arrival_date", "arrival_date", "data_prevista"],
    "temperature_condition": ["temperature_condition", "temperature", "temperatura"],
    "movement_notes": ["movement_notes", "transport_notes", "notas_transporte"],

    # Bacteria.
    "genus": ["genus", "genero", "gênero"],
    "species": ["species", "especie", "espécie"],
    "strain": ["strain", "linhagem"],
    "genotype": ["genotype", "genotipo", "genótipo"],
    "resistance_markers": ["resistance_markers", "resistance", "marcadores_resistencia"],
    "isolation_source": ["isolation_source", "source", "origem_isolamento"],

    # Phage.
    "phage_name": ["phage_name", "fago", "phage"],
    "taxonomy": ["taxonomy", "taxonomia"],
    "morphotype": ["morphotype", "morfotipo"],
    "lifestyle": ["lifestyle", "ciclo"],
    "genome_type": ["genome_type", "tipo_genoma"],
    "genome_size_bp": ["genome_size_bp", "genome_size", "tamanho_genoma"],
    "isolation_method": ["isolation_method", "metodo_isolamento"],
    "temp_C": ["temp_C", "temp_c", "growth_temperature"],
    "ncbi_accession": ["ncbi_accession", "genbank", "accession"],

    # Plasmid.
    "backbone_name": ["backbone_name", "backbone", "vector", "vetor"],
    "vector_type": ["vector_type", "tipo_vetor"],
    "origin_of_replication": ["origin_of_replication", "origin", "ori"],
    "backbone_size_bp": ["backbone_size_bp", "backbone_size"],
    "is_empty_vector": ["is_empty_vector", "empty_vector"],
    "induction_system": ["induction_system", "inducao", "indução"],
    "backbone_resistance_markers": ["backbone_resistance_markers", "backbone_resistance"],
    "insert_resistance_markers": ["insert_resistance_markers", "insert_resistance"],
    "purpose": ["purpose", "finalidade"],
    "insert_name": ["insert_name", "insert", "inserto"],
    "insert_size_bp": ["insert_size_bp", "insert_size"],
    "construction_name": ["construction_name", "construct", "construcao", "construção"],
}


TYPE_ALIASES = {
    "bacteria": "Bacterium (Host)",
    "bacterium": "Bacterium (Host)",
    "bacterium (host)": "Bacterium (Host)",
    "bacteria (host)": "Bacterium (Host)",
    "host": "Bacterium (Host)",
    "bactéria": "Bacterium (Host)",
    "bacteria hospedeira": "Bacterium (Host)",

    "phage": "Phage (Virus)",
    "fago": "Phage (Virus)",
    "virus": "Phage (Virus)",
    "vírus": "Phage (Virus)",
    "phage (virus)": "Phage (Virus)",

    "plasmid": "Plasmid",
    "plasmídeo": "Plasmid",
    "plasmideo": "Plasmid",

    "other": "Other",
    "outro": "Other",
}


def _normalize_header(value):
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def _clean_value(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def _as_bool(value):
    raw = _clean_value(value).lower()
    return raw in {"1", "true", "yes", "sim", "public", "público", "publico"}


def _canonical_type(value):
    raw = _clean_value(value)
    key = raw.lower().strip()
    return TYPE_ALIASES.get(key, raw)


def _build_column_map(columns):
    normalized_columns = {_normalize_header(c): c for c in columns}
    result = {}

    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            normalized_alias = _normalize_header(alias)
            if normalized_alias in normalized_columns:
                result[canonical] = normalized_columns[normalized_alias]
                break

    return result



def read_sample_table(file_path):
    ext = os.path.splitext(str(file_path))[1].lower()

    if ext in {".xlsx", ".xls"}:
        return pd.read_excel(
            file_path,
            sheet_name=0,
            dtype=str,
            keep_default_na=False,
        )

    if ext == ".tsv":
        return pd.read_csv(
            file_path,
            sep="\t",
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )

    if ext in {".csv", ".txt"}:
        return pd.read_csv(
            file_path,
            sep=None,
            engine="python",
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )

    raise ValueError(
        "Unsupported file format. Use CSV, TSV, XLS or XLSX."
    )



def evaluate_row(normalized, seen_sample_ids):
    """Validate one table row: IDs, type, typed columns, Biobank and Collection names, organism and visibility."""
    sample_id = normalized.get("sample_id", "")
    sample_type = _canonical_type(normalized.get("sample_type", ""))
    organism_name = normalized.get("organism_name", "")
    biobank_name = normalized.get("biobank", "")
    collection_name = normalized.get("collection", "")

    errors = []
    warnings = []

    if not sample_id:
        errors.append("Missing sample_id.")
    elif Sample.objects.filter(
        sample_id__iexact=sample_id
    ).exists():
        errors.append(
            f"Sample ID already exists: {sample_id}"
        )

    if sample_id:
        key = sample_id.casefold()

        if key in seen_sample_ids:
            errors.append(
                f"Duplicate sample_id in this table: {sample_id}"
            )

        seen_sample_ids.add(key)

    if not sample_type:
        errors.append("Missing sample_type.")
    elif sample_type not in ["Bacterium (Host)", "Phage (Virus)", "Plasmid", "Other"]:
        errors.append(
            f"Unsupported sample_type: {sample_type}"
        )

    matched_biobank = None
    if biobank_name:
        matched_biobank = Biobank.objects.filter(name__iexact=biobank_name).first()
        if not matched_biobank:
            warnings.append(f"Biobank not found: {biobank_name}")

    matched_collection = None
    if collection_name:
        matched_collection = Collection.objects.filter(name__iexact=collection_name).first()
        if not matched_collection:
            warnings.append(f"Collection not found: {collection_name}")

    if not organism_name:
        if sample_type == "Bacterium (Host)":
            organism_name = " ".join(
                x for x in [
                    normalized.get("genus", ""),
                    normalized.get("species", ""),
                    normalized.get("strain", ""),
                ]
                if x
            )
        elif sample_type == "Phage (Virus)":
            organism_name = normalized.get("strain", "") or normalized.get("phage_name", "") or normalized.get("taxonomy", "")
        elif sample_type == "Plasmid":
            organism_name = normalized.get("construction_name", "") or normalized.get("backbone_name", "")

    if not organism_name.strip():
        errors.append(
            "Missing organism_name or subtype identification."
        )

    # Type-aware check of every typed column: numbers, yes/no, dates, lists and fixed vocabularies.
    specs = sample_tables.by_key()
    own = {c.key for c in sample_tables.columns_for(sample_type)} if sample_type in sample_tables.SAMPLE_TYPES else set(specs)

    for key in list(normalized):
        spec = specs.get(key)

        if spec is None or key in {"sample_type", "biobank", "collection", "is_public"} or not normalized[key]:
            continue

        if key not in own:
            warnings.append(f"{key} does not apply to {sample_type} and will be ignored.")
            normalized[key] = ""

            continue

        value, problem = sample_tables.normalize_value(spec, normalized[key])
        normalized[key] = value

        if problem:
            errors.append(problem)

    visibility = normalized.get(
        "is_public", ""
    ).strip().casefold()

    allowed_visibility = {
        "", "0", "1",
        "true", "false",
        "yes", "no",
        "sim", "não", "nao",
        "public", "público", "publico",
        "private", "privado",
    }

    if visibility not in allowed_visibility:
        errors.append(
            "Invalid is_public. Use true or false."
        )

    if ";" in collection_name:
        errors.append(
            "Multiple Collections require individual review."
        )

    return {
        "sample_id": sample_id, "sample_type": sample_type, "organism_name": organism_name,
        "biobank_name": biobank_name, "collection_name": collection_name,
        "matched_biobank": matched_biobank, "matched_collection": matched_collection,
        "errors": errors, "warnings": warnings, "normalized": normalized,
    }


@transaction.atomic
def import_sample_table(batch):
    df = read_sample_table(batch.original_file.path)
    # Empty strings must not become false Sample rows.
    df = (
        df.replace(r"^\s*$", pd.NA, regex=True)
        .dropna(how="all")
        .fillna("")
    )

    normalized_headers = [
        _normalize_header(name)
        for name in df.columns
    ]

    if len(normalized_headers) != len(set(normalized_headers)):
        raise ValueError(
            "Duplicate column headers in the uploaded table."
        )

    column_map = _build_column_map(df.columns)

    required = {"sample_id", "sample_type"}
    missing = sorted(required - set(column_map))

    if missing:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing)
        )

    seen_sample_ids = set()

    total = 0
    valid = 0
    invalid = 0

    for idx, row in df.iterrows():
        raw_data = {
            str(col): _clean_value(row[col])
            for col in df.columns
        }

        preset_columns = {
            original_col
            for canonical, original_col in column_map.items()
            if canonical in {"biobank", "collection", "sample_type"}
        }

        # An ID that is only the type prefix (BAC-, PHA-, ...) is a template placeholder, not an identifier.
        id_column = column_map.get("sample_id")
        bare_id = bool(id_column) and raw_data.get(id_column, "").strip() in set(sample_tables.ID_PREFIXES.values())

        if bare_id:
            preset_columns.add(id_column)

        # Ignore untouched rows of a preconfigured template.
        # Any other populated field must still be validated.
        if preset_columns and not any(
            value
            for column, value in raw_data.items()
            if column not in preset_columns
        ):
            continue

        total += 1

        normalized = {}
        for canonical, original_col in column_map.items():
            normalized[canonical] = _clean_value(row[original_col])

        result = evaluate_row(
            normalized, seen_sample_ids,
        ) if not bare_id else evaluate_row(
            {**normalized, "sample_id": ""}, seen_sample_ids,
        )
        sample_id, sample_type = result["sample_id"], result["sample_type"]
        organism_name = result["organism_name"]
        biobank_name, collection_name = result["biobank_name"], result["collection_name"]
        matched_biobank, matched_collection = result["matched_biobank"], result["matched_collection"]
        errors, warnings = result["errors"], result["warnings"]
        normalized = result["normalized"]

        status = (
            "ready_to_fill"
            if not errors
            else "waiting_review"
        )

        SampleIntakeRecord.objects.create(
            batch=batch,
            row_number=int(idx) + 2,
            imported_sample_id=sample_id,
            sample_type=sample_type,
            organism_name=organism_name,
            biobank_name=biobank_name,
            collection_name=collection_name,
            matched_biobank=matched_biobank,
            matched_collection=matched_collection,
            storage_location=normalized.get("storage_location", ""),
            provider=normalized.get("provider", ""),
            research_group_name=normalized.get("research_group", ""),
            is_public=_as_bool(normalized.get("is_public", "")),
            scientific_notes=normalized.get("scientific_notes", ""),
            intake_type=normalized.get("intake_type", ""),
            source_biobank_name=normalized.get("source_biobank", ""),
            destination_biobank_name=normalized.get("destination_biobank", ""),
            expected_arrival_date=normalized.get("expected_arrival_date", ""),
            temperature_condition=normalized.get("temperature_condition", ""),
            movement_notes=normalized.get("movement_notes", ""),
            raw_data=raw_data,
            normalized_data=normalized,
            validation_errors=errors,
            validation_warnings=warnings,
            status=status,
        )

        if errors:
            invalid += 1
        else:
            valid += 1

    if total == 0:
        raise ValueError(
            "No Sample rows found. Complete at least one row "
            "before uploading the template."
        )

    known = set(column_map.values())
    ignored = [str(c) for c in df.columns if c not in known and str(c).strip()]

    if ignored:
        batch.notes = ("Columns not recognised and ignored: " + ", ".join(ignored))[:500]

    batch.total_rows = total
    batch.valid_rows = valid
    batch.invalid_rows = invalid
    batch.status = "validated"
    batch.save(update_fields=["total_rows", "valid_rows", "invalid_rows", "status", "notes", "updated_at"])

    return batch


EDIT_SKIP = {"sample_type", "biobank", "collection"}


def update_intake_record(record, values):
    """Apply edits made on screen to one staged row, validate it again and refresh the batch counters."""
    batch = record.batch
    submitted = {k: str(v).strip() for k, v in values.items()}
    sample_type = _canonical_type(submitted.get("sample_type", record.sample_type or ""))
    own = {c.key for c in sample_tables.columns_for(sample_type)} if sample_type in sample_tables.SAMPLE_TYPES else set()
    normalized = dict(record.normalized_data or {})

    for key in sample_tables.by_key():
        if key in submitted:
            normalized[key] = submitted[key]

    normalized["sample_type"] = sample_type

    # Values that do not belong to the chosen type are dropped instead of being reported again.
    for key in list(normalized):
        if key in sample_tables.by_key() and own and key not in own:
            normalized[key] = ""

    others = {
        (r.imported_sample_id or "").casefold()
        for r in batch.records.exclude(pk=record.pk)
        if r.imported_sample_id
    }
    result = evaluate_row(normalized, others)

    record.imported_sample_id = result["sample_id"]
    record.sample_type = result["sample_type"]
    record.organism_name = result["organism_name"]
    record.biobank_name = result["biobank_name"]
    record.collection_name = result["collection_name"]
    record.matched_biobank = result["matched_biobank"]
    record.matched_collection = result["matched_collection"]
    record.provider = result["normalized"].get("provider", "")
    record.research_group_name = result["normalized"].get("research_group", "")
    record.is_public = _as_bool(result["normalized"].get("is_public", ""))
    record.scientific_notes = result["normalized"].get("scientific_notes", "")
    record.expected_arrival_date = result["normalized"].get("expected_arrival_date", "")
    record.temperature_condition = result["normalized"].get("temperature_condition", "")
    record.movement_notes = result["normalized"].get("movement_notes", "")
    record.normalized_data = result["normalized"]
    record.validation_errors = result["errors"]
    record.validation_warnings = result["warnings"]
    record.status = "waiting_review" if result["errors"] else "ready_to_fill"
    record.save()

    records = list(batch.records.all())
    batch.total_rows = len(records)
    batch.invalid_rows = sum(1 for r in records if r.validation_errors)
    batch.valid_rows = batch.total_rows - batch.invalid_rows
    batch.save(update_fields=["total_rows", "valid_rows", "invalid_rows", "updated_at"])

    return record
