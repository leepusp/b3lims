from django.core.management.base import BaseCommand

from core.models import NotebookEntry, NotebookTemplate
from core.services import custom_field_layout as layout


class Command(BaseCommand):
    help = (
        "Copy custom fields from the old keys to the new ones. Use --prefer-old "
        "after a rollback, when edits made by the previous release only exist "
        "under the old keys."
    )

    def add_arguments(self, parser):
        parser.add_argument("--prefer-old", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        convert = layout.migrated_forced if options["prefer_old"] else layout.migrated
        changed = 0
        for model, attr in ((NotebookEntry, "metadata"), (NotebookTemplate, "structure")):
            for obj in model.objects.iterator(chunk_size=200):
                updated = convert(getattr(obj, attr))
                if updated is None:
                    continue
                changed += 1
                if not options["dry_run"]:
                    setattr(obj, attr, updated)
                    obj.save(update_fields=[attr])
        verb = "would update" if options["dry_run"] else "updated"
        self.stdout.write(f"{verb} {changed} rows")
