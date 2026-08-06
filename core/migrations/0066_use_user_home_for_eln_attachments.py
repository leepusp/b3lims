import core.models.lab_tools.notebook
import core.services.lab_tools_storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0065_add_notebook_jupyter_links"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notebookattachment",
            name="file",
            field=models.FileField(
                max_length=512,
                storage=(
                    core.services.lab_tools_storage
                    .UserHomeLabToolsStorage()
                ),
                upload_to=(
                    core.models.lab_tools.notebook
                    .notebook_attachment_upload_to
                ),
            ),
        ),
    ]
