"""Signatures and deviations of Notebook entries (traceability).

A signed entry is locked: the content cannot change until the author amends it with a reason, which also
voids the signatures and keeps them as history. Deviations are recorded against an entry at any time, because
what went differently from the plan is often noticed after the page was signed.
"""

from django.conf import settings
from django.db import models


class NotebookSignature(models.Model):
    MEANINGS = [
        ("author", "I performed and wrote this"),
        ("witness", "I read and understood this"),
        ("reviewer", "I reviewed and approve this"),
    ]

    entry = models.ForeignKey("core.NotebookEntry", on_delete=models.CASCADE, related_name="signatures")
    signer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    signer_name = models.CharField(max_length=150, blank=True)
    meaning = models.CharField(max_length=10, choices=MEANINGS)
    comment = models.CharField(max_length=500, blank=True)
    content_sha256 = models.CharField(max_length=64)
    signed_at = models.DateTimeField(auto_now_add=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    superseded_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["entry", "superseded_at"], name="core_nbsig_entry_idx")]

    def __str__(self):
        return f"{self.entry_id} {self.meaning} {self.signer_name}"


class NotebookDeviation(models.Model):
    IMPACTS = [("none", "No impact"), ("minor", "Minor"), ("major", "Major")]

    entry = models.ForeignKey("core.NotebookEntry", on_delete=models.CASCADE, related_name="deviations")
    step_text = models.CharField(max_length=500, blank=True)
    description = models.TextField(max_length=3000)
    impact = models.CharField(max_length=10, choices=IMPACTS, default="minor")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    resolution = models.TextField(max_length=3000, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.entry_id} deviation {self.pk}"
