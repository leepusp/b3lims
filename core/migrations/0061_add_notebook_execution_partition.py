from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0060_add_eln_jupyter_execution"),
    ]

    operations = [
        migrations.AddField(
            model_name="notebookkernelexecution",
            name="partition",
            field=models.CharField(
                default="max50",
                max_length=32,
            ),
        ),
    ]
