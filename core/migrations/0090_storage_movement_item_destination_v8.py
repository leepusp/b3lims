from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0089_storage_workspaces_v8"),
    ]

    operations = [
        migrations.AddField(
            model_name="storagemovementitem",
            name="destination_location_id_snapshot",
            field=models.PositiveBigIntegerField(
                blank=True,
                null=True,
            ),
        ),
    ]
