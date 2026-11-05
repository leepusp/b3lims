"""Context for the Molecular Registry landing page.

Everything here is read-only and works on a list of MolecularSequence rows the
caller already filtered for visibility, so it never widens access.
"""

from collections import defaultdict

from django.db.models import Count

from core.models.lab_tools.notebook import MolecularSequence
from core.models.samples.storage import SampleStorageAssignment
from core.permissions.samples import visible_samples_for_user
from core.permissions.storage_workspaces_v8 import can_view_storage_location


def type_counts(molecules):
    """Return [(value, label, count)] for every type, in menu order."""
    counts = defaultdict(int)

    for molecule in molecules:
        counts[molecule.sequence_type] += 1

    return [
        (value, label, counts.get(value, 0))
        for value, label in MolecularSequence.SEQUENCE_TYPE_CHOICES
    ]


def duplicate_groups(molecules):
    """Map molecule id -> [(id, name)] of other records with the same sequence.

    Records match when sequence checksum and topology are equal and the
    sequence is not empty.
    """
    groups = defaultdict(list)

    for molecule in molecules:
        if molecule.checksum_sha256:
            key = (molecule.checksum_sha256, molecule.topology)
            groups[key].append(molecule)

    result = {}

    for members in groups.values():
        if len(members) < 2:
            continue

        for molecule in members:
            result[molecule.id] = [
                (other.id, other.name)
                for other in members
                if other.id != molecule.id
            ]

    return result


def record_context(user, molecules):
    """Return {molecule id: context dict} using a handful of queries."""
    ids = [molecule.id for molecule in molecules]

    if not ids:
        return {}

    counted = {
        row["id"]: row
        for row in MolecularSequence.objects.filter(id__in=ids).values("id").annotate(
            features=Count("features", distinct=True),
            alignments=Count("alignments", distinct=True),
            structures=Count("structures", distinct=True),
            entries=Count("notebook_links", distinct=True),
        )
    }

    sample_ids = {
        molecule.linked_sample_id
        for molecule in molecules
        if molecule.linked_sample_id
    }
    visible_samples = set(
        visible_samples_for_user(user)
        .filter(id__in=sample_ids)
        .values_list("id", flat=True)
    ) if sample_ids else set()

    places = defaultdict(list)

    if visible_samples:
        assignments = (
            SampleStorageAssignment.objects.filter(
                sample_id__in=visible_samples, status="active"
            )
            .select_related("location")
            .order_by("rank", "pk")
        )

        for assignment in assignments:
            if can_view_storage_location(user, assignment.location):
                places[assignment.sample_id].append(assignment)

    context = {}

    for molecule in molecules:
        row = counted.get(molecule.id, {})
        sample_id = molecule.linked_sample_id
        assignment = (
            places[sample_id][0]
            if sample_id and places.get(sample_id)
            else None
        )

        context[molecule.id] = {
            "features": row.get("features", 0),
            "alignments": row.get("alignments", 0),
            "structures": row.get("structures", 0),
            "entries": row.get("entries", 0),
            "sample_visible": sample_id in visible_samples,
            "place": assignment.location.full_path if assignment else "",
            "place_position": assignment.position if assignment else "",
            "place_location_id": assignment.location_id if assignment else None,
        }

    return context


def attach_registry_context(user, molecules, universe=None):
    """Set .registry_context and .duplicates on every molecule in the list.

    Duplicates are looked up among ``universe`` (every record the user can
    see) so a search filter does not hide them.
    """
    context = record_context(user, molecules)
    duplicates = duplicate_groups(universe if universe is not None else molecules)

    for molecule in molecules:
        molecule.registry_context = context.get(molecule.id, {})
        molecule.duplicates = duplicates.get(molecule.id, [])

    return molecules


def inspector_context(user, molecule, universe):
    """JSON-safe context for the detail page inspector.

    ``universe`` is every record the user can see (for duplicate lookup).
    """
    from django.urls import reverse

    attach_registry_context(user, [molecule], universe)
    context = molecule.registry_context
    sample = molecule.linked_sample if context.get("sample_visible") else None
    place_id = context.get("place_location_id")

    return {
        "sample": (
            {
                "id": sample.sample_id,
                "url": reverse("sample_detail", args=[sample.id]),
            }
            if sample else None
        ),
        "place": context.get("place", ""),
        "place_position": context.get("place_position", ""),
        "place_url": (
            reverse("storage_workspace") + f"?location={place_id}"
            if place_id else ""
        ),
        "entries": context.get("entries", 0),
        "duplicates": [
            {
                "id": other_id,
                "name": other_name,
                "url": reverse("molecular_sequence_detail", args=[other_id]),
            }
            for other_id, other_name in molecule.duplicates
        ],
    }
