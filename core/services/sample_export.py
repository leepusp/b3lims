from io import BytesIO
import csv

import pandas as pd
from django.http import HttpResponse
from django.utils import timezone

from core.models import Sample


STANDARD_COLUMNS = [
    "sample_id",
    "sample_type",
    "organism_name",
    "status",
    "biobank",
    "collections",
    "storage_location",
    "provider",
    "is_public",
    "scientific_notes",
    "notes",
    "tags",
    "keywords",

    # Bacterium / host fields
    "genus",
    "species",
    "strain",
    "genotype",
    "isolation_source",
    "resistance_markers",

    # Phage fields
    "phage_name",
    "morphotype",
    "taxonomy",
    "lifestyle",
    "isolation_method",
    "genome_type",
    "genome_size_bp",
    "temp_C",
    "ncbi_accession",

    # Plasmid / vector fields
    "backbone_name",
    "backbone_aliases",
    "vector_type",
    "induction_system",
    "origin_of_replication",
    "backbone_size_bp",
    "backbone_resistance_markers",
    "is_empty_vector",
    "construction_name",
    "insert_name",
    "purpose",
    "insert_size_bp",
    "insert_resistance_markers",
]


FULL_EXTRA_COLUMNS = [
    "database_id",
    "uuid",
    "owner",
    "research_group",
    "is_active",
    "created_at",
    "updated_at",
    "files_count",
]


def _stringify(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _field(obj, name, default=""):
    if obj is None:
        return default
    try:
        value = getattr(obj, name)
    except Exception:
        return default
    return _stringify(value)


def _related(sample, names):
    for name in names:
        try:
            value = getattr(sample, name)
            if value is not None:
                return value
        except Exception:
            continue
    return None


def _many_to_text(sample, attr):
    try:
        manager = getattr(sample, attr)
        return "; ".join(str(obj) for obj in manager.all())
    except Exception:
        return ""


def _files_count(sample):
    for attr in ["files", "sample_files", "samplefile_set"]:
        try:
            manager = getattr(sample, attr)
            return manager.count()
        except Exception:
            continue
    return 0


def _subtype_data(sample):
    data = {column: "" for column in STANDARD_COLUMNS}

    subtype = _related(sample, [
        "bacteria",
        "bacterium",
        "phage",
        "plasmid",
    ])

    if subtype is None:
        return data

    for column in STANDARD_COLUMNS:
        if hasattr(subtype, column):
            data[column] = _field(subtype, column)

    return data


def _sample_to_row(sample, schema="standard"):
    subtype_data = _subtype_data(sample)

    row = {
        "sample_id": _field(sample, "sample_id"),
        "sample_type": _field(sample, "sample_type"),
        "organism_name": _field(sample, "organism_name"),
        "status": _field(sample, "status"),
        "biobank": _field(getattr(sample, "biobank", None), "name"),
        "collections": _many_to_text(sample, "collections"),
        "storage_location": _field(sample, "storage_location"),
        "provider": _field(getattr(sample, "owner", None), "username"),
        "is_public": _field(sample, "is_public"),
        "scientific_notes": _field(sample, "scientific_notes"),
        "notes": _field(sample, "notes"),
        "tags": _many_to_text(sample, "tags"),
        "keywords": _many_to_text(sample, "keywords"),
    }

    row.update(subtype_data)

    if schema == "full":
        row.update({
            "database_id": _field(sample, "id"),
            "uuid": _field(sample, "uuid"),
            "owner": _field(getattr(sample, "owner", None), "username"),
            "research_group": _field(getattr(sample, "research_group", None), "name"),
            "is_active": _field(sample, "is_active"),
            "created_at": _field(sample, "created_at"),
            "updated_at": _field(sample, "updated_at"),
            "files_count": _files_count(sample),
        })

    return row


def _get_queryset(request):
    qs = Sample.objects.all()

    valid_fields = {field.name for field in Sample._meta.fields}
    select_fields = [
        field for field in ["biobank", "owner", "research_group"]
        if field in valid_fields
    ]

    if select_fields:
        qs = qs.select_related(*select_fields)

    qs = qs.prefetch_related("collections", "tags", "keywords")

    include_inactive = request.GET.get("include_inactive") in ["1", "true", "True", "yes"]
    if not include_inactive and "is_active" in valid_fields:
        qs = qs.filter(is_active=True)

    sample_type = request.GET.get("sample_type")
    if sample_type:
        qs = qs.filter(sample_type=sample_type)

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)

    biobank = request.GET.get("biobank")
    if biobank:
        if biobank.isdigit():
            qs = qs.filter(biobank_id=int(biobank))
        else:
            qs = qs.filter(biobank__name__iexact=biobank)

    collection = request.GET.get("collection")
    if collection:
        if collection.isdigit():
            qs = qs.filter(collections__id=int(collection))
        else:
            qs = qs.filter(collections__name__iexact=collection)

    search = request.GET.get("q")
    if search:
        qs = qs.filter(sample_id__icontains=search) | qs.filter(organism_name__icontains=search)

    return qs.distinct().order_by("sample_type", "sample_id")


def export_samples_table(request):
    schema = request.GET.get("schema", "standard")
    file_format = request.GET.get("format", "csv")

    if schema not in ["standard", "full"]:
        schema = "standard"

    columns = list(STANDARD_COLUMNS)
    if schema == "full":
        columns = FULL_EXTRA_COLUMNS + columns

    rows = [_sample_to_row(sample, schema=schema) for sample in _get_queryset(request)]

    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"samples_export_{schema}_{timestamp}"

    if file_format == "xlsx":
        output = BytesIO()
        df = pd.DataFrame(rows, columns=columns)

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="samples")
            pd.DataFrame({
                "field": columns,
                "description": [_field_description(col) for col in columns],
            }).to_excel(writer, index=False, sheet_name="schema")

        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return response

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'

    writer = csv.DictWriter(response, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})

    return response


def _field_description(field):
    descriptions = {
        "sample_id": "Stable external identifier or barcode.",
        "sample_type": "Sample type: Bacterium (Host), Phage (Virus), Plasmid or Other.",
        "organism_name": "Display name used in the inventory.",
        "status": "Current sample status in the biobank workflow.",
        "biobank": "Physical biobank where the sample is stored.",
        "collections": "One or more logical collections separated by semicolon.",
        "storage_location": "Free-text or structured storage path.",
        "provider": "User or collaborator associated with the sample.",
        "is_public": "Whether the sample is public in the platform.",
        "scientific_notes": "Scientific notes or ELN-style notes.",
        "notes": "General internal notes.",
        "tags": "Tags separated by semicolon.",
        "keywords": "Keywords separated by semicolon.",
        "database_id": "Internal database primary key.",
        "uuid": "Internal UUID used by the system.",
        "owner": "Sample owner username.",
        "research_group": "Research group linked to the sample.",
        "is_active": "Whether the record is active.",
        "created_at": "Creation timestamp.",
        "updated_at": "Last update timestamp.",
        "files_count": "Number of files linked to the sample.",
    }
    return descriptions.get(field, "Subtype-specific or optional sample metadata field.")
