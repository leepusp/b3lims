import copy
import hashlib
import json

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import (
    connection,
    transaction,
)
from django.db.models import Q

from core.models import (
    Bacteria,
    Event,
    HostRange,
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

            hostrange_plans = (
                self._build_hostrange_plans(
                    plans
                )
            )

            self._validate_collisions(
                plans
            )

            self._validate_hostrange_collisions(
                hostrange_plans
            )

            self._emit_plan(
                plans,
                hostrange_plans,
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

            hostrange_plans = (
                self._build_hostrange_plans(
                    plans,
                    lock=True,
                )
            )

            # All target-name, HostRange topology and plan
            # identity validation happens before the first
            # UPDATE/INSERT.
            self._validate_collisions(
                plans
            )

            self._validate_hostrange_collisions(
                hostrange_plans
            )

            actual_plan_sha256 = (
                self._plan_fingerprint(
                    plans,
                    hostrange_plans,
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
                plans,
                hostrange_plans,
            )

            for plan in plans:
                self._normalize_one(
                    plan
                )

            # HostRange rows reference concrete Bacteria /
            # Phage Sample rows. Materialize their expanded
            # topology only after every aliquot row exists.
            self._materialize_hostranges(
                hostrange_plans
            )

            self._validate_hostrange_materialization(
                hostrange_plans
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


    def _hostrange_clone_values(
        self,
        relation,
    ):
        values = {}

        for field in (
            HostRange._meta.concrete_fields
        ):
            if (
                field.primary_key
                or field.name
                in {
                    "phage",
                    "bacteria",
                }
            ):
                continue

            value = relation.__dict__.get(
                field.attname
            )

            # ImageField values are persisted as their
            # storage path. Reusing that path preserves the
            # historical evidence without copying files.
            if hasattr(
                value,
                "name",
            ):
                value = value.name

            values[
                field.attname
            ] = copy.deepcopy(
                value
            )

        return values

    def _build_hostrange_plans(
        self,
        plans,
        *,
        lock=False,
    ):
        plans_by_pk = {
            plan["sample"].pk: plan
            for plan in plans
        }

        if not plans_by_pk:
            return []

        candidate_pks = list(
            plans_by_pk
        )

        queryset = (
            HostRange.objects
            .filter(
                Q(
                    phage_id__in=candidate_pks
                )
                |
                Q(
                    bacteria_id__in=candidate_pks
                )
            )
            .select_related(
                "phage",
                "bacteria",
            )
            .order_by("pk")
        )

        if lock:
            queryset = (
                queryset.select_for_update()
            )

        hostrange_plans = []

        for relation in queryset:
            phage_plan = (
                plans_by_pk.get(
                    relation.phage_id
                )
            )

            bacteria_plan = (
                plans_by_pk.get(
                    relation.bacteria_id
                )
            )

            phage_target_ids = (
                list(
                    phage_plan["target_ids"]
                )
                if phage_plan is not None
                else [
                    relation.phage.sample_id
                ]
            )

            bacteria_target_ids = (
                list(
                    bacteria_plan[
                        "target_ids"
                    ]
                )
                if bacteria_plan is not None
                else [
                    relation.bacteria.sample_id
                ]
            )

            target_pairs = [
                (
                    phage_target_id,
                    bacteria_target_id,
                )
                for phage_target_id
                in phage_target_ids
                for bacteria_target_id
                in bacteria_target_ids
            ]

            preserved_pair = (
                phage_target_ids[0],
                bacteria_target_ids[0],
            )

            new_pairs = [
                pair
                for pair in target_pairs
                if pair != preserved_pair
            ]

            hostrange_plans.append(
                {
                    "source": relation,
                    "source_pk": (
                        relation.pk
                    ),
                    "phage_pk": (
                        relation.phage_id
                    ),
                    "bacteria_pk": (
                        relation.bacteria_id
                    ),
                    "phage_target_ids": (
                        phage_target_ids
                    ),
                    "bacteria_target_ids": (
                        bacteria_target_ids
                    ),
                    "target_pairs": (
                        target_pairs
                    ),
                    "preserved_pair": (
                        preserved_pair
                    ),
                    "new_pairs": (
                        new_pairs
                    ),
                    "clone_values": (
                        self._hostrange_clone_values(
                            relation
                        )
                    ),
                }
            )

        return hostrange_plans

    def _validate_hostrange_collisions(
        self,
        hostrange_plans,
    ):
        pair_owners = {}

        for plan in hostrange_plans:
            for pair in plan[
                "target_pairs"
            ]:
                previous = (
                    pair_owners.get(
                        pair
                    )
                )

                if (
                    previous is not None
                    and previous
                    != plan["source_pk"]
                ):
                    raise CommandError(
                        "HostRange target collision "
                        "inside normalization plan: "
                        f"{pair[0]} -> {pair[1]} "
                        "generated by HostRange "
                        f"{previous} and "
                        f"{plan['source_pk']}."
                    )

                pair_owners[
                    pair
                ] = plan["source_pk"]

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
        hostrange_plans,
    ):
        sample_rows = []

        for plan in plans:
            sample = plan["sample"]

            sample_rows.append(
                {
                    "pk": sample.pk,
                    "uuid": str(
                        sample.uuid
                    ),
                    "micro_qr_token": (
                        sample.micro_qr_token
                    ),
                    "original_id": (
                        plan["original_id"]
                    ),
                    "original_count": (
                        plan[
                            "original_count"
                        ]
                    ),
                    "updated_at": str(
                        sample.updated_at
                    ),
                    "target_ids": list(
                        plan["target_ids"]
                    ),
                }
            )

        hostrange_rows = []

        for plan in hostrange_plans:
            hostrange_rows.append(
                {
                    "source_pk": (
                        plan["source_pk"]
                    ),
                    "phage_pk": (
                        plan["phage_pk"]
                    ),
                    "bacteria_pk": (
                        plan["bacteria_pk"]
                    ),
                    "phage_target_ids": list(
                        plan[
                            "phage_target_ids"
                        ]
                    ),
                    "bacteria_target_ids": list(
                        plan[
                            "bacteria_target_ids"
                        ]
                    ),
                    "target_pairs": [
                        list(pair)
                        for pair in plan[
                            "target_pairs"
                        ]
                    ],
                    "clone_values": (
                        plan[
                            "clone_values"
                        ]
                    ),
                }
            )

        payload = json.dumps(
            {
                "samples": (
                    sample_rows
                ),
                "host_ranges": (
                    hostrange_rows
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            default=str,
        ).encode(
            "utf-8"
        )

        return hashlib.sha256(
            payload
        ).hexdigest()

    def _emit_plan(
        self,
        plans,
        hostrange_plans,
    ):
        rows_to_add = sum(
            plan["original_count"] - 1
            for plan in plans
        )

        hostrange_rows_to_add = sum(
            len(
                plan["new_pairs"]
            )
            for plan in hostrange_plans
        )

        self.stdout.write(
            f"candidate_records={len(plans)}"
        )

        self.stdout.write(
            f"rows_to_add={rows_to_add}"
        )

        self.stdout.write(
            "hostrange_records="
            f"{len(hostrange_plans)}"
        )

        self.stdout.write(
            "hostrange_rows_to_add="
            f"{hostrange_rows_to_add}"
        )

        self.stdout.write(
            "plan_sha256="
            + self._plan_fingerprint(
                plans,
                hostrange_plans,
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

        for plan in hostrange_plans:
            targets = ",".join(
                (
                    f"{phage_id}"
                    f">{bacteria_id}"
                )
                for (
                    phage_id,
                    bacteria_id,
                )
                in plan["target_pairs"]
            )

            self.stdout.write(
                "hostrange="
                f"pk:{plan['source_pk']};"
                f"phage_pk:"
                f"{plan['phage_pk']};"
                f"bacteria_pk:"
                f"{plan['bacteria_pk']};"
                f"targets:{targets}"
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


    def _materialize_hostranges(
        self,
        hostrange_plans,
    ):
        for plan in hostrange_plans:
            for (
                phage_sample_id,
                bacteria_sample_id,
            ) in plan["new_pairs"]:
                try:
                    phage = (
                        Phage.objects.get(
                            sample_id=(
                                phage_sample_id
                            )
                        )
                    )
                except Phage.DoesNotExist as exc:
                    raise CommandError(
                        "HostRange materialization "
                        "failed: Phage "
                        f"{phage_sample_id} "
                        "does not exist."
                    ) from exc

                try:
                    bacteria = (
                        Bacteria.objects.get(
                            sample_id=(
                                bacteria_sample_id
                            )
                        )
                    )
                except Bacteria.DoesNotExist as exc:
                    raise CommandError(
                        "HostRange materialization "
                        "failed: Bacteria "
                        f"{bacteria_sample_id} "
                        "does not exist."
                    ) from exc

                if (
                    HostRange.objects
                    .filter(
                        phage=phage,
                        bacteria=bacteria,
                    )
                    .exists()
                ):
                    raise CommandError(
                        "HostRange collision after "
                        "Sample materialization: "
                        f"{phage_sample_id} -> "
                        f"{bacteria_sample_id}."
                    )

                relation = (
                    HostRange.objects.create(
                        phage=phage,
                        bacteria=bacteria,
                        **copy.deepcopy(
                            plan[
                                "clone_values"
                            ]
                        ),
                    )
                )

                self.stdout.write(
                    "hostrange_materialized="
                    f"pk:{relation.pk};"
                    f"source_pk:"
                    f"{plan['source_pk']};"
                    f"phage:"
                    f"{phage_sample_id};"
                    f"bacteria:"
                    f"{bacteria_sample_id}"
                )

    def _validate_hostrange_materialization(
        self,
        hostrange_plans,
    ):
        expected_pairs = 0

        for plan in hostrange_plans:
            preserved_pair = (
                plan["preserved_pair"]
            )

            for pair in plan[
                "target_pairs"
            ]:
                (
                    phage_sample_id,
                    bacteria_sample_id,
                ) = pair

                try:
                    relation = (
                        HostRange.objects
                        .select_related(
                            "phage",
                            "bacteria",
                        )
                        .get(
                            phage__sample_id=(
                                phage_sample_id
                            ),
                            bacteria__sample_id=(
                                bacteria_sample_id
                            ),
                        )
                    )
                except HostRange.DoesNotExist as exc:
                    raise CommandError(
                        "Post-normalization HostRange "
                        "validation failed: missing "
                        f"{phage_sample_id} -> "
                        f"{bacteria_sample_id}."
                    ) from exc

                if (
                    pair == preserved_pair
                    and relation.pk
                    != plan["source_pk"]
                ):
                    raise CommandError(
                        "Post-normalization HostRange "
                        "validation failed: historical "
                        f"row {plan['source_pk']} was not "
                        "preserved for "
                        f"{phage_sample_id} -> "
                        f"{bacteria_sample_id}."
                    )

                current_values = (
                    self._hostrange_clone_values(
                        relation
                    )
                )

                if (
                    current_values
                    != plan["clone_values"]
                ):
                    raise CommandError(
                        "Post-normalization HostRange "
                        "validation failed: metadata "
                        "mismatch for "
                        f"{phage_sample_id} -> "
                        f"{bacteria_sample_id}."
                    )

                expected_pairs += 1

        self.stdout.write(
            "hostrange_materialized_pairs="
            f"{expected_pairs}"
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
