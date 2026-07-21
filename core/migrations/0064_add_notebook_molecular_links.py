from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_molecular_links(apps, schema_editor):
    MolecularSequence = apps.get_model(
        "core",
        "MolecularSequence",
    )
    NotebookMolecularLink = apps.get_model(
        "core",
        "NotebookMolecularLink",
    )

    for molecule in (
        MolecularSequence.objects
        .exclude(source_entry_id__isnull=True)
        .iterator()
    ):
        NotebookMolecularLink.objects.get_or_create(
            entry_id=molecule.source_entry_id,
            molecule_id=molecule.id,
            defaults={
                "linked_by_id": molecule.owner_id,
                "snapshot_json": {
                    "id": molecule.id,
                    "name": molecule.name,
                    "sequence_type": molecule.sequence_type,
                    "topology": molecule.topology,
                    "length": molecule.length,
                    "description": molecule.description,
                    "checksum_sha256": (
                        molecule.checksum_sha256
                    ),
                },
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(
            settings.AUTH_USER_MODEL
        ),
        (
            "core",
            "0063_copy_legacy_jupyter_notebooks",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="NotebookMolecularLink",
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
                    "snapshot_json",
                    models.JSONField(
                        blank=True,
                        default=dict,
                    ),
                ),
                (
                    "notes",
                    models.TextField(blank=True),
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
                        related_name="molecular_links",
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
                            "notebook_molecular_links_created"
                        ),
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "molecule",
                    models.ForeignKey(
                        on_delete=(
                            django.db.models.deletion.CASCADE
                        ),
                        related_name="notebook_links",
                        to="core.molecularsequence",
                    ),
                ),
            ],
            options={
                "ordering": ["-linked_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="notebookmolecularlink",
            constraint=models.UniqueConstraint(
                fields=("entry", "molecule"),
                name=(
                    "unique_notebook_entry_"
                    "molecular_link"
                ),
            ),
        ),
        migrations.RunPython(
            backfill_molecular_links,
            migrations.RunPython.noop,
        ),
    ]
