"""Card previews for the Molecular Registry home.

Pure functions plus one query for features. Every SVG is built here from
numbers and from colours that are validated, so nothing user-typed reaches the
markup unescaped.
"""

import math
import re
from collections import defaultdict

from core.models.lab_tools.notebook import MolecularFeature

NUCLEOTIDE_TYPES = {"dna", "rna", "plasmid", "insert", "other"}
MAX_FEATURES_DRAWN = 40
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

# Average residue masses (Da) for proteins; water added once per chain.
_RESIDUE_MASS = {
    "A": 71.0788, "R": 156.1875, "N": 114.1038, "D": 115.0886,
    "C": 103.1388, "E": 129.1155, "Q": 128.1307, "G": 57.0519,
    "H": 137.1411, "I": 113.1594, "L": 113.1594, "K": 128.1741,
    "M": 131.1926, "F": 147.1766, "P": 97.1167, "S": 87.0782,
    "T": 101.1051, "W": 186.2132, "Y": 163.1760, "V": 99.1326,
}
_PKA_POS = {"K": 10.5, "R": 12.4, "H": 6.0}
_PKA_NEG = {"D": 3.9, "E": 4.1, "C": 8.3, "Y": 10.1}
_PKA_NTERM, _PKA_CTERM = 9.0, 2.0


def _color(value):
    return value if _COLOR.match(value or "") else "#868E96"


def features_by_molecule(molecule_ids):
    grouped = defaultdict(list)

    rows = (
        MolecularFeature.objects.filter(molecule_id__in=molecule_ids)
        .order_by("order", "start", "id")
        .values("molecule_id", "name", "start", "end", "color")
    )

    for row in rows:
        grouped[row["molecule_id"]].append(row)

    return grouped


def _polar(angle, radius):
    return 50 + radius * math.cos(angle), 50 + radius * math.sin(angle)


def _circular_svg(length, features):
    parts = [
        '<svg viewBox="0 0 100 100" class="mr-thumb-svg" aria-hidden="true">',
        '<circle cx="50" cy="50" r="34" fill="none" stroke="#DDE3EA" '
        'stroke-width="9"/>',
    ]

    for feature in features[:MAX_FEATURES_DRAWN]:
        start, end = feature["start"], feature["end"]

        if not length or start < 1 or end < start:
            continue

        span = min(end, length) - start + 1

        if span >= length:
            continue

        a1 = (start - 1) / length * 2 * math.pi - math.pi / 2
        a2 = min(end, length) / length * 2 * math.pi - math.pi / 2
        x1, y1 = _polar(a1, 34)
        x2, y2 = _polar(a2, 34)
        large = 1 if span / length > 0.5 else 0
        parts.append(
            f'<path d="M{x1:.2f} {y1:.2f} A34 34 0 {large} 1 '
            f'{x2:.2f} {y2:.2f}" fill="none" stroke="{_color(feature["color"])}" '
            'stroke-width="9"/>'
        )

    parts.append("</svg>")

    return "".join(parts)


def _linear_svg(length, features):
    parts = [
        '<svg viewBox="0 0 200 40" class="mr-thumb-svg" preserveAspectRatio='
        '"none" aria-hidden="true">',
        '<rect x="4" y="17" width="192" height="6" rx="3" fill="#DDE3EA"/>',
    ]

    for feature in features[:MAX_FEATURES_DRAWN]:
        start, end = feature["start"], feature["end"]

        if not length or start < 1 or end < start:
            continue

        x = 4 + (start - 1) / length * 192
        width = max((min(end, length) - start + 1) / length * 192, 2)
        parts.append(
            f'<rect x="{x:.2f}" y="11" width="{width:.2f}" height="18" rx="3" '
            f'fill="{_color(feature["color"])}"/>'
        )

    parts.append("</svg>")

    return "".join(parts)


def melting_temperature(sequence):
    """Basic Tm: Wallace rule up to 13 nt, GC-based formula above."""
    seq = (sequence or "").upper()
    n = len(seq)

    if not n:
        return None

    gc = seq.count("G") + seq.count("C")

    if n <= 13:
        return round(2 * (n - gc) + 4 * gc, 1)

    return round(64.9 + 41 * (gc - 16.4) / n, 1)


def protein_mass_kda(sequence):
    seq = (sequence or "").upper()
    residues = [r for r in seq if r in _RESIDUE_MASS]

    if not residues:
        return None

    return round((sum(_RESIDUE_MASS[r] for r in residues) + 18.015) / 1000, 1)


def protein_pi(sequence):
    seq = [r for r in (sequence or "").upper() if r in _RESIDUE_MASS]

    if not seq:
        return None

    def charge(ph):
        total = 1 / (1 + 10 ** (ph - _PKA_NTERM))
        total -= 1 / (1 + 10 ** (_PKA_CTERM - ph))

        for residue in seq:
            if residue in _PKA_POS:
                total += 1 / (1 + 10 ** (ph - _PKA_POS[residue]))
            elif residue in _PKA_NEG:
                total -= 1 / (1 + 10 ** (_PKA_NEG[residue] - ph))

        return total

    low, high = 0.0, 14.0

    for _ in range(40):
        mid = (low + high) / 2

        if charge(mid) > 0:
            low = mid
        else:
            high = mid

    return round((low + high) / 2, 1)


def card_for(molecule, features):
    """Return the preview and stats shown on one registry card."""
    kind = molecule.sequence_type
    length = molecule.length or 0
    sequence = molecule.sequence or ""
    gc = molecule.gc_content
    card = {"preview_kind": "linear", "preview_html": "", "stats": []}

    if kind == "primer":
        shown = sequence[:40]
        clamp = shown[-5:] if len(shown) > 5 else ""
        body = shown[: len(shown) - len(clamp)]
        card["preview_kind"] = "primer"
        card["primer_body"] = body
        card["primer_clamp"] = clamp
        card["stats"] = [(length, "nt")]

        tm = melting_temperature(sequence)

        if tm is not None:
            card["stats"].append((f"{tm:g} °C", "Tm"))

        if gc is not None:
            card["stats"].append((f"{gc:g}%", "GC"))

        return card

    if kind == "protein":
        card["preview_kind"] = "protein"
        card["preview_html"] = _linear_svg(length, features)
        card["stats"] = [(length, "aa")]
        mass = protein_mass_kda(sequence)
        pi = protein_pi(sequence)

        if mass is not None:
            card["stats"].append((f"{mass:g}", "kDa"))

        if pi is not None:
            card["stats"].append((f"{pi:g}", "pI"))

        return card

    circular = molecule.topology == "circular"
    card["preview_kind"] = "circular" if circular else "linear"
    card["preview_html"] = (
        _circular_svg(length, features)
        if circular
        else _linear_svg(length, features)
    )
    unit = "nt" if kind == "rna" else "bp"
    card["stats"] = [(f"{length:,}", unit)]

    if features:
        card["stats"].append((len(features), "features"))

    if gc is not None:
        card["stats"].append((f"{gc:g}%", "GC"))

    return card


def attach_cards(molecules):
    grouped = features_by_molecule([m.id for m in molecules])

    for molecule in molecules:
        molecule.card = card_for(molecule, grouped.get(molecule.id, []))

    return molecules
