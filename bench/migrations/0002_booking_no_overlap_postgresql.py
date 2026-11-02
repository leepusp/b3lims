"""PostgreSQL-only guard against overlapping exclusive bookings.

The booking service already locks the resource row and checks overlaps in
Python; this constraint is a second line of defence in the database.

It needs the btree_gist extension. If the database user cannot create it,
the migration logs a warning and continues: the Python check still applies.
SQLite (used by the test suite) is skipped.
"""

import logging

from django.db import migrations, transaction


logger = logging.getLogger(__name__)

CONSTRAINT = "bench_booking_no_overlap"


def add_constraint(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    try:
        with transaction.atomic(using=connection.alias):
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
                cursor.execute(
                    f"""
                    ALTER TABLE bench_booking
                    ADD CONSTRAINT {CONSTRAINT}
                    EXCLUDE USING gist (
                        resource_id WITH =,
                        tstzrange("start", "end") WITH &&
                    )
                    WHERE (cancelled_at IS NULL AND exclusive)
                    """
                )
    except Exception as error:  # noqa: BLE001 - keep deploying without the extra guard
        logger.warning(
            "Skipped %s (btree_gist unavailable?): %s. Overlaps are still checked in Python.",
            CONSTRAINT,
            error,
        )


def drop_constraint(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE bench_booking DROP CONSTRAINT IF EXISTS {CONSTRAINT}")


class Migration(migrations.Migration):

    dependencies = [
        ("bench", "0001_lab_calendar_bookings"),
    ]

    operations = [
        migrations.RunPython(add_constraint, drop_constraint),
    ]
