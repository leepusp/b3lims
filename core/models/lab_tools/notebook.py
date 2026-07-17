import hashlib
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models

from core.models.samples.sample import Sample
from core.models.chemicals.chemical import Chemical


def notebook_attachment_upload_to(instance, filename):
    entry_id = instance.entry_id or "unassigned"
    safe_name = Path(filename).name
    return f"notebook/entries/{entry_id}/attachments/{uuid.uuid4().hex}_{safe_name}"


def default_jupyter_notebook():
    """Return a minimal, valid Jupyter notebook document."""
    return {
        "cells": [],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


class NotebookEntry(models.Model):
    """
    Electronic lab notebook entry.

    The free-text content remains available for backward compatibility, while
    structured blocks provide tables, images, code, sequence/plasmid records,
    sample-linked snapshots, attachments, and molecular records.
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


class NotebookChemicalLink(models.Model):
    """
    Explicit link between a notebook entry and a Chemical inventory record.

    snapshot_json preserves the reagent state at the time it was linked, while
    the chemical foreign key keeps a live reference to the current inventory record.
    """
    entry = models.ForeignKey(
        NotebookEntry,
        on_delete=models.CASCADE,
        related_name="chemical_links",
    )
    chemical = models.ForeignKey(
        Chemical,
        on_delete=models.CASCADE,
        related_name="notebook_chemical_links",
    )
    snapshot_json = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notebook_chemical_links_created",
    )
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-linked_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "chemical"],
                name="unique_notebook_entry_chemical_link",
            )
        ]

    def __str__(self):
        return f"{self.entry_id} -> chemical:{self.chemical_id}"


class MolecularFeature(models.Model):
    """
    Editable sequence feature linked to a MolecularSequence.

    This is the persistent source of truth for SeqViz annotations,
    feature colors, coordinates, strand and notes.
    """
    FEATURE_TYPES = [
        ("promoter", "Promoter"),
        ("rbs", "RBS"),
        ("cds", "CDS / ORF / Insert"),
        ("terminator", "Terminator"),
        ("ori", "Origin"),
        ("antibiotic", "Antibiotic marker"),
        ("primer", "Primer binding site"),
        ("domain", "Protein domain"),
        ("utr", "UTR"),
        ("custom", "Custom"),
    ]

    STRANDS = [
        ("+", "Forward"),
        ("-", "Reverse"),
        (".", "Not applicable"),
    ]

    molecule = models.ForeignKey(
        "MolecularSequence",
        on_delete=models.CASCADE,
        related_name="features",
    )
    name = models.CharField(max_length=255)
    feature_type = models.CharField(max_length=32, choices=FEATURE_TYPES, default="custom")
    start = models.PositiveIntegerField(default=1)
    end = models.PositiveIntegerField(default=1)
    strand = models.CharField(max_length=1, choices=STRANDS, default="+")
    color = models.CharField(max_length=16, default="#868e96")
    notes = models.TextField(blank=True)
    qualifiers_json = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "start", "id"]

    def __str__(self):
        return f"{self.molecule_id}:{self.name} {self.start}-{self.end}"


class NotebookBlock(models.Model):
    BLOCK_TYPE_CHOICES = [
        ("protocol", "Protocol"),
        ("image", "Image"),
        ("table", "Table"),
        ("sequence", "Sequence"),
        ("plasmid", "Plasmid"),
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

class NotebookKernelDocument(models.Model):
    """Jupyter-compatible document attached to one ELN entry."""

    entry = models.OneToOneField(
        NotebookEntry,
        on_delete=models.CASCADE,
        related_name="kernel_document",
    )
    title = models.CharField(max_length=255, default="ELN analysis")
    notebook_json = models.JSONField(default=default_jupyter_notebook)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notebook_kernel_documents_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notebook_kernel_documents_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "ELN Jupyter Notebook"
        verbose_name_plural = "ELN Jupyter Notebooks"

    def __str__(self):
        return f"{self.entry_id}: {self.title}"


class NotebookKernelExecution(models.Model):
    """Audited Slurm execution of an ELN Jupyter notebook."""

    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("unknown", "Unknown"),
    ]

    document = models.ForeignKey(
        NotebookKernelDocument,
        on_delete=models.CASCADE,
        related_name="executions",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notebook_kernel_executions_submitted",
    )
    job_id = models.CharField(max_length=64, blank=True, db_index=True)
    run_id = models.CharField(max_length=128, unique=True)
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default="submitted",
        db_index=True,
    )
    requested_cell_index = models.PositiveIntegerField(null=True, blank=True)
    cpus = models.PositiveSmallIntegerField(default=2)
    memory_mb = models.PositiveIntegerField(default=8192)
    time_minutes = models.PositiveIntegerField(default=60)
    partition = models.CharField(max_length=32, default="max50")
    source_path = models.CharField(max_length=1024)
    run_directory = models.CharField(max_length=1024)
    result_path = models.CharField(max_length=1024, blank=True)
    summary_json = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at", "-id"]
        verbose_name = "ELN Jupyter Execution"
        verbose_name_plural = "ELN Jupyter Executions"

    def __str__(self):
        return f"{self.document_id}: {self.job_id or self.run_id} ({self.status})"

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


class JupyterNotebook(models.Model):
    """Jupyter notebook independent from ELN NotebookEntry records."""

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="jupyter_notebooks",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jupyter_notebooks_updated",
    )

    notebook_json = models.JSONField(default=dict, blank=True)
    is_archived = models.BooleanField(default=False, db_index=True)

    legacy_document = models.OneToOneField(
        "NotebookKernelDocument",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="independent_notebook",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        verbose_name = "Jupyter Notebook"
        verbose_name_plural = "Jupyter Notebooks"

    def __str__(self):
        return self.title


class JupyterKernelSession(models.Model):
    """Persistent Jupyter kernel hosted by a time-limited Slurm job."""

    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("pending", "Pending"),
        ("running", "Running"),
        ("stopping", "Stopping"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("unknown", "Unknown"),
    ]

    notebook = models.ForeignKey(
        JupyterNotebook,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="jupyter_kernel_sessions",
    )

    job_id = models.CharField(max_length=32, db_index=True)
    run_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="submitted",
        db_index=True,
    )

    partition = models.CharField(max_length=32)
    cpus = models.PositiveSmallIntegerField(default=2)
    memory_mb = models.PositiveIntegerField(default=8192)
    time_minutes = models.PositiveIntegerField(default=60)

    run_directory = models.CharField(max_length=1024)
    kernel_info = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at", "-id"]
        verbose_name = "Jupyter Kernel Session"
        verbose_name_plural = "Jupyter Kernel Sessions"

    def __str__(self):
        return (
            f"{self.notebook_id} · "
            f"{self.job_id} · {self.status}"
        )
