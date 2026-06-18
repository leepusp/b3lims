import hashlib
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models

from core.models.samples.sample import Sample


def notebook_attachment_upload_to(instance, filename):
    entry_id = instance.entry_id or "unassigned"
    safe_name = Path(filename).name
    return f"notebook/entries/{entry_id}/attachments/{uuid.uuid4().hex}_{safe_name}"


class NotebookEntry(models.Model):
    """
    Electronic lab notebook entry.

    The free-text content remains available for backward compatibility, while
    structured blocks provide tables, images, code, sequence/plasmid records,
    Slurm job references, and sample-linked snapshots.
    """
    ENTRY_TYPE_CHOICES = [
        ("experiment", "Experiment"),
        ("protocol", "Protocol"),
        ("analysis", "Analysis"),
        ("inventory", "Inventory"),
        ("meeting", "Meeting / discussion"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("in_progress", "In progress"),
        ("completed", "Completed"),
        ("reviewed", "Reviewed"),
        ("archived", "Archived"),
    ]

    VISIBILITY_CHOICES = [
        ("private", "Private"),
        ("lab", "Lab"),
        ("shared", "Shared"),
    ]

    title = models.CharField(max_length=255, default="Untitled experiment")
    content = models.TextField(blank=True)
    protocol_content = models.TextField(blank=True)

    entry_type = models.CharField(
        max_length=32,
        choices=ENTRY_TYPE_CHOICES,
        default="experiment",
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="draft",
    )
    project = models.CharField(max_length=255, blank=True)
    experiment_date = models.DateField(null=True, blank=True)
    visibility = models.CharField(
        max_length=32,
        choices=VISIBILITY_CHOICES,
        default="private",
    )

    mentions = models.ManyToManyField(
        Sample,
        related_name="notebook_mentions",
        blank=True,
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="core_notebook_entries",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Notebook Entry"
        verbose_name_plural = "Notebook Entries"

    def __str__(self):
        return f"{self.title} - {self.author.username}"


class NotebookSampleLink(models.Model):
    """
    Explicit link between a notebook entry and a sample.

    snapshot_json preserves the sample state at the time it was linked, while
    the sample foreign key keeps a live reference to the current sample record.
    """
    entry = models.ForeignKey(
        NotebookEntry,
        on_delete=models.CASCADE,
        related_name="sample_links",
    )
    sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name="notebook_sample_links",
    )
    snapshot_json = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notebook_sample_links_created",
    )
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-linked_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "sample"],
                name="unique_notebook_entry_sample_link",
            )
        ]

    def __str__(self):
        return f"{self.entry_id} -> {self.sample_id}"


