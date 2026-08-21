from django.db import migrations


class Migration(migrations.Migration):
    """
    Historical compatibility migration.

    The repository's 0001_initial migration already creates the
    ``is_active`` fields on Biobank and Collection.

    The original version of this migration attempted to add those
    columns a second time, preventing a fresh database from being
    migrated from scratch.

    Existing deployed databases are unaffected because this migration
    is already recorded as applied. Fresh databases receive both fields
    from 0001_initial, so no database operation is required here.
    """

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = []
