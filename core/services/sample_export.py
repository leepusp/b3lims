from io import BytesIO
import csv

import pandas as pd
from django.http import HttpResponse
from django.utils import timezone

from django.core.exceptions import PermissionDenied
from core.models import Sample
from core.services.sample_intake import COLUMN_ALIASES
from core.permissions.samples import visible_samples_for_user


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
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
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
    data = {}

    subtype_columns = STANDARD_COLUMNS[
        STANDARD_COLUMNS.index("genus"):
    ]

    subtype = _related(sample, [
        "bacteria",
        "bacterium",
        "phage",
        "plasmid",
    ])

    if subtype is None:
        return data

    for column in subtype_columns:
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
        "collection": _many_to_text(sample, "collections"),
        "research_group": _field(getattr(sample, "research_group", None), "name"),
        "biosafety_level": _field(sample, "biosafety_level"),
        "storage_location": _field(sample, "storage_location"),
        "provider": _field(getattr(sample, "owner", None), "username"),
        "is_public": _field(sample, "is_public"),
        "scientific_notes": _field(sample, "scientific_notes"),
        "notes": _field(sample, "notes"),
        "tags": _many_to_text(sample, "tags"),
        "keywords": _many_to_text(sample, "keywords"),
    }

    row.update(subtype_data)
    row.update({k: _stringify(v) for k, v in (getattr(sample, "type_data", None) or {}).items()})

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
    qs = visible_samples_for_user(request.user)

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




def _template_preset_from_request(request):
    """Resolve optional institutional defaults with authorization."""

    from core.models import Biobank, Collection
    from core.permissions.biobanks import (
        editable_biobanks_for_user,
    )
    from core.permissions.samples import (
        editable_sample_collections_for_user,
    )

    selected = {
        "biobank": request.GET.get("biobank_id", "").strip(),
        "collection": request.GET.get("collection_id", "").strip(),
    }

    if not any(selected.values()):
        raise ValueError(
            "Select a Biobank or Collection for this template."
        )

    presets = {}

    options = (
        (
            "biobank",
            Biobank,
            editable_biobanks_for_user,
        ),
        (
            "collection",
            Collection,
            editable_sample_collections_for_user,
        ),
    )

    for field, model, permission_queryset in options:
        value = selected[field]

        if not value:
            continue

        if (
            not value.isascii()
            or not value.isdecimal()
            or len(value) > 19
            or int(value) < 1
        ):
            raise ValueError(
                "Invalid institutional selection."
            )

        entity = (
            permission_queryset(request.user)
            .filter(pk=int(value))
            .first()
        )

        if entity is None:
            raise PermissionDenied(
                "You cannot use the selected "
                "institutional entity."
            )

        # Intake currently resolves entities by name.
        # Refuse ambiguous names instead of selecting
        # the wrong institutional record.
        if model.objects.filter(
            name__iexact=entity.name,
            is_active=True,
        ).count() != 1:
            raise ValueError(
                f"Ambiguous {field} name. "
                "Use the generic template and resolve "
                "the institution during review."
            )

        presets[field] = entity.name

    return presets


