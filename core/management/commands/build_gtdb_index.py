from django.core.management.base import BaseCommand, CommandError

from core.services import gtdb_local


class Command(BaseCommand):
    help = "Build the local GTDB species summary (SQLite) from the bac120 metadata used by the internal repository."

    def add_arguments(self, parser):
        parser.add_argument("--metadata", help="bac120_metadata_r*.tsv(.gz) file (default: the newest under settings.BIOBANK_GTDB_DIR)")
        parser.add_argument("--output", help="SQLite file to write (default: <repository>/index/gtdb.sqlite)")

    def handle(self, *args, **options):
        try:
            summary = gtdb_local.build_index(options.get("metadata"), options.get("output"))
        except (FileNotFoundError, OSError) as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(
            f"Indexed {summary['species']} GTDB species from {summary['genomes']} genomes ({summary['release']}) -> {summary['path']}"
        ))
