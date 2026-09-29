import copy
import hashlib

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import (
    connection,
    transaction,
)

from core.models import (
    Bacteria,
    Event,
    Phage,
    Plasmid,
    Sample,
    SampleOrigin,
)


SUBTYPE_ACCESSORS = (
    ("bacteria", Bacteria),
    ("phage", Phage),
    ("plasmid", Plasmid),
)


SAMPLE_GENERATED_FIELDS = {
    "id",
    "uuid",
    "sample_id",
    "micro_qr_token",
    "aliquot_count",
    "created_at",
    "updated_at",
}


ORIGIN_GENERATED_FIELDS = {
    "id",
    "sample",
    "created_at",
    "updated_at",
}


class Command(BaseCommand):
    help = (
        "Normalize historical Sample records with "
        "aliquot_count > 1 into one Sample row per "
        "physical aliquot. Runs as dry-run unless "
        "--apply is explicitly supplied."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Apply normalization. Without this flag "
                "the command is strictly a dry-run."
            ),
        )

        parser.add_argument(
            "--expected-candidates",
            type=int,
            default=None,
            help=(
                "Required with --apply. The write is "
                "refused unless the current candidate "
                "count exactly matches this value."
            ),
        )

        parser.add_argument(
            "--expected-plan-sha256",
            default=None,
            help=(
                "Required with --apply. Must match the "
                "plan_sha256 emitted by a prior dry-run."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = bool(
            options["apply"]
        )

        expected_candidates = options[
            "expected_candidates"
        ]

        expected_plan_sha256 = (
            options.get(
                "expected_plan_sha256"
            )
            or ""
        ).strip().lower()

        self.stdout.write(
            "MODE="
            + (
                "APPLY"
                if apply_changes
                else "DRY_RUN"
            )
        )

        if (
            apply_changes
            and expected_candidates is None
        ):
            raise CommandError(
                "--expected-candidates is required "
                "when using --apply."
            )

        if (
            expected_candidates is not None
            and expected_candidates < 0
        ):
            raise CommandError(
                "--expected-candidates must be "
                "zero or greater."
            )

        if (
            apply_changes
            and not expected_plan_sha256
        ):
            raise CommandError(
                "--expected-plan-sha256 is required "
                "when using --apply."
            )

        if apply_changes:
            self._apply(
                expected_candidates,
                expected_plan_sha256,
            )
            return

        with transaction.atomic():
            if (
                connection.vendor
                == "postgresql"
            ):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SET TRANSACTION READ ONLY"
                    )

                    cursor.execute(
                        "SHOW transaction_read_only"
                    )

                    read_only = (
                        cursor.fetchone()[0]
                    )

                if read_only != "on":
                    raise CommandError(
                        "PostgreSQL dry-run transaction "
                        "is not READ ONLY."
                    )

                self.stdout.write(
                    "database_transaction_read_only=on"
                )

            candidates = list(
                Sample.objects
                .filter(
                    aliquot_count__gt=1
                )
                .order_by("pk")
            )

            plans = self._build_plans(
                candidates
            )

            self._validate_collisions(
                plans
            )

            self._emit_plan(
                plans
            )

            # Additional protection for non-PostgreSQL
            # environments such as the test database.
            transaction.set_rollback(
                True
            )

        self.stdout.write(
            "DRY_RUN_COMPLETE=PASS"
        )

    def _apply(
        self,
        expected_candidates,
        expected_plan_sha256,
    ):
        with transaction.atomic():
            candidates = list(
                Sample.objects
                .select_for_update()
                .filter(
                    aliquot_count__gt=1
                )
                .order_by("pk")
            )

            actual_candidates = len(
                candidates
            )

            if (
                actual_candidates
                != expected_candidates
            ):
                raise CommandError(
                    "Expected "
                    f"{expected_candidates} candidate "
                    "record(s), found "
                    f"{actual_candidates}."
                )

            plans = self._build_plans(
                candidates
            )

            # All target-name and plan identity validation
            # happens before the first UPDATE/INSERT.
            self._validate_collisions(
                plans
            )

            actual_plan_sha256 = (
                self._plan_fingerprint(
                    plans
                )
            )

            if (
                actual_plan_sha256
                != expected_plan_sha256
            ):
                raise CommandError(
                    "Expected plan SHA256 "
                    f"{expected_plan_sha256}, "
                    "but current plan is "
                    f"{actual_plan_sha256}."
                )

            self._emit_plan(
                plans
            )

            for plan in plans:
                self._normalize_one(
                    plan
                )

            source_pks = [
                plan["sample"].pk
                for plan in plans
            ]

            remaining = (
                Sample.objects
                .filter(
                    pk__in=source_pks,
                    aliquot_count__gt=1,
                )
                .count()
            )

            if remaining:
                raise CommandError(
                    "Post-normalization validation "
                    f"failed: {remaining} source "
                    "record(s) still have "
                    "aliquot_count > 1."
                )

            expected_ids = [
                target_id
                for plan in plans
                for target_id in plan[
                    "target_ids"
                ]
            ]

            materialized = (
                Sample.objects
                .filter(
                    sample_id__in=expected_ids
                )
                .count()
            )

            if (
                materialized
                != len(expected_ids)
            ):
                raise CommandError(
                    "Post-normalization validation "
                    "failed: expected "
                    f"{len(expected_ids)} normalized "
                    "Sample rows, found "
                    f"{materialized}."
                )

            self.stdout.write(
                "NORMALIZATION_APPLIED=PASS"
            )

    def _build_plans(
        self,
        candidates,
    ):
        plans = []

        target_owners = {}

        for sample in candidates:
            count = int(
                sample.aliquot_count
            )

            if count <= 1:
                raise CommandError(
                    "Invalid candidate "
                    f"{sample.sample_id}: "
                    f"aliquot_count={count}."
                )

            original_id = (
                sample.sample_id
            )

            target_ids = [
                (
                    f"{original_id}_"
                    f"1.{index}"
                )
                for index in range(
                    1,
                    count + 1,
                )
            ]

            for target_id in target_ids:
                previous = (
                    target_owners.get(
                        target_id
                    )
                )

                if previous is not None:
                    raise CommandError(
                        "Target collision inside "
                        "normalization plan: "
                        f"{target_id} generated by "
                        f"{previous} and "
                        f"{original_id}."
                    )

                target_owners[
                    target_id
                ] = original_id

            plans.append(
                {
                    "sample": sample,
                    "original_id": (
                        original_id
                    ),
                    "original_count": (
                        count
                    ),
                    "target_ids": (
                        target_ids
                    ),
                }
            )

        return plans

    def _validate_collisions(
        self,
        plans,
    ):
        target_ids = [
            target_id
            for plan in plans
            for target_id in plan[
                "target_ids"
            ]
        ]

        if not target_ids:
            return

        collisions = list(
            Sample.objects
            .filter(
                sample_id__in=target_ids
            )
            .order_by(
                "sample_id"
            )
            .values_list(
                "sample_id",
                flat=True,
            )
        )

        if collisions:
            raise CommandError(
                "Target collision detected: "
                + ", ".join(
                    collisions
                )
            )

    def _plan_fingerprint(
        self,
        plans,
    ):
        rows = []

        for plan in plans:
            sample = plan["sample"]

            rows.append(
                "|".join(
                    [
                        str(sample.pk),
                        str(sample.uuid),
                        str(
                            sample.micro_qr_token
                        ),
                        plan["original_id"],
                        str(
                            plan[
                                "original_count"
                            ]
                        ),
                        str(
                            sample.updated_at
                        ),
                        ",".join(
                            plan[
                                "target_ids"
                            ]
                        ),
                    ]
                )
            )

        payload = "\n".join(
            rows
        ).encode(
            "utf-8"
        )

        return hashlib.sha256(
            payload
        ).hexdigest()

    def _emit_plan(
        self,
        plans,
    ):
        rows_to_add = sum(
            plan["original_count"] - 1
            for plan in plans
        )

        self.stdout.write(
            f"candidate_records={len(plans)}"
        )

        self.stdout.write(
            f"rows_to_add={rows_to_add}"
        )

        self.stdout.write(
            "plan_sha256="
            + self._plan_fingerprint(
                plans
            )
        )

        for plan in plans:
            self.stdout.write(
                "candidate="
                f"pk:{plan['sample'].pk};"
                f"source:{plan['original_id']};"
                f"count:{plan['original_count']};"
                "targets:"
                + ",".join(
                    plan["target_ids"]
                )
            )

    def _normalize_one(
        self,
        plan,
    ):
        source = plan["sample"]

        original_id = plan[
            "original_id"
        ]

        target_ids = plan[
            "target_ids"
        ]

        subtype_model, subtype = (
            self._resolve_subtype(
                source
            )
        )

        source_created_at = (
            source.created_at
        )

        source_updated_at = (
            source.updated_at
        )

        # The historical database row becomes the first
        # physical aliquot. Its PK, UUID, QR token and all
        # reverse historical dependencies remain untouched.
        source.sample_id = (
            target_ids[0]
        )

        source.aliquot_count = 1

        source.save(
            update_fields=[
                "sample_id",
                "aliquot_count",
            ]
        )

        self.stdout.write(
            "preserved="
            f"pk:{source.pk};"
            f"source:{original_id};"
            f"target:{target_ids[0]};"
            f"uuid:{source.uuid};"
            f"token:{source.micro_qr_token}"
        )

        for target_id in target_ids[1:]:
            clone = self._create_clone(
                source=source,
                target_id=target_id,
                subtype_model=subtype_model,
                subtype=subtype,
                source_created_at=(
                    source_created_at
                ),
                source_updated_at=(
                    source_updated_at
                ),
            )

            self.stdout.write(
                "materialized="
                f"pk:{clone.pk};"
                f"target:{clone.sample_id};"
                f"uuid:{clone.uuid};"
                f"token:{clone.micro_qr_token}"
            )

    def _resolve_subtype(
        self,
        source,
    ):
        found = []

        for (
            accessor,
            model,
        ) in SUBTYPE_ACCESSORS:
            try:
                child = getattr(
                    source,
                    accessor,
                )
            except ObjectDoesNotExist:
                continue

            found.append(
                (
                    model,
                    child,
                )
            )

        if len(found) > 1:
            raise CommandError(
                "Sample "
                f"{source.sample_id} "
                "unexpectedly has multiple "
                "multi-table subtypes."
            )

        if not found:
            return (
                None,
                None,
            )

        return found[0]

    def _sample_clone_values(
        self,
        source,
        target_id,
    ):
        values = {}

        for field in (
            Sample._meta.concrete_fields
        ):
            if (
                field.primary_key
                or field.name
                in SAMPLE_GENERATED_FIELDS
            ):
                continue

            values[
                field.attname
            ] = copy.deepcopy(
                getattr(
                    source,
                    field.attname,
                )
            )

        values["sample_id"] = (
            target_id
        )

        values["aliquot_count"] = 1

        return values

    def _subtype_clone_values(
        self,
        subtype_model,
        subtype,
    ):
        if subtype_model is None:
            return {}

        values = {}

        for field in (
            subtype_model._meta.local_fields
        ):
            remote = getattr(
                field,
                "remote_field",
                None,
            )

            if (
                field.primary_key
                or field.auto_created
                or getattr(
                    remote,
                    "parent_link",
                    False,
                )
            ):
                continue

            values[
                field.attname
            ] = copy.deepcopy(
                getattr(
                    subtype,
                    field.attname,
                )
            )

        return values

    def _create_clone(
        self,
        *,
        source,
        target_id,
        subtype_model,
        subtype,
        source_created_at,
        source_updated_at,
    ):
        values = (
            self._sample_clone_values(
                source,
                target_id,
            )
        )

        values.update(
            self._subtype_clone_values(
                subtype_model,
                subtype,
            )
        )

        model = (
            subtype_model
            if subtype_model is not None
            else Sample
        )

        clone = model.objects.create(
            **values
        )

        # The physical aliquot already existed when the
        # aggregate was originally registered. Preserve
        # that registration timestamp while the dedicated
        # Event below records when normalization occurred.
        Sample.objects.filter(
            pk=clone.pk
        ).update(
            created_at=source_created_at,
            updated_at=source_updated_at,
        )

        self._clone_direct_m2m(
            source,
            clone,
        )

        self._clone_origin(
            source,
            clone,
        )

        Event.objects.create(
            sample=clone,
            event_type="entry",
            location_snapshot=(
                source.storage_location
                or ""
            ),
            notes=(
                "Materialized from historical "
                f"aggregate {source.pk} "
                f"({source.sample_id}) as "
                f"{target_id} during historical "
                "aliquot normalization."
            ),
            performed_by=None,
        )

        clone.refresh_from_db()

        return clone

    def _clone_direct_m2m(
        self,
        source,
        clone,
    ):
        for field in (
            Sample._meta.many_to_many
        ):
            source_manager = getattr(
                source,
                field.name,
            )

            clone_manager = getattr(
                clone,
                field.name,
            )

            clone_manager.set(
                list(
                    source_manager.all()
                )
            )

    def _clone_origin(
        self,
        source,
        clone,
    ):
        try:
            origin = source.origin
        except ObjectDoesNotExist:
            return

        values = {}

        for field in (
            SampleOrigin._meta
            .concrete_fields
        ):
            if (
                field.primary_key
                or field.name
                in ORIGIN_GENERATED_FIELDS
            ):
                continue

            values[
                field.attname
            ] = copy.deepcopy(
                getattr(
                    origin,
                    field.attname,
                )
            )

        cloned_origin = (
            SampleOrigin.objects.create(
                sample=clone,
                **values,
            )
        )

        SampleOrigin.objects.filter(
            pk=cloned_origin.pk
        ).update(
            created_at=origin.created_at,
            updated_at=origin.updated_at,
        )
