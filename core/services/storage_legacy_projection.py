"""Read-only projection of historical Sample storage paths.

These virtual locations are not StorageLocation records and must
never be used as transfer destinations.
"""

from hashlib import sha256
import re


def build_legacy_storage_projection(records):
    """Convert recognizable legacy paths into visualization-only nodes.

    records: iterable of (sample_identifier, storage_path).
    """
    nodes = {}
    samples = []
    unparsed = 0

    def virtual_id(*parts):
        raw = "\\0".join(parts).encode("utf-8")
        return "legacy:" + sha256(raw).hexdigest()[:24]

    for sample_identifier, raw_path in records:
        parts = [
            part.strip()
            for part in str(raw_path or "").split(">")
        ]

        if (
            len(parts) != 3
            or not re.fullmatch(
                r"Freezer\s+\S.*",
                parts[0],
                re.IGNORECASE,
            )
            or not re.fullmatch(
                r"Caixa\s+\S.*",
                parts[1],
                re.IGNORECASE,
            )
            or not re.fullmatch(
                r"[A-Z][1-9][0-9]?",
                parts[2],
                re.IGNORECASE,
            )
        ):
            unparsed += 1
            continue

        freezer, box, position = parts
        position = position.upper()

        freezer_id = virtual_id("freezer", freezer)
        box_id = virtual_id("box", freezer, box)

        nodes.setdefault(freezer_id, {
            "id": freezer_id,
            "parent": None,
            "name": freezer + " · historical",
            "kind": "freezer",
            "type": "Freezer (historical)",
            "path": freezer,
            "rank": 0,
            "active": True,
            "legacy": True,
        })

        nodes.setdefault(box_id, {
            "id": box_id,
            "parent": freezer_id,
            "name": box + " · historical",
            "kind": "box",
            "type": "Box (historical)",
            "path": freezer + " > " + box,
            "rank": 0,
            "active": True,
            "legacy": True,
        })

        samples.append({
            "box": box_id,
            "code": str(sample_identifier),
            "position": position,
            "status": "active",
            "legacy": True,
        })

    return {
        "nodes": list(nodes.values()),
        "samples": samples,
        "unparsed": unparsed,
        "source": "sample.storage_location",
    }
