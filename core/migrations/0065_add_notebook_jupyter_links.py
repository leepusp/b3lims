from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(
            settings.AUTH_USER_MODEL
        ),
        (
            "core",
            "0064_add_notebook_molecular_links",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="NotebookJupyterLink",
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
                (
                    "linked_at",
                    models.DateTimeField(
                        auto_now_add=True
                    ),
                ),
                (
                    "entry",
                    models.ForeignKey(
                        on_delete=(
                            django.db.models.deletion.CASCADE
                        ),
                        related_name="jupyter_links",
                        to="core.notebookentry",
                    ),
                ),
                (
                    "linked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=(
                            django.db.models.deletion.SET_NULL
                        ),
                        related_name=(
                            "notebook_jupyter_links_created"
                        ),
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "notebook",
                    models.ForeignKey(
                        on_delete=(
                            django.db.models.deletion.CASCADE
                        ),
                        related_name="eln_links",
                        to="core.jupyternotebook",
                    ),
                ),
            ],
            options={
                "ordering": [
                    "-linked_at",
                    "-id",
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="notebookjupyterlink",
            constraint=models.UniqueConstraint(
                fields=(
                    "entry",
                    "notebook",
                ),
                name=(
                    "unique_notebook_entry_"
                    "jupyter_link"
                ),
            ),
        ),
        migrations.DeleteModel(
            name="NotebookKernelExecution",
        ),
        migrations.RemoveField(
            model_name="jupyternotebook",
            name="legacy_document",
        ),
        migrations.DeleteModel(
            name="NotebookKernelDocument",
        ),
    ]
