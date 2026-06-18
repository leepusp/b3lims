from pathlib import Path
import mimetypes

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models.samples.sample import Sample
from core.models.samples.sample_files import SampleFile


class Command(BaseCommand):
    help = "Link an existing MEDIA_ROOT file to a Biobank sample using the existing SampleFile model."

    def add_arguments(self, parser):
        parser.add_argument("sample_id", help="Biobank sample_id, for example PLA-2026-5515.")
        parser.add_argument(
            "path",
            help=(
                "File path. Can be absolute or relative to MEDIA_ROOT. "
                "Example: _unassigned_samples/pla-2026-00001/pET-28a.pdf"
            ),
        )
        parser.add_argument(
            "--category",
            default="raw",
            choices=[choice[0] for choice in SampleFile._meta.get_field("category").choices],
            help="Sample file category.",
        )
        parser.add_argument(
            "--description",
            default="",
            help="Optional curation/linking note.",
        )

    def resolve_path(self, value):
        raw = Path(value)

        if raw.is_absolute():
            absolute_path = raw
            try:
                relative_path = absolute_path.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
            except ValueError as exc:
                raise CommandError(
                    f"Absolute file must be inside MEDIA_ROOT: {settings.MEDIA_ROOT}"
                ) from exc
        else:
            absolute_path = Path(settings.MEDIA_ROOT) / raw
            relative_path = raw.as_posix()

        if not absolute_path.exists():
            raise CommandError(f"File not found: {absolute_path}")

        if not absolute_path.is_file():
            raise CommandError(f"Path is not a file: {absolute_path}")

        max_length = SampleFile._meta.get_field("file").max_length
        if len(relative_path) > max_length:
            raise CommandError(
                f"Relative path is too long for SampleFile.file "
                f"({len(relative_path)} > {max_length}): {relative_path}"
            )

        return absolute_path, relative_path

    def handle(self, *args, **options):
        sample_id = options["sample_id"]
        input_path = options["path"]

        try:
            sample = Sample.objects.get(sample_id=sample_id)
        except Sample.DoesNotExist as exc:
            raise CommandError(f"Sample not found: {sample_id}") from exc

        absolute_path, relative_path = self.resolve_path(input_path)
        stat = absolute_path.stat()

        sample_file, created = SampleFile.objects.get_or_create(
            sample=sample,
            file=relative_path,
            defaults={
                "description": options["description"],
            },
        )

        sample_file.description = options["description"] or sample_file.description
        sample_file.mime_type = mimetypes.guess_type(absolute_path.name)[0] or sample_file.mime_type
        sample_file.file_size = stat.st_size
        sample_file.category = options["category"]
        sample_file.save()

        # SampleFile.save() auto-detects category from extension. Restore the requested
        # category if the user explicitly selected one.
        if options["category"]:
            SampleFile.objects.filter(pk=sample_file.pk).update(category=options["category"])
            sample_file.refresh_from_db()

        action = "Created" if created else "Updated"

        self.stdout.write(self.style.SUCCESS(f"{action} SampleFile link."))
        self.stdout.write(f"Sample: {sample.sample_id}")
        self.stdout.write(f"File: {sample_file.file.name}")
        self.stdout.write(f"Category: {sample_file.category}")
        self.stdout.write(f"MIME type: {sample_file.mime_type}")
        self.stdout.write(f"File size: {sample_file.file_size}")
