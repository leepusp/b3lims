"""Excel and CSV import templates, one per Sample type, built from the column definitions in ``sample_tables``."""

from __future__ import annotations

import csv
from io import BytesIO

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from core.services import sample_tables as tables

GROUP_COLORS = {tables.IDENT: "17365D", tables.ORG: "1F6E43", tables.BIO: "6A3D9A", tables.LOGISTICS: "8A5A00"}
REQUIRED_COLOR = "A61E1E"
ENTRY_ROWS = 200
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NUMBER_FORMATS = {tables.TEXT: "@", tables.INTEGER: "0", tables.DECIMAL: "0.0##", tables.BOOLEAN: "@", tables.CHOICE: "@", tables.DATE: "yyyy-mm-dd", tables.LIST: "@"}


def filename_for(sample_type, preconfigured: bool) -> str:
    slug = tables.SLUG_OF.get(sample_type, "all_types")

    return f"b3lims_import_{slug}" + ("_preconfigured" if preconfigured else "")


def prefilled(columns, sample_type, presets) -> dict:
    values = dict(presets or {})

    if sample_type:
        values["sample_type"] = sample_type

    return {c.key: values.get(c.key, "") for c in columns}


def csv_response(columns, sample_type, presets, name):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{name}.csv"'
    writer = csv.writer(response)

    writer.writerow([c.key for c in columns])

    if presets:
        row = prefilled(columns, sample_type, presets)

        for _ in range(100):
            writer.writerow([row[c.key] for c in columns])

    return response


