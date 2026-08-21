import mimetypes
import os
from pathlib import PurePosixPath

from django.db import models

from core.services.sample_data_storage import (
    sample_data_storage,
    sample_file_upload_name,
)

from .sample import Sample


def sample_file_upload_to(instance, filename):
    return sample_file_upload_name(
        instance.sample,
        filename,
    )


class SampleFile(models.Model):
    VIEW_CATEGORIES = [
        ("image", "Image (Microscopy/Gel)"),
        ("table", "Table (CSV/Excel)"),
        ("sequence", "Sequence (FASTA/FASTQ)"),
        ("pdf", "PDF Document"),
        ("raw", "Raw Data / Other"),
    ]

    sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name="files",
    )

    file = models.FileField(
        upload_to=sample_file_upload_to,
        storage=sample_data_storage,
        max_length=512,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    mime_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    file_size = models.BigIntegerField(
        blank=True,
        null=True,
    )

    category = models.CharField(
        max_length=20,
        choices=VIEW_CATEGORIES,
        default="raw",
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
    )

    def save(self, *args, **kwargs):
        if self.file:
            self.file_size = self.file.size

            guess, _ = mimetypes.guess_type(
                self.file.name
            )

            self.mime_type = guess

            ext = os.path.splitext(
                self.file.name
            )[1].lower()

            if ext in {
                ".jpg",
                ".jpeg",
                ".png",
                ".tif",
                ".tiff",
            }:
                self.category = "image"

            elif ext in {
                ".csv",
                ".xlsx",
                ".xls",
            }:
                self.category = "table"

            elif ext in {
                ".fasta",
                ".fastq",
                ".gb",
            }:
                self.category = "sequence"

            elif ext == ".pdf":
                self.category = "pdf"

        super().save(
            *args,
            **kwargs,
        )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    file__regex=(
                        r"^users/"
                        r"[A-Za-z0-9]"
                        r"[A-Za-z0-9_.-]{0,63}/"
                        r"samples/"
                        r"sample_[0-9]+_"
                        r"[A-Za-z0-9._-]+/"
                        r"files/"
                        r"[A-Za-z0-9]"
                        r"[A-Za-z0-9_.-]{0,254}$"
                    )
                ),
                name=(
                    "samplefile_file_strict_user_path"
                ),
            ),
        ]

    @property
    def filename(self):
        """Return only the user-facing file basename."""

        if not self.file:
            return ""

        return PurePosixPath(
            str(self.file.name)
        ).name

    def __str__(self):
        return (
            f"File for "
            f"{self.sample.sample_id} "
            f"({self.category})"
        )
