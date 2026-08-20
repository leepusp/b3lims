from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0069_add_molecular_structure"),
    ]

    operations = [
        migrations.AddField(
            model_name="shipment",
            name="recipient_group_researcher",
            field=models.CharField(
                blank=True,
                max_length=255,
                verbose_name=(
                    "Recipient group / laboratory / researcher"
                ),
            ),
        ),
    ]
