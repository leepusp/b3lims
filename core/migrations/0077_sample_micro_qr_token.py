import secrets

import core.models.samples.sample
from django.db import migrations, models


TOKEN_ALPHABET = (
    "23456789"
    "ABCDEFGHJKLMNPQRSTUVWXYZ"
)
TOKEN_LENGTH = 10


def _new_token():
    return "".join(
        secrets.choice(TOKEN_ALPHABET)
        for _ in range(TOKEN_LENGTH)
    )


def populate_micro_qr_tokens(
    apps,
    schema_editor,
):
    Sample = apps.get_model(
        "core",
        "Sample",
    )

    existing = set(
        Sample.objects.exclude(
            micro_qr_token__isnull=True
        )
        .exclude(
            micro_qr_token=""
        )
        .values_list(
            "micro_qr_token",
            flat=True,
        )
    )

    queryset = (
        Sample.objects.filter(
            micro_qr_token__isnull=True
        )
        .order_by("pk")
    )

    for sample in queryset.iterator():
        while True:
            token = _new_token()

            if token not in existing:
                break

        Sample.objects.filter(
            pk=sample.pk
        ).update(
            micro_qr_token=token
        )

        existing.add(token)


class Migration(migrations.Migration):

    dependencies = [
        (
            "core",
            "0076_extend_sample_origin_metadata",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="sample",
            name="micro_qr_token",
            field=models.CharField(
                editable=False,
                help_text=(
                    "Permanent compact identifier "
                    "encoded in the Sample Micro QR "
                    "label."
                ),
                max_length=10,
                null=True,
            ),
        ),
        migrations.RunPython(
            populate_micro_qr_tokens,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="sample",
            name="micro_qr_token",
            field=models.CharField(
                default=(
                    core.models.samples.sample
                    .generate_sample_micro_qr_token
                ),
                editable=False,
                help_text=(
                    "Permanent compact identifier "
                    "encoded in the Sample Micro QR "
                    "label."
                ),
                max_length=10,
                unique=True,
            ),
        ),
    ]
