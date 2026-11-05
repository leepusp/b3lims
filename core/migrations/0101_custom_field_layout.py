import copy

from django.db import migrations


def _with_new_keys(data):
    """Copy of ``data`` with the new keys added, or None when nothing to do.

    Self-contained on purpose: a migration must keep working when the service
    code changes in the contract release.
    """
    if not isinstance(data, dict):
        return None
    namespace = data.get("elabftw") if isinstance(data.get("elabftw"), dict) else {}
    has_old = "extra_fields" in data or "extra_fields_groups" in namespace
    if not has_old or ("custom_fields" in data and "custom_field_groups" in data):
        return None
    result = dict(data)
    fields = data.get("custom_fields", data.get("extra_fields"))
    groups = data.get("custom_field_groups", namespace.get("extra_fields_groups"))
    result["custom_fields"] = copy.deepcopy(fields if isinstance(fields, dict) else {})
    result["custom_field_groups"] = copy.deepcopy(groups if isinstance(groups, list) else [])
    return result


def copy_to_new_keys(apps, schema_editor):
    """Expand step: the old keys stay, so the previous release still works."""
    for model_name, attr in (("NotebookEntry", "metadata"), ("NotebookTemplate", "structure")):
        Model = apps.get_model("core", model_name)
        for obj in Model.objects.iterator(chunk_size=200):
            updated = _with_new_keys(getattr(obj, attr))
            if updated is not None:
                setattr(obj, attr, updated)
                obj.save(update_fields=[attr])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0100_notebook_favorite_tags_step_groups"),
    ]

    operations = [
        migrations.RunPython(copy_to_new_keys, migrations.RunPython.noop),
    ]