def xlsx_response(columns, sample_type, presets, biobanks, collections, name):
    book = Workbook()
    sheet = book.active
    sheet.title = "samples"
    lists = book.create_sheet("lists")
    refs = {}

    def add_list(title, values):
        column = lists.max_column + 1 if lists["A1"].value is not None else 1
        lists.cell(1, column, title).font = Font(bold=True)

        for i, value in enumerate(values, start=2):
            lists.cell(i, column, value)

        letter = get_column_letter(column)
        lists.column_dimensions[letter].width = max(14, len(title) + 2)

        return f"lists!${letter}$2:${letter}${max(len(values), 1) + 1}"

    refs["biobank"] = add_list("biobank", biobanks or [""])
    refs["collection"] = add_list("collection", collections or [""])

    for column in columns:
        if column.kind == tables.CHOICE and column.choices:
            refs[column.key] = add_list(column.key, list(column.choices))

    last = (100 if presets else ENTRY_ROWS) + 1
    values = prefilled(columns, sample_type, presets)
    sheet.freeze_panes = "B2"
    sheet.row_dimensions[1].height = 24

    for position, column in enumerate(columns, start=1):
        head = sheet.cell(1, position, column.key)
        head.font = Font(bold=True, color="FFFFFF")
        head.fill = PatternFill("solid", fgColor=REQUIRED_COLOR if column.required else GROUP_COLORS[column.group])
        head.alignment = Alignment(vertical="center", wrap_text=True)
        note = [column.help, "", "Type: " + tables.type_label(column)]

        if column.choices:
            note.append("Allowed: " + ", ".join(column.choices))

        note.append("Required." if column.required else "Optional.")
        head.comment = Comment("\n".join(n for n in note if n is not None), "B3 LIMS", width=300, height=140)
        sheet.column_dimensions[get_column_letter(position)].width = max(column.width, len(column.key) + 4)

        letter = get_column_letter(position)

        for row in range(2, last + 1):
            cell = sheet.cell(row, position)
            cell.number_format = NUMBER_FORMATS[column.kind]

            if values[column.key]:
                cell.value = values[column.key]

        rule = None
        strict_error = column.strict and column.kind == tables.CHOICE

        if column.key in refs:
            rule = DataValidation(type="list", formula1="=" + refs[column.key], allow_blank=True)
            rule.errorStyle = "stop" if strict_error else "warning"
            rule.error = f"Pick a value from the list for {column.key}." if strict_error else "This value is not in the list. Keep it only if you are sure."
            rule.errorTitle = column.key
        elif column.kind == tables.BOOLEAN:
            rule = DataValidation(type="list", formula1='"true,false"', allow_blank=True)
            rule.error, rule.errorTitle = "Use true or false.", column.key
        elif column.kind == tables.INTEGER:
            rule = DataValidation(type="whole", operator="greaterThanOrEqual", formula1=str(int(column.minimum or 0)), allow_blank=True)
            rule.error, rule.errorTitle = "Enter a whole number, digits only.", column.key
        elif column.kind == tables.DECIMAL:
            rule = DataValidation(type="decimal", operator="between", formula1=str(column.minimum if column.minimum is not None else -1e6), formula2=str(column.maximum if column.maximum is not None else 1e9), allow_blank=True)
            rule.error, rule.errorTitle = "Enter a number (decimal point) in the expected range.", column.key
        elif column.kind == tables.DATE:
            rule = DataValidation(type="date", operator="greaterThan", formula1="36526", allow_blank=True)
            rule.error, rule.errorTitle = "Enter a date such as 2026-12-01.", column.key

        if rule is not None:
            rule.showErrorMessage = True
            rule.showInputMessage = True
            rule.promptTitle = column.key
            rule.prompt = column.help[:250]
            sheet.add_data_validation(rule)
            rule.add(f"{letter}2:{letter}{last}")

    sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}1"

    example = book.create_sheet("example", 1)
    example.append([c.key for c in columns])
    shown = [sample_type] if sample_type else [tables.BACTERIUM, tables.PHAGE, tables.PLASMID]

    for kind in shown:
        example.append([tables.example_row(kind, columns)[c.key] for c in columns])

    for position, column in enumerate(columns, start=1):
        example.cell(1, position).font = Font(bold=True)
        example.column_dimensions[get_column_letter(position)].width = max(column.width, len(column.key) + 4)

    dictionary = book.create_sheet("field_dictionary", 2)
    dictionary.append(["field", "group", "required", "data type", "allowed values", "example", "description"])

    for column in columns:
        sample = next((v for v in column.example.values() if v), "")
        dictionary.append([column.key, column.group, "Yes" if column.required else "No", tables.type_label(column), ", ".join(column.choices), sample, column.help])

    for position, width in enumerate([26, 22, 10, 28, 40, 28, 70], start=1):
        dictionary.column_dimensions[get_column_letter(position)].width = width
        dictionary.cell(1, position).font = Font(bold=True)

    steps = [
        ("1", "Fill the samples sheet: one Sample per row. The example sheet shows how each column looks when filled."),
        ("2", "Keep the column headers unchanged. Hover a header to read its help, type and allowed values."),
        ("3", "Dark red headers are required. Blue, green, purple and brown headers are optional groups."),
        ("4", "Choice columns have a drop-down list. Numbers accept digits only, yes/no columns accept true or false, dates use YYYY-MM-DD."),
        ("5", "Several resistance markers go in one cell separated by commas."),
        ("6", "Leave columns that do not apply to your Sample blank."),
        ("7", "The upload only stages the rows for review. Samples are created when you confirm each row."),
        ("8", "Do not enter passwords or sensitive credentials."),
    ]

    if sample_type is None:
        steps.insert(1, ("1b", "This template has the columns of every Sample type. Columns that do not apply to a row's sample_type are ignored."))

    instructions = book.create_sheet("instructions", 3)
    instructions.append(["step", "instruction"])
    instructions.column_dimensions["B"].width = 120

    for row in steps:
        instructions.append(list(row))

    output = BytesIO()
    book.save(output)

    response = HttpResponse(output.getvalue(), content_type=XLSX)
    response["Content-Disposition"] = f'attachment; filename="{name}.xlsx"'

    return response


def template_response(file_format, sample_type=None, presets=None, biobanks=None, collections=None):
    columns = tables.columns_for(sample_type)
    name = filename_for(sample_type, bool(presets))

    if file_format == "csv":
        return csv_response(columns, sample_type, presets, name)

    if file_format != "xlsx":
        return HttpResponse("Use csv or xlsx.", status=400, content_type="text/plain")

    return xlsx_response(columns, sample_type, presets, biobanks, collections, name)
