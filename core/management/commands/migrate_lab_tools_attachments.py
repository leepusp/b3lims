import hashlib
from pathlib import Path, PurePosixPath

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models.lab_tools.notebook import NotebookAttachment
from core.services.lab_tools_storage import (
    lab_tools_storage,
    validate_username,
)


class Command(BaseCommand):
    help = (
        "Copy legacy ELN attachments from shared MEDIA_ROOT storage "
        "into each entry author's protected Unix home."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Copy files and update attachment records.",
        )
        parser.add_argument(
            "--delete-source",
            action="store_true",
            help=(
                "Delete each legacy source only after its copy and "
                "database update succeed. Requires --apply."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        delete_source = options["delete_source"]

        if delete_source and not apply_changes:
            raise CommandError("--delete-source requires --apply.")

        attachments = (
            NotebookAttachment.objects
            .select_related("entry", "entry__author")
            .filter(file__startswith="notebook/")
            .order_by("id")
        )
        found = migrated = missing = 0

        for attachment in attachments.iterator():
            found += 1
            username = validate_username(
                attachment.entry.author.get_username()
            )
            legacy_name = attachment.file.name
            basename = Path(PurePosixPath(legacy_name).name).name
            destination_name = (
                f"users/{username}/eln/entries/"
                f"{attachment.entry_id}/attachments/{basename}"
            )

            if not attachment.file.storage.exists(legacy_name):
                missing += 1
                self.stderr.write(
                    f"MISSING attachment={attachment.id} "
                    f"source={legacy_name}"
                )
                continue

            if not apply_changes:
                self.stdout.write(
                    f"WOULD_MIGRATE attachment={attachment.id} "
                    f"user={username} destination={destination_name}"
                )
                continue

            with attachment.file.storage.open(legacy_name, "rb") as source:
                saved_name = lab_tools_storage.save(
                    destination_name,
                    File(source),
                    max_length=512,
                )

            if attachment.checksum_sha256:
                hasher = hashlib.sha256()
                with lab_tools_storage.open(saved_name, "rb") as copied:
                    for chunk in iter(
                        lambda: copied.read(1024 * 1024),
                        b"",
                    ):
                        hasher.update(chunk)

                if hasher.hexdigest() != attachment.checksum_sha256:
                    lab_tools_storage.delete(saved_name)
                    raise CommandError(
                        f"Checksum mismatch for attachment {attachment.id}."
                    )

            try:
                with transaction.atomic():
                    updated = NotebookAttachment.objects.filter(
                        pk=attachment.pk,
                        file=legacy_name,
                    ).update(file=saved_name)

                    if updated != 1:
                        raise CommandError(
                            "Attachment changed during migration: "
                            f"{attachment.id}."
                        )
            except Exception:
                lab_tools_storage.delete(saved_name)
                raise

            if delete_source:
                legacy_path = Path(
                    lab_tools_storage.path(legacy_name)
                )
                legacy_path.unlink(missing_ok=True)

            migrated += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"MIGRATED attachment={attachment.id} "
                    f"user={username} destination={saved_name}"
                )
            )

        mode = "APPLY" if apply_changes else "DRY_RUN"
        self.stdout.write(
            f"{mode} found={found} migrated={migrated} missing={missing}"
        )
