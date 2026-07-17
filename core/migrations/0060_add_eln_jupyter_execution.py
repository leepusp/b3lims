from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

import core.models.lab_tools.notebook


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0059_remove_legacy_molecular_features_json"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotebookKernelDocument",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(default="ELN analysis", max_length=255)),
                (
                    "notebook_json",
                    models.JSONField(
                        default=core.models.lab_tools.notebook.default_jupyter_notebook
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notebook_kernel_documents_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "entry",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="kernel_document",
                        to="core.notebookentry",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notebook_kernel_documents_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "ELN Jupyter Notebook",
                "verbose_name_plural": "ELN Jupyter Notebooks",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="NotebookKernelExecution",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("job_id", models.CharField(blank=True, db_index=True, max_length=64)),
                ("run_id", models.CharField(max_length=128, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("submitted", "Submitted"),
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                            ("unknown", "Unknown"),
                        ],
                        db_index=True,
                        default="submitted",
                        max_length=32,
                    ),
                ),
                (
                    "requested_cell_index",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("cpus", models.PositiveSmallIntegerField(default=2)),
                ("memory_mb", models.PositiveIntegerField(default=8192)),
                ("time_minutes", models.PositiveIntegerField(default=60)),
                ("source_path", models.CharField(max_length=1024)),
                ("run_directory", models.CharField(max_length=1024)),
                ("result_path", models.CharField(blank=True, max_length=1024)),
                ("summary_json", models.JSONField(blank=True, default=dict)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="executions",
                        to="core.notebookkerneldocument",
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notebook_kernel_executions_submitted",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "ELN Jupyter Execution",
                "verbose_name_plural": "ELN Jupyter Executions",
                "ordering": ["-submitted_at", "-id"],
            },
        ),
    ]
