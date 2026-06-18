from django.core.management.base import BaseCommand

from core.models.samples.sample_files import SampleFile


class Command(BaseCommand):
    help = "List curated SampleFile records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sample-id",
            default="",
            help="Optional sample_id filter.",
        )

    def handle(self, *args, **options):
        qs = SampleFile.objects.select_related("sample").all().order_by(
            "sample__sample_id",
            "category",
            "file",
        )

        if options["sample_id"]:
            qs = qs.filter(sample__sample_id=options["sample_id"])

        self.stdout.write(
            "\t".join(
                [
                    "id",
                    "sample_id",
                    "category",
                    "file",
                    "file_size",
                    "mime_type",
                    "uploaded_at",
                    "description",
                ]
            )
        )

        for item in qs:
            self.stdout.write(
                "\t".join(
                    [
                        str(item.id),
                        item.sample.sample_id,
                        item.category or "",
                        item.file.name,
                        str(item.file_size or ""),
                        item.mime_type or "",
                        item.uploaded_at.isoformat() if item.uploaded_at else "",
                        (item.description or "").replace("\n", " "),
                    ]
                )
            )
