"""Workflow: a flow chart of steps linked to ELN entries, molecular records and samples.

Phase 1 is the execution flow (status, owner, deadline). ``kind`` and ``config``
on a step are the extension point for phase 2, where a step runs a tool
(Jupyter notebook on DaVinci, later Galaxy) and returns its results.
"""

from django.conf import settings
from django.db import models


class Workflow(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        DONE = "done", "Done"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="", db_default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_default="draft")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workflows")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="shared_workflows")
    entry = models.ForeignKey(
        "core.NotebookEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="workflows"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def __str__(self):
        return self.name


class WorkflowStep(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To do"
        DOING = "doing", "In progress"
        DONE = "done", "Done"
        BLOCKED = "blocked", "Blocked"

    class Kind(models.TextChoices):
        MANUAL = "manual", "Manual"
        JUPYTER = "jupyter", "Jupyter notebook"  # phase 2
        GALAXY = "galaxy", "Galaxy"  # phase 2

    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="steps")
    title = models.CharField(max_length=200)
    notes = models.TextField(blank=True, default="", db_default="")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.MANUAL, db_default="manual")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TODO, db_default="todo")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    due_date = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # Position on the canvas.
    x = models.IntegerField(default=40, db_default=40)
    y = models.IntegerField(default=40, db_default=40)
    # Links: an ELN entry, an ELN step (kept in sync), a molecular record, a sample.
    entry = models.ForeignKey(
        "core.NotebookEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="workflow_steps"
    )
    notebook_step = models.OneToOneField(
        "core.NotebookStep", null=True, blank=True, on_delete=models.SET_NULL, related_name="workflow_step"
    )
    molecule = models.ForeignKey(
        "core.MolecularSequence", null=True, blank=True, on_delete=models.SET_NULL, related_name="workflow_steps"
    )
    sample = models.ForeignKey(
        "core.Sample", null=True, blank=True, on_delete=models.SET_NULL, related_name="workflow_steps"
    )
    # Phase 2: tool parameters and results.
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.workflow_id}: {self.title}"


class WorkflowEdge(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="edges")
    source = models.ForeignKey(WorkflowStep, on_delete=models.CASCADE, related_name="outgoing")
    target = models.ForeignKey(WorkflowStep, on_delete=models.CASCADE, related_name="incoming")

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["source", "target"], name="core_wf_edge_unique"),
            models.CheckConstraint(condition=~models.Q(source=models.F("target")), name="core_wf_edge_not_self"),
        ]

    def __str__(self):
        return f"{self.source_id} -> {self.target_id}"
