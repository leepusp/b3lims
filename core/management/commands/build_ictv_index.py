from django.core.management.base import BaseCommand, CommandError

from core.services import ictv_local


class Command(BaseCommand):
    help = "Build the local ICTV species index (SQLite) from the Virus Metadata Resource spreadsheet."

    def add_arguments(self, parser):
        parser.add_argument("--vmr", help="VMR_MSL*.xlsx file (default: the newest under settings.BIOBANK_ICTV_DIR/*/)")
        parser.add_argument("--output", help="SQLite file to write (default: <repository>/index/ictv.sqlite)")

    def handle(self, *args, **options):
        try:
            summary = ictv_local.build_index(options.get("vmr"), options.get("output"))
        except (FileNotFoundError, ValueError, OSError) as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(
            f"Indexed {summary['species']} ICTV species ({summary['phages']} infecting bacteria or archaea) from {summary['release']} -> {summary['path']}"
        ))
