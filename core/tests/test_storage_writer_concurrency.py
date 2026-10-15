"""PostgreSQL regression for competing Storage writers."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import (
    connection,
    connections,
    close_old_connections,
    transaction,
)
from django.test import TransactionTestCase

from core.models.samples.sample import Sample
from core.models.samples.storage import (
    SampleStorageAssignment,
    StorageLocation,
    StorageWorkspace,
)
from core.services.storage_assignment_reconcile import (
    reconcile_sample_storage_from_text,
)
from core.services.storage_sample_movements import move_sample


@unittest.skipUnless(
    connection.vendor == "postgresql",
    "Requires real PostgreSQL row-level locks.",
)
class StorageWriterConcurrencyTests(TransactionTestCase):

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="e1c-lock-owner",
            is_staff=True,
        )

        self.workspace = StorageWorkspace.objects.create(
            name="E1C PostgreSQL Concurrency Workspace",
            scope="personal",
            owner=self.owner,
        )

        self.room = StorageLocation.objects.create(
            name="E1C Concurrent Room",
            location_type="room",
            workspace=self.workspace,
        )
        self.box_a = StorageLocation.objects.create(
            name="E1C Box A",
            parent=self.room,
            location_type="box",
            workspace=self.workspace,
        )
        self.box_b = StorageLocation.objects.create(
            name="E1C Box B",
            parent=self.room,
            location_type="box",
            workspace=self.workspace,
        )

        self.sample = Sample.objects.create(
            sample_id="E1C-LOCK-001",
            sample_type="Other",
            organism_name="E1C Lock Test",
            owner=self.owner,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location=f"{self.box_a.full_path} > P01",
        )

        self.assignment = SampleStorageAssignment.objects.create(
            sample=self.sample,
            location=self.box_a,
            rank=1,
            is_primary=True,
            position="P01",
            status="active",
        )

    def writer(self, kind, barrier):
        """E1C_REAL_SERVICE_CONCURRENCY_V1.

        Start both writers together and allow their services
        to acquire locks using their actual implementations.
        No locks are acquired manually before either service.
        """
        close_old_connections()

        try:
            barrier.wait(timeout=10)

            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SET LOCAL lock_timeout = '6s'"
                    )

                if kind == "edit":
                    reconcile_sample_storage_from_text(
                        sample=self.sample,
                        storage_location_text=self.box_a.full_path,
                    )

                elif kind == "move":
                    move_sample(
                        assignment_id=self.assignment.pk,
                        destination_id=self.box_b.pk,
                        position="P04",
                        expected_location_id=self.box_a.pk,
                        expected_position="P01",
                        expected_source_path=self.box_a.full_path,
                        expected_destination_path=self.box_b.full_path,
                        actor=self.owner,
                        reason="Concurrent service regression test.",
                    )

                else:
                    raise ValueError("Unknown writer type.")

            return ("ok", None, "")

        except ValidationError as exc:
            return ("conflict", None, str(exc)[:300])

        except Exception as exc:
            underlying = getattr(exc, "__cause__", None)

            sqlstate = (
                getattr(underlying, "sqlstate", None)
                or getattr(exc, "sqlstate", None)
                or getattr(underlying, "pgcode", None)
            )

            return (
                "error",
                sqlstate,
                f"{type(exc).__name__}: {exc}"[:300],
            )

        finally:
            connections.close_all()


    def test_edit_and_move_do_not_deadlock(self):
        barrier = Barrier(2)

        with ThreadPoolExecutor(max_workers=2) as pool:
            edit_future = pool.submit(
                self.writer, "edit", barrier
            )
            move_future = pool.submit(
                self.writer, "move", barrier
            )

            results = [
                edit_future.result(timeout=18),
                move_future.result(timeout=18),
            ]

        print("\nE1C_CONCURRENCY_OUTCOMES:", results)

        unexpected = [
            result for result in results
            if result[0] not in {"ok", "conflict"}
        ]

        self.assertFalse(
            unexpected,
            f"Concurrent Storage writers failed: {results}",
        )


    def test_competing_movements_cannot_claim_same_slot(self):
        """Only one concurrent transfer may occupy a physical slot."""
        from core.models.samples.storage import StorageMovement

        second_sample = Sample.objects.create(
            sample_id="E1C-LOCK-002",
            sample_type="Other",
            organism_name="Second Concurrent Sample",
            owner=self.owner,
            status="qc",
            aliquot_count=1,
            is_active=True,
            is_public=False,
            is_embargoed=False,
            storage_location=f"{self.box_a.full_path} > P02",
        )

        second_assignment = SampleStorageAssignment.objects.create(
            sample=second_sample,
            location=self.box_a,
            rank=1,
            is_primary=True,
            position="P02",
            status="active",
        )

        barrier = Barrier(2)

        def competing_move(assignment_id, old_position, new_position):
            close_old_connections()

            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")

                barrier.wait(timeout=10)

                move_sample(
                    assignment_id=assignment_id,
                    destination_id=self.box_b.pk,
                    position=new_position,
                    expected_location_id=self.box_a.pk,
                    expected_position=old_position,
                    expected_source_path=self.box_a.full_path,
                    expected_destination_path=self.box_b.full_path,
                    actor=self.owner,
                    reason="Concurrent physical slot validation.",
                )

                return ("ok", "")

            except ValidationError as exc:
                return ("rejected", str(exc))

            except Exception as exc:
                return ("error", f"{type(exc).__name__}: {exc}")

            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                competing_move,
                self.assignment.pk,
                "P01",
                "P09",
            )
            second = pool.submit(
                competing_move,
                second_assignment.pk,
                "P02",
                " p09 ",
            )

            outcomes = [
                first.result(timeout=20),
                second.result(timeout=20),
            ]

        print("CONCURRENT_SLOT_OUTCOMES:", outcomes)

        statuses = sorted(item[0] for item in outcomes)

        self.assertEqual(
            statuses,
            ["ok", "rejected"],
            f"Unexpected movement results: {outcomes}",
        )

        assignments = list(
            SampleStorageAssignment.objects.filter(
                pk__in=[
                    self.assignment.pk,
                    second_assignment.pk,
                ]
            ).select_related("location", "sample")
        )

        destination_occupants = [
            assignment
            for assignment in assignments
            if (
                assignment.location_id == self.box_b.pk
                and assignment.position.strip().casefold() == "p09"
            )
        ]

        self.assertEqual(len(destination_occupants), 1)

        self.assertEqual(
            StorageMovement.objects.filter(
                movement_type="sample"
            ).count(),
            1,
        )

        for assignment in assignments:
            assignment.sample.refresh_from_db()

            self.assertEqual(
                assignment.sample.storage_location,
                (
                    f"{assignment.location.full_path}"
                    f" > {assignment.position}"
                ),
            )