def _export_import_template(file_format, presets=None):
    """Generate the official B3 LIMS intake template."""

    columns = list(COLUMN_ALIASES)
    filename = "b3lims_sample_import_template_v8151"

    if presets:
        filename += "_preconfigured"

    preset_rows = [
        {
            column: presets.get(column, "")
            for column in columns
        }
        for _ in range(100)
    ] if presets else []

    if file_format == "csv":
        response = HttpResponse(
            content_type="text/csv; charset=utf-8"
        )

        response["Content-Disposition"] = (
            f'attachment; filename="{filename}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(columns)

        for row in preset_rows:
            writer.writerow([
                row[column]
                for column in columns
            ])

        return response

    if file_format != "xlsx":
        return HttpResponse(
            "Use csv or xlsx.",
            status=400,
            content_type="text/plain",
        )

    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    output = BytesIO()

    dictionary = []

    descriptions = {
        "sample_id": "Required. Unique external Sample identifier.",
        "sample_type": "Required. Select a supported Sample type.",
        "organism_name": "Organism or biological material identification.",
        "biobank": "Requested Biobank; validated by the receiving team.",
        "collection": "Requested Collection; validated by the receiving team.",
        "provider": "External provider or collaborator.",
        "research_group": "Requested research group.",
        "storage_location": "Optional. Requires internal storage validation.",
        "is_public": "Use true or false. Blank means private.",
        "scientific_notes": "Scientific observations.",
    }

    for column in columns:
        dictionary.append({
            "field": column,
            "required": (
                "Yes"
                if column in {"sample_id", "sample_type"}
                else "Conditional / optional"
            ),
            "description": descriptions.get(
                column,
                "Optional subtype-specific or intake metadata.",
            ),
        })

    instructions = [
        ("1", "Complete the samples worksheet."),
        ("2", "Keep the column headers unchanged."),
        ("3", "Enter one Sample per row."),
        ("4", "Keep sample_id as text, preserving leading zeros."),
        ("5", "Use allowed sample_type values."),
        ("6", "Leave non-applicable fields blank."),
        ("7", "Do not enter passwords or sensitive credentials."),
        ("8", "The upload stages records; it does not create Samples."),
        ("9", "The receiving team assigns internal ownership."),
        ("10", "Public visibility and physical storage require review."),
    ]

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(
            preset_rows,
            columns=columns,
        ).to_excel(
            writer,
            sheet_name="samples",
            index=False,
        )

        pd.DataFrame(dictionary).to_excel(
            writer,
            sheet_name="field_dictionary",
            index=False,
        )

        pd.DataFrame({
            "sample_type": [
                "Bacterium (Host)",
                "Phage (Virus)",
                "Plasmid",
                "Other",
            ],
            "is_public": [
                "false",
                "true",
                "",
                "",
            ],
        }).to_excel(
            writer,
            sheet_name="allowed_values",
            index=False,
        )

        pd.DataFrame(
            instructions,
            columns=["step", "instruction"],
        ).to_excel(
            writer,
            sheet_name="instructions",
            index=False,
        )

        ws = writer.sheets["samples"]
        ws.freeze_panes = "A2"

        for cell in ws[1]:
            cell.font = Font(
                bold=True,
                color="FFFFFF",
            )
            cell.fill = PatternFill(
                fill_type="solid",
                fgColor="17365D",
            )

        for position, name in enumerate(columns, start=1):
            letter = ws.cell(1, position).column_letter

            ws.column_dimensions[letter].width = min(
                max(len(name) + 4, 18),
                34,
            )

            # Preset templates contain exactly 100 entry rows.
            # Avoid creating additional formatted empty rows.
            # Generic templates retain 200 optional entry rows.
            last_row = 101 if presets else 201

            for row in range(2, last_row + 1):
                ws.cell(row, position).number_format = "@"

        type_column = ws.cell(
            1, columns.index("sample_type") + 1
        ).column_letter

        allowed_types = DataValidation(
            type="list",
            formula1=(
                '"Bacterium (Host),Phage (Virus),'
                'Plasmid,Other"'
            ),
            allow_blank=True,
        )

        allowed_types.showErrorMessage = True
        allowed_types.error = (
            "Select one of the supported Sample types."
        )

        ws.add_data_validation(allowed_types)
        allowed_types.add(
            f"{type_column}2:{type_column}201"
        )

        public_column = ws.cell(
            1, columns.index("is_public") + 1
        ).column_letter

        public_values = DataValidation(
            type="list",
            formula1='"false,true"',
            allow_blank=True,
        )

        ws.add_data_validation(public_values)
        public_values.add(
            f"{public_column}2:{public_column}201"
        )

    response = HttpResponse(
        output.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}.xlsx"'
    )

    return response


