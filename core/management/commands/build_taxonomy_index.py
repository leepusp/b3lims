from django.core.management.base import BaseCommand, CommandError

from core.services import taxonomy_local


class Command(BaseCommand):
    help = "Build the local taxonomy index (SQLite) from the NCBI taxdump used by the internal repository."

    def add_arguments(self, parser):
        parser.add_argument("--taxdump", help="Directory with nodes.dmp and names.dmp (default: settings.BIOBANK_TAXONOMY_DIR)")
        parser.add_argument("--output", help="SQLite file to write (default: <repository>/index/taxonomy.sqlite)")

    def handle(self, *args, **options):
        try:
            summary = taxonomy_local.build_index(options.get("taxdump"), options.get("output"))
        except (FileNotFoundError, OSError) as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(
            f"Indexed {summary['nodes']} taxa (dump {summary['version']}) -> {summary['path']}"
        ))
