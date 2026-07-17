from django.db import migrations


def copy_legacy_jupyter_notebooks(apps, schema_editor):
    LegacyDocument = apps.get_model(
        "core",
        "NotebookKernelDocument",
    )
    JupyterNotebook = apps.get_model(
        "core",
        "JupyterNotebook",
    )

    for document in LegacyDocument.objects.all().iterator():
        entry = document.entry

        owner_id = (
            document.updated_by_id
            or getattr(entry, "author_id", None)
        )

        title = (
            str(document.title or "").strip()
            or str(getattr(entry, "title", "") or "").strip()
            or f"Imported Jupyter notebook {document.pk}"
        )

        JupyterNotebook.objects.get_or_create(
            legacy_document_id=document.pk,
            defaults={
                "title": title[:255],
                "description": (
                    "Imported from the legacy ELN-linked "
                    "Jupyter workspace."
                ),
                "owner_id": owner_id,
                "updated_by_id": document.updated_by_id,
                "notebook_json": (
                    document.notebook_json
                    if isinstance(document.notebook_json, dict)
                    else {}
                ),
                "is_archived": False,
            },
        )


def preserve_imported_notebooks(apps, schema_editor):
    # Intentionally non-destructive. A migration rollback must not
    # delete notebooks that users may have edited after import.
    pass


class Migration(migrations.Migration):

    dependencies = [
        (
            "core",
            "0062_add_independent_jupyter_notebooks",
        ),
    ]

    operations = [
        migrations.RunPython(
            copy_legacy_jupyter_notebooks,
            preserve_imported_notebooks,
        ),
    ]
