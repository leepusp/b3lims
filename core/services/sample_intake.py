import os
import pandas as pd

from core.models import Biobank, Collection, Sample
from core.models.samples.intake import SampleIntakeRecord


COLUMN_ALIASES = {
    "sample_id": ["sample_id", "id", "barcode", "id_barcode", "sample code", "codigo", "código"],
    "sample_type": ["sample_type", "type", "biological_type", "tipo", "tipo_amostra"],
    "organism_name": ["organism_name", "organism", "identification", "nome", "organismo"],
    "biobank": ["biobank", "biobanco", "destination_biobank", "biobank_name"],
    "collection": ["collection", "colecao", "coleção", "collection_name"],
    "storage_location": ["storage_location", "location", "localizacao", "localização", "freezer_box"],
    "provider": ["provider", "collaborator", "sender", "fornecedor", "colaborador"],
    "research_group": ["research_group", "grupo", "laboratorio", "laboratório"],
    "is_public": ["is_public", "public", "visibilidade"],
    "scientific_notes": ["scientific_notes", "notes", "observations", "observacoes", "observações"],

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

    # Phage.
    "phage_name": ["phage_name", "fago", "phage"],
    "taxonomy": ["taxonomy", "taxonomia"],
    "morphotype": ["morphotype", "morfotipo"],
    "lifestyle": ["lifestyle", "ciclo"],
    "genome_type": ["genome_type", "tipo_genoma"],
    "genome_size_bp": ["genome_size_bp", "genome_size", "tamanho_genoma"],

    # Plasmid.
    "backbone_name": ["backbone_name", "backbone", "vector", "vetor"],
    "vector_type": ["vector_type", "tipo_vetor"],
    "origin_of_replication": ["origin_of_replication", "origin", "ori"],
    "backbone_size_bp": ["backbone_size_bp", "backbone_size"],
    "is_empty_vector": ["is_empty_vector", "empty_vector"],
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
    ext = os.path.splitext(file_path)[1].lower()

    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(file_path)

    if ext in [".tsv", ".txt"]:
        return pd.read_csv(file_path, sep="\t")

    return pd.read_csv(file_path)


def import_sample_table(batch):
    df = read_sample_table(batch.original_file.path)
    df = df.dropna(how="all")

    column_map = _build_column_map(df.columns)

    total = 0
    valid = 0
    invalid = 0

    for idx, row in df.iterrows():
        total += 1

        raw_data = {
            str(col): _clean_value(row[col])
            for col in df.columns
        }

        normalized = {}
        for canonical, original_col in column_map.items():
            normalized[canonical] = _clean_value(row[original_col])

        sample_id = normalized.get("sample_id", "")
        sample_type = _canonical_type(normalized.get("sample_type", ""))
        organism_name = normalized.get("organism_name", "")
        biobank_name = normalized.get("biobank", "")
        collection_name = normalized.get("collection", "")

        errors = []
        warnings = []

        if not sample_id:
            errors.append("Missing sample_id.")
        elif Sample.objects.filter(sample_id=sample_id).exists():
            errors.append(f"Sample ID already exists: {sample_id}")

        if not sample_type:
            errors.append("Missing sample_type.")
        elif sample_type not in ["Bacterium (Host)", "Phage (Virus)", "Plasmid", "Other"]:
            warnings.append(f"Unknown sample_type: {sample_type}")

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
                organism_name = normalized.get("phage_name", "") or normalized.get("taxonomy", "")
            elif sample_type == "Plasmid":
                organism_name = normalized.get("construction_name", "") or normalized.get("backbone_name", "")

        status = "ready_to_fill" if not errors else "waiting_review"

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

    batch.total_rows = total
    batch.valid_rows = valid
    batch.invalid_rows = invalid
    batch.status = "validated"
    batch.save(update_fields=["total_rows", "valid_rows", "invalid_rows", "status", "updated_at"])

    return batch
