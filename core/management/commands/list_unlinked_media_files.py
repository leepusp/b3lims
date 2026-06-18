import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models.samples.sample_files import SampleFile


def classify_media_file(relative_path, mime_type):
    rel = str(relative_path).lower()
    mime = str(mime_type or "").lower()

    if rel.startswith("shipment_documents/") or rel.startswith("shipments/documents/"):
        return "shipment_document"

    if rel.startswith("sample_imports/"):
        return "import_file"

    if mime.startswith("image/") or rel.endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff")):
        return "image"

    if rel.endswith((".csv", ".tsv", ".xlsx", ".xls")):
        return "table"

    if rel.endswith((".fasta", ".fa", ".fastq", ".fq", ".gb", ".gbk")):
        return "sequence"

    if rel.endswith(".pdf") or mime == "application/pdf":
        return "pdf"

    if rel.endswith((".pdb", ".cif", ".mmcif")):
        return "structure"

    return "raw"


class Command(BaseCommand):
    help = "List MEDIA_ROOT files that are not linked to any SampleFile record."

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-linked",
            action="store_true",
            help="Show linked and unlinked files.",
        )
        parser.add_argument(
            "--category",
            default="",
            help="Optional category filter, for example pdf, image, table, sequence, shipment_document.",
        )

    def handle(self, *args, **options):
        inventory_path = Path(settings.BIOBANK_INVENTORY_ROOT) / "media_files_index.tsv"

        if not inventory_path.exists():
            raise CommandError(
                f"Media index not found: {inventory_path}. "
                "Run: python manage.py sync_biobank_inventory"
            )

        linked_paths = set(SampleFile.objects.values_list("file", flat=True))

        with inventory_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = list(reader)

        self.stdout.write(
            "\t".join(
                [
                    "status",
                    "category",
                    "relative_path",
                    "size_bytes",
                    "mime_type",
                    "sha256",
                ]
            )
        )

        shown = 0

        for row in rows:
            relative_path = row.get("relative_path", "")
            mime_type = row.get("mime_type", "")
            category = classify_media_file(relative_path, mime_type)
            status = "linked" if relative_path in linked_paths else "unlinked"

            if not options["include_linked"] and status == "linked":
                continue

            if options["category"] and category != options["category"]:
                continue

            self.stdout.write(
                "\t".join(
                    [
                        status,
                        category,
                        relative_path,
                        row.get("size_bytes", ""),
                        mime_type,
                        row.get("sha256", ""),
                    ]
                )
            )
            shown += 1

        self.stderr.write(f"Rows shown: {shown}")