def export_samples_table(request):
    if request.method not in {"GET", "POST"}:
        return HttpResponse(
            "Method not allowed.",
            status=405,
            content_type="text/plain",
        )

    params = (
        request.POST
        if request.method == "POST"
        else request.GET
    )

    schema = params.get("schema", "standard")
    file_format = params.get("format", "csv")

    if file_format not in {"csv", "xlsx"}:
        return HttpResponse(
            "Unsupported export format.",
            status=400,
            content_type="text/plain",
        )

    if request.method == "POST" and schema == "template":
        return HttpResponse(
            "Template downloads require GET.",
            status=400,
            content_type="text/plain",
        )

    if schema == "template":
        presets = None

        if params.get("preset") == "1":
            try:
                presets = _template_preset_from_request(request)
            except ValueError as exc:
                return HttpResponse(
                    str(exc),
                    status=400,
                    content_type="text/plain",
                )

        from core.permissions.biobanks import editable_biobanks_for_user
        from core.permissions.samples import editable_sample_collections_for_user
        from core.services import sample_tables, sample_template

        sample_type = sample_tables.type_for_slug(params.get("type", ""))

        if params.get("type", "").strip() and sample_type is None:
            return HttpResponse(
                "Unknown Sample type for this template.",
                status=400,
                content_type="text/plain",
            )

        def names(queryset):
            return list(
                queryset.filter(is_active=True).order_by("name").values_list("name", flat=True)
            )

        return sample_template.template_response(
            file_format,
            sample_type=sample_type,
            presets=presets,
            biobanks=names(editable_biobanks_for_user(request.user)),
            collections=names(editable_sample_collections_for_user(request.user)),
        )

    if schema not in ["standard", "full"]:
        schema = "standard"

    from core.services import sample_tables

    typed = sample_tables.type_for_slug(params.get("sample_type", "")) or params.get("sample_type", "").strip()
    typed = typed if typed in sample_tables.all_type_names() else None

    columns = list(STANDARD_COLUMNS)
    if typed and schema == "standard":
        # One Sample type: exactly the columns of its import template, so the file can be edited and imported again.
        columns = [c.key for c in sample_tables.columns_for(typed)]
    if schema == "full":
        columns = FULL_EXTRA_COLUMNS + columns

    queryset = _get_queryset(request)

    if request.method == "POST":
        raw_ids = request.POST.getlist("sample_ids")

        if not raw_ids or len(raw_ids) > 500:
            return HttpResponse(
                "Select between 1 and 500 Samples.",
                status=400,
                content_type="text/plain",
            )

        if any(
            not value.isascii()
            or not value.isdecimal()
            or len(value) > 19
            or int(value) < 1
            for value in raw_ids
        ):
            return HttpResponse(
                "Invalid Sample selection.",
                status=400,
                content_type="text/plain",
            )

        selected_ids = [int(value) for value in raw_ids]

        if len(selected_ids) != len(set(selected_ids)):
            return HttpResponse(
                "Duplicate Sample identifiers in selection.",
                status=400,
                content_type="text/plain",
            )

        # Authorization is rechecked against the current
        # database state, not trusted from browser checkboxes.
        queryset = queryset.filter(pk__in=selected_ids)

        if queryset.count() != len(selected_ids):
            raise PermissionDenied(
                "One or more selected Samples are not visible."
            )

    rows = [
        _sample_to_row(sample, schema=schema)
        for sample in queryset
    ]

    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"samples_export_{schema}_{timestamp}"

    if file_format == "xlsx":
        output = BytesIO()
        df = pd.DataFrame(rows, columns=columns)

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="samples")
            specs = sample_tables.by_key()
            pd.DataFrame({
                "field": columns,
                "data type": [sample_tables.type_label(specs[c]) if c in specs else "" for c in columns],
                "allowed values": [", ".join(specs[c].choices) if c in specs else "" for c in columns],
                "description": [specs[c].help if c in specs and specs[c].help else _field_description(c) for c in columns],
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
