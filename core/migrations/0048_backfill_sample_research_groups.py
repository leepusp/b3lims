from django.db import migrations


def backfill_sample_research_groups(apps, schema_editor):
    Sample = apps.get_model("core", "Sample")

    qs = (
        Sample.objects
        .filter(
            is_active=True,
            research_group__isnull=True,
            biobank__research_group__isnull=False,
        )
        .select_related("biobank", "biobank__research_group")
    )

    for sample in qs.iterator():
        sample.research_group_id = sample.biobank.research_group_id
        sample.save(update_fields=["research_group"])


def reverse_backfill_sample_research_groups(apps, schema_editor):
    # Intentionally no-op.
    # Existing explicit group assignments should not be erased on rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0047_register_biobank_user_roles"),
    ]

    operations = [
        migrations.RunPython(
            backfill_sample_research_groups,
            reverse_backfill_sample_research_groups,
        ),
    ]
