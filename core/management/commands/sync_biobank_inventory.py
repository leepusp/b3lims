from django.core.management.base import BaseCommand

from core.services.sample_inventory_storage import sync_all_sample_inventory


class Command(BaseCommand):
    help = "Synchronize shared Biobank sample inventory manifests and media file index."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-checksums",
            action="store_true",
            help="Skip SHA256 checksum calculation for faster indexing.",
        )

    def handle(self, *args, **options):
        compute_checksums = not options["no_checksums"]

        result = sync_all_sample_inventory(
            compute_file_checksums=compute_checksums,
        )

        self.stdout.write(self.style.SUCCESS("Biobank inventory synchronized."))
        self.stdout.write(f"Sample count: {result['sample_count']}")
        self.stdout.write(f"Samples TSV: {result['samples_index']['tsv_path']}")
        self.stdout.write(f"Samples JSON: {result['samples_index']['json_path']}")
        self.stdout.write(f"Media index: {result['media_files_index']['path']}")
        self.stdout.write(f"Media file count: {result['media_files_index']['file_count']}")
        self.stdout.write(f"Generated at: {result['generated_at']}")
