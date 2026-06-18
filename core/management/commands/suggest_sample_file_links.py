import csv
import re
import shlex
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.management.commands.list_unlinked_media_files import classify_media_file
from core.models.samples.sample import Sample
from core.models.samples.sample_files import SampleFile


STOPWORDS = {
    "data",
    "sample",
    "samples",
    "unassigned",
    "shipment",
    "shipments",
    "documents",
    "document",
    "signed",
    "import",
    "imports",
    "minimal",
    "test",
    "raw",
    "pdf",
    "csv",
    "xlsx",
    "xls",
    "tif",
    "tiff",
    "pdb",
    "txt",
    "legacy",
    "content",
    "declaration",
    "sender",
    "mta",
    "ttm",
    "2024",
    "2025",
    "2026",
    "2027",
    "bac",
    "pla",
    "pha",
    "virus",
    "host",
    "bacterium",
    "plasmid",
    "phage",
}


def normalize_text(value):
    value = str(value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return value.strip()


def tokens(value):
    result = set()
    for token in normalize_text(value).split():
        if len(token) < 3:
            continue
        if token in STOPWORDS:
            continue
        if token.isdigit() and 1900 <= int(token) <= 2100:
            continue
        result.add(token)
    return result


def sample_text(sample):
    parts = [
        sample.sample_id,
        sample.sample_type,
        sample.organism_name,
        sample.storage_location,
        sample.notes,
        sample.scientific_notes,
    ]

    for rel_name in ["biobank", "owner", "research_group"]:
        obj = getattr(sample, rel_name, None)
        if obj is not None:
            parts.append(str(obj))

    return " ".join(str(part or "") for part in parts)


def score_file_against_sample(relative_path, sample):
    rel_norm = normalize_text(relative_path)
    sample_id_norm = normalize_text(sample.sample_id).replace(" ", "")

    score = 0
    reasons = []

    compact_rel = rel_norm.replace(" ", "")

    if sample_id_norm and sample_id_norm in compact_rel:
        score += 100
        reasons.append("sample_id")

    file_tokens = tokens(relative_path)
    sample_tokens = tokens(sample_text(sample))

    overlap = sorted(file_tokens & sample_tokens)

    if overlap:
        score += len(overlap) * 10
        reasons.extend(overlap)

    # Plasmid names like pET-28a are often split into pet and 28a.
    if sample.sample_type and "plasmid" in sample.sample_type.casefold():
        if {"pet", "28a"} <= file_tokens and {"pet", "28a"} <= sample_tokens:
            score += 40
            reasons.append("plasmid_name_pet_28a")

    return score, sorted(set(reasons))


class Command(BaseCommand):
    help = "Suggest possible SampleFile links from indexed MEDIA_ROOT files to existing samples."

    def add_arguments(self, parser):
        parser.add_argument(
            "--top",
            type=int,
            default=5,
            help="Maximum suggestions per unlinked file.",
        )
        parser.add_argument(
            "--min-score",
            type=int,
            default=10,
            help="Minimum score to display a suggestion.",
        )
        parser.add_argument(
            "--include-linked",
            action="store_true",
            help="Also suggest links for files already linked.",
        )
        parser.add_argument(
            "--category",
            default="",
            help="Optional category filter, for example pdf, image, table, sequence.",
        )

    def handle(self, *args, **options):
        inventory_path = Path(settings.BIOBANK_INVENTORY_ROOT) / "media_files_index.tsv"

        if not inventory_path.exists():
            raise CommandError(
                f"Media index not found: {inventory_path}. "
                "Run: python manage.py sync_biobank_inventory"
            )

        linked_paths = set(SampleFile.objects.values_list("file", flat=True))
        samples = list(Sample.objects.all().order_by("sample_id", "id"))

        with inventory_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = list(reader)

        self.stdout.write(
            "\t".join(
                [
                    "relative_path",
                    "category",
                    "sample_id",
                    "score",
                    "matched_terms",
                    "sample_type",
                    "organism_name",
                    "link_command",
                ]
            )
        )

        shown = 0

        for row in rows:
            relative_path = row.get("relative_path", "")
            mime_type = row.get("mime_type", "")
            category = classify_media_file(relative_path, mime_type)

            if not options["include_linked"] and relative_path in linked_paths:
                continue

            if options["category"] and category != options["category"]:
                continue

            suggestions = []

            for sample in samples:
                score, reasons = score_file_against_sample(relative_path, sample)

                if score >= options["min_score"]:
                    suggestions.append((score, reasons, sample))

            suggestions.sort(key=lambda item: (-item[0], item[2].sample_id))

            for score, reasons, sample in suggestions[: options["top"]]:
                command = (
                    "python manage.py link_sample_file "
                    f"{shlex.quote(sample.sample_id)} "
                    f"{shlex.quote(relative_path)} "
                    f"--category {shlex.quote(category if category in ['raw', 'image', 'table', 'sequence', 'pdf'] else 'raw')} "
                    f"--description {shlex.quote('Curated link suggested from media index; review before treating as final.')}"
                )

                self.stdout.write(
                    "\t".join(
                        [
                            relative_path,
                            category,
                            sample.sample_id,
                            str(score),
                            ",".join(reasons),
                            sample.sample_type or "",
                            sample.organism_name or "",
                            command,
                        ]
                    )
                )
                shown += 1

        self.stderr.write(f"Suggestions shown: {shown}")
