from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "core",
            "0077_sample_micro_qr_token",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="phage",
            name="phage_name",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text=(
                    "Legacy phage name retained for "
                    "compatibility with existing records."
                ),
                max_length=100,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="phage",
            name="strain",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Phage strain or isolate designation."
                ),
                max_length=100,
                null=True,
            ),
        ),
    ]