class NotebookBlock(models.Model):
    BLOCK_TYPE_CHOICES = [
        ("text", "Text"),
        ("image", "Image"),
        ("table", "Table"),
        ("code", "Code / plot"),
        ("sequence", "Sequence"),
        ("plasmid", "Plasmid"),
        ("slurm_job", "Slurm job"),
        ("attachment", "Attachment"),
    ]

    entry = models.ForeignKey(
        NotebookEntry,
        on_delete=models.CASCADE,
        related_name="blocks",
    )
    block_type = models.CharField(max_length=32, choices=BLOCK_TYPE_CHOICES)
    title = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)
    content_data = models.JSONField(default=dict, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notebook_blocks_created",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Notebook Block"
        verbose_name_plural = "Notebook Blocks"

    def __str__(self):
        return f"{self.entry_id} [{self.block_type}] {self.title or self.id}"


class NotebookAttachment(models.Model):
    ATTACHMENT_TYPE_CHOICES = [
        ("image", "Image"),
        ("table", "Table"),
        ("result", "Result"),
        ("sequence", "Sequence"),
        ("other", "Other"),
    ]

    entry = models.ForeignKey(
        NotebookEntry,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    block = models.ForeignKey(
        NotebookBlock,
        on_delete=models.SET_NULL,
        related_name="attachments",
        null=True,
        blank=True,
    )
    file = models.FileField(upload_to=notebook_attachment_upload_to)
    attachment_type = models.CharField(
        max_length=32,
        choices=ATTACHMENT_TYPE_CHOICES,
        default="other",
    )
    caption = models.CharField(max_length=255, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notebook_attachments_uploaded",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notebook Attachment"
        verbose_name_plural = "Notebook Attachments"

    def save(self, *args, **kwargs):
        if self.file and not self.checksum_sha256:
            try:
                hasher = hashlib.sha256()
                for chunk in self.file.chunks():
                    hasher.update(chunk)
                self.checksum_sha256 = hasher.hexdigest()
                self.file.seek(0)
            except Exception:
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return self.caption or Path(self.file.name).name


class NotebookSlurmJob(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    entry = models.ForeignKey(
        NotebookEntry,
        on_delete=models.CASCADE,
        related_name="slurm_jobs",
    )
    block = models.ForeignKey(
        NotebookBlock,
        on_delete=models.SET_NULL,
        related_name="slurm_jobs",
        null=True,
        blank=True,
    )

    job_name = models.CharField(max_length=255)
    job_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="draft")

    partition = models.CharField(max_length=64, blank=True)
    cpus = models.PositiveIntegerField(default=1)
    memory = models.CharField(max_length=32, blank=True)
    time_limit = models.CharField(max_length=32, blank=True)

    command = models.TextField(blank=True)
    workdir = models.CharField(max_length=1024, blank=True)
    script_path = models.CharField(max_length=1024, blank=True)
    stdout_path = models.CharField(max_length=1024, blank=True)
    stderr_path = models.CharField(max_length=1024, blank=True)

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notebook_slurm_jobs_submitted",
    )

    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_status_check_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Notebook Slurm Job"
        verbose_name_plural = "Notebook Slurm Jobs"

    def __str__(self):
        return f"{self.job_name} ({self.job_id or self.status})"


class MolecularSequence(models.Model):
    """
    Molecular sequence asset used by the ELN, samples, plasmid workspace and
    future cloning/design tools.

    This restores the previous MolecularSequence concept and extends it for
    DNA/RNA/protein/plasmid/primer records.
    """
    SEQUENCE_TYPE_CHOICES = [
        ("dna", "DNA"),
        ("rna", "RNA"),
        ("protein", "Protein"),
        ("plasmid", "Plasmid"),
        ("primer", "Primer"),
        ("insert", "Insert"),
        ("other", "Other"),
    ]

    TOPOLOGY_CHOICES = [
        ("linear", "Linear"),
        ("circular", "Circular"),
    ]

    name = models.CharField(max_length=255)
    sequence_type = models.CharField(
        max_length=32,
        choices=SEQUENCE_TYPE_CHOICES,
        default="dna",
    )
    topology = models.CharField(
        max_length=32,
        choices=TOPOLOGY_CHOICES,
        default="linear",
    )
    sequence = models.TextField(blank=True)
    description = models.TextField(blank=True)

    length = models.PositiveIntegerField(default=0)
    gc_content = models.FloatField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)

    features_json = models.JSONField(default=list, blank=True)

    linked_sample = models.ForeignKey(
        Sample,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="molecular_sequences",
    )
    source_entry = models.ForeignKey(
        NotebookEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="molecular_sequences",
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="molecular_sequences",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "Molecular Sequence"
        verbose_name_plural = "Molecular Sequences"

    def _clean_sequence(self):
        return "".join(str(self.sequence or "").split()).upper()

    def _compute_gc_content(self, sequence):
        if not sequence:
            return None

        if self.sequence_type not in {"dna", "rna", "plasmid", "primer", "insert"}:
            return None

        gc = sequence.count("G") + sequence.count("C")
        atgc = sum(sequence.count(base) for base in ["A", "T", "U", "G", "C"])

        if atgc == 0:
            return None

        return round((gc / atgc) * 100, 2)

    def save(self, *args, **kwargs):
        cleaned = self._clean_sequence()
        self.sequence = cleaned
        self.length = len(cleaned)
        self.gc_content = self._compute_gc_content(cleaned)

        if cleaned:
            self.checksum_sha256 = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        else:
            self.checksum_sha256 = ""

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.sequence_type}, {self.length} bp/aa)"
