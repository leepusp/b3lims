"""Data submission packages and the internal repository.

A package gathers records (sequences, structures, samples, ELN entries) with
metadata and a taxon. It starts as a draft, is proposed for review, and only
reaches a destination after a named person approves it. Phase 1 publishes to
the internal repository; GenBank/SRA, wwPDB and Zenodo adapters follow.
"""

from django.conf import settings
from django.db import models


class SubmissionPackage(models.Model):
    class Destination(models.TextChoices):
        INTERNAL = "internal", "Internal repository (USP/CEPID B3)"
        GENBANK = "genbank", "GenBank / SRA (NCBI)"
        PDB = "pdb", "PDB / wwPDB"
        ZENODO = "zenodo", "Zenodo"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PROPOSED = "proposed", "Proposed"
        APPROVED = "approved", "Approved"
        PUBLISHED = "published", "Published"
        REJECTED = "rejected", "Rejected"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="", db_default="")
    destination = models.CharField(
        max_length=12, choices=Destination.choices, default=Destination.INTERNAL, db_default="internal"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_default="draft")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="submission_packages")
    workflow = models.ForeignKey(
        "core.Workflow", null=True, blank=True, on_delete=models.SET_NULL, related_name="submission_packages"
    )

    # Taxon (NCBI taxonomy id) with the lineage frozen at the time it was set.
    taxon_id = models.CharField(max_length=20, blank=True, default="", db_default="")
    taxon_name = models.CharField(max_length=255, blank=True, default="", db_default="")
    taxonomy_version = models.CharField(max_length=40, blank=True, default="", db_default="")
    lineage = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    review_note = models.TextField(blank=True, default="", db_default="")
    proposed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    repository_path = models.CharField(max_length=400, blank=True, default="", db_default="")
    manifest_sha256 = models.CharField(max_length=64, blank=True, default="", db_default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        permissions = [("approve_submission", "Can approve data submissions")]

    def __str__(self):
        return self.title


class SubmissionItem(models.Model):
    class Kind(models.TextChoices):
        SEQUENCE = "sequence", "Sequence record"
        STRUCTURE = "structure", "3D structure"
        SAMPLE = "sample", "Sample"
        ENTRY = "entry", "ELN entry"

    package = models.ForeignKey(SubmissionPackage, on_delete=models.CASCADE, related_name="items")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    label = models.CharField(max_length=255, blank=True, default="", db_default="")
    molecule = models.ForeignKey(
        "core.MolecularSequence", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    structure = models.ForeignKey(
        "core.MolecularStructure", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    sample = models.ForeignKey("core.Sample", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    entry = models.ForeignKey("core.NotebookEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.package_id}: {self.kind} {self.label}"
