# Generated manually for the reagent document and soft-deactivation workflow.

import core.models.chemicals.chemical
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0055_register_cibio_transport_authorization"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="chemical",
            name="is_active",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.CreateModel(
            name="ChemicalFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to=core.models.chemicals.chemical.chemical_document_upload_to)),
                ("original_filename", models.CharField(max_length=255)),
                ("title", models.CharField(max_length=255)),
                ("document_type", models.CharField(choices=[("sds", "Safety Data Sheet (SDS)"), ("coa", "Certificate of Analysis"), ("specification", "Product Specification"), ("protocol", "Protocol / Instructions"), ("other", "Other Document")], default="other", max_length=30)),
                ("description", models.TextField(blank=True)),
                ("version", models.CharField(blank=True, max_length=50)),
                ("document_date", models.DateField(blank=True, null=True)),
                ("mime_type", models.CharField(blank=True, max_length=150)),
                ("file_size", models.BigIntegerField(blank=True, null=True)),
                ("is_primary", models.BooleanField(default=False, help_text="Primary SDS shown on the reagent QR page.")),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("chemical", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="files", to="core.chemical")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="chemical_files", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-is_primary", "-document_date", "-uploaded_at"],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("is_active", True), ("is_primary", True)), fields=("chemical",), name="unique_active_primary_chemical_document"),
                    models.CheckConstraint(condition=models.Q(("is_primary", False), ("document_type", "sds"), _connector="OR"), name="primary_chemical_document_must_be_sds"),
                ],
            },
        ),
    ]
