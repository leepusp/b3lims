"""Serialize cooperating Storage writers within a database transaction."""

from django.core.exceptions import ImproperlyConfigured
from django.db import connection


def acquire_storage_writer_lock():
    """
    Serialize Storage mutations on PostgreSQL.

    Call this before acquiring Sample, assignment, or location row locks.
    PostgreSQL releases the advisory lock automatically when the
    surrounding transaction commits or rolls back.

    SQLite uses its existing transaction behavior.
    """
    if connection.vendor != "postgresql":
        return

    if not connection.in_atomic_block:
        raise ImproperlyConfigured(
            "A Storage writer lock requires an active transaction."
        )

    # Application-specific two-integer advisory lock namespace.
    lock_key = (0x42334C49, 0x53544F52)

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            lock_key,
        )
