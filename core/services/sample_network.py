from django.urls import reverse

from core.models import HostRange
from core.models.samples.relationship import (
    SampleRelationship,
)


def build_sample_network_context(
    samples_qs,
):
    """
    Serialize the biological relationship network for an
    already-authorized Sample queryset.

    This service does not decide Sample visibility. Callers must
    supply the exact Sample scope that may be exposed.

    Relationships are serialized only when both endpoints belong
    to that supplied Sample scope.
    """
    qs = (
        samples_qs
        .select_related(
            "owner",
            "biobank",
            "research_group",
        )
        .prefetch_related(
            "collections",
        )
        .order_by(
            "pk"
        )
    )

    samples = list(
        qs
    )

    visible_ids = {
        sample.pk
        for sample in samples
    }

    nodes = []
    node_index = {}

    for sample in samples:
        sample_type = (
            sample.sample_type
            or ""
        )

        if "Bacterium" in sample_type:
            node_type = "bacteria"

        elif "Phage" in sample_type:
            node_type = "phage"

        elif "Plasmid" in sample_type:
            node_type = "plasmid"

        else:
            node_type = "generic"

        collections = sorted(
            {
                collection.name
                for collection
                in sample.collections.all()
                if collection.name
            },
            key=str.casefold,
        )

        node = {
            "id": sample.pk,
            "label": (
                sample.sample_id
                or f"Sample {sample.pk}"
            ),
            "sample_id": (
                sample.sample_id
                or ""
            ),
            "organism_name": (
                sample.organism_name
                or ""
            ),
            "sample_type": sample_type,
            "node_type": node_type,
            "group": node_type,
            "status": (
                sample.status
                or ""
            ),
            "status_label": (
                sample.get_status_display()
            ),
            "biosafety_level": (
                sample.biosafety_level
                or ""
            ),
            "owner": (
                sample.owner.username
                if sample.owner_id
                else ""
            ),
            "research_group": (
                sample.research_group.name
                if sample.research_group_id
                else ""
            ),
            "biobank": (
                sample.biobank.name
                if sample.biobank_id
                else ""
            ),
            "collections": collections,
            "collections_text": (
                ", ".join(
                    collections
                )
            ),
            "is_public": bool(
                sample.is_public
            ),
            "is_embargoed": bool(
                sample.is_embargoed
            ),
            "detail_url": reverse(
                "sample_detail",
                args=[
                    sample.pk,
                ],
            ),
            "degree": 0,
            "relationship_count": 0,
            "host_range_count": 0,
        }

        # Keep vis-network tooltips plain text. Richer metadata
        # is rendered through the dedicated Inspector.
        node["title"] = " | ".join(
            [
                (
                    node["organism_name"]
                    or "Unspecified organism"
                ),
                node["sample_id"],
                (
                    node["sample_type"]
                    or "Unspecified type"
                ),
            ]
        )

        nodes.append(
            node
        )

        node_index[
            sample.pk
        ] = node

    edges = []

    relationships = list(
        SampleRelationship.objects
        .filter(
            source_sample_id__in=visible_ids,
            target_sample_id__in=visible_ids,
        )
        .select_related(
            "source_sample",
            "target_sample",
            "created_by",
        )
        .order_by(
            "pk"
        )
    )

    lineage_types = {
        "aliquot",
        "passage",
        "mutated_from",
        "assembled_from",
        "extracted_from",
    }

    for relationship in relationships:
        relationship_type = (
            relationship.relationship_type
            or "other"
        )

        if relationship_type == "STORAGE":
            category = "storage"
            label = "Storage / Association"

        elif relationship_type in lineage_types:
            category = "lineage"
            label = (
                relationship
                .get_relationship_type_display()
            )

        elif relationship_type == "infects":
            category = "infection"
            label = (
                relationship
                .get_relationship_type_display()
            )

        else:
            category = "other"
            label = (
                relationship
                .get_relationship_type_display()
            )

        edge = {
            "id": (
                f"relationship-"
                f"{relationship.pk}"
            ),
            "from": (
                relationship
                .source_sample_id
            ),
            "to": (
                relationship
                .target_sample_id
            ),
            "relation_source":
                "sample_relationship",
            "relationship_type":
                relationship_type,
            "relationship_category":
                category,
            "label": label,
            "notes": (
                relationship.notes
                or ""
            ),
            "created_by": (
                relationship
                .created_by
                .username
                if relationship.created_by_id
                else ""
            ),
            "created_at": (
                relationship
                .created_at
                .isoformat()
                if relationship.created_at
                else ""
            ),
            "arrows": "to",
            "dashes": (
                category == "storage"
            ),
            "color": {
                "color": "#64748b",
            },
        }

        edges.append(
            edge
        )

        for sample_id in (
            relationship.source_sample_id,
            relationship.target_sample_id,
        ):
            node_index[
                sample_id
            ][
                "degree"
            ] += 1

            node_index[
                sample_id
            ][
                "relationship_count"
            ] += 1

    host_ranges = list(
        HostRange.objects
        .filter(
            phage_id__in=visible_ids,
            bacteria_id__in=visible_ids,
        )
        .select_related(
            "phage",
            "bacteria",
        )
        .order_by(
            "pk"
        )
    )

    for host_range in host_ranges:
        edge = {
            "id": (
                f"host-range-"
                f"{host_range.pk}"
            ),
            "from": (
                host_range.phage_id
            ),
            "to": (
                host_range.bacteria_id
            ),
            "relation_source":
                "host_range",
            "relationship_type":
                "host_range",
            "relationship_category":
                "infection",
            "label": "Infects",
            "notes": (
                host_range.notes
                or ""
            ),
            "is_isolation_host": bool(
                host_range
                .is_isolation_host
            ),
            "efficiency_eop": (
                host_range
                .efficiency_eop
            ),
            "arrows": "to",
            "dashes": False,
            "color": {
                "color": "#dc3545",
            },
        }

        edges.append(
            edge
        )

        for sample_id in (
            host_range.phage_id,
            host_range.bacteria_id,
        ):
            node_index[
                sample_id
            ][
                "degree"
            ] += 1

            node_index[
                sample_id
            ][
                "host_range_count"
            ] += 1

    connected_count = sum(
        1
        for node in nodes
        if node[
            "degree"
        ] > 0
    )

    return {
        "network_nodes": nodes,
        "network_edges": edges,
        "network_stats": {
            "visible_samples": len(
                nodes
            ),
            "connected_samples":
                connected_count,
            "isolated_samples": (
                len(
                    nodes
                )
                - connected_count
            ),
            "relationships": len(
                edges
            ),
            "sample_relationships": len(
                relationships
            ),
            "host_ranges": len(
                host_ranges
            ),
        },
    }
