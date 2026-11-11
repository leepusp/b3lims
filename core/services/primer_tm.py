"""Melting temperature of a DNA oligo by nearest-neighbour thermodynamics.

Same method as the primer window of the Molecular Registry (``molecular_inspector_calc.js``), so a
notebook, the API and the browser give the same number for the same conditions.

* Nearest-neighbour parameters: SantaLucia (1998), unified set.
* Salt: ``santalucia`` keeps the classic sodium term; ``owczarzy`` uses Owczarzy et al. (2008), which
  also handles Mg2+ and dNTPs (they bind Mg2+, so only the free Mg2+ counts).
* Additives: DMSO lowers Tm by about 0.6 C per 1 %, formamide by about 0.65 C per 1 % (approximate).

This is an estimate: polymerase vendors use their own buffers and calculators, so compare with theirs
before ordering when the exact annealing temperature matters.
"""

from __future__ import annotations

import math

NN = {
    "AA": (-7.9, -22.2), "AT": (-7.2, -20.4), "TA": (-7.2, -21.3), "CA": (-8.5, -22.7), "GT": (-8.4, -22.4),
    "CT": (-7.8, -21.0), "GA": (-8.2, -22.2), "CG": (-10.6, -27.2), "GC": (-9.8, -24.4), "GG": (-8.0, -19.9),
}
ALIAS = {"TT": "AA", "TG": "CA", "AC": "GT", "AG": "CT", "TC": "GA", "CC": "GG"}
R = 1.987
MG_DNTP_KA = 3.0e4  # M^-1, Mg2+ + dNTP binding (Owczarzy 2008)
DMSO_PER_PERCENT = 0.6
FORMAMIDE_PER_PERCENT = 0.65
MIN_LENGTH, MAX_LENGTH = 8, 120
COMPLEMENT = str.maketrans("ACGT", "TGCA")


def _clean(sequence):
    return "".join(c for c in (sequence or "").upper().replace("U", "T") if not c.isspace())


def free_magnesium(mg_molar, dntp_molar):
    """Mg2+ left after dNTPs bind it 1:1 (quadratic for the binding equilibrium)."""
    if mg_molar <= 0:
        return 0.0
    if dntp_molar <= 0:
        return mg_molar

    b = 1 + MG_DNTP_KA * (mg_molar + dntp_molar)
    bound = (b - math.sqrt(b * b - 4 * MG_DNTP_KA**2 * mg_molar * dntp_molar)) / (2 * MG_DNTP_KA)

    return max(mg_molar - bound, 0.0)


def _owczarzy(inv_tm_1m, gc_fraction, length, mon, mg):
    """1/Tm (kelvin) corrected from 1 M Na+ to the given monovalent and free Mg2+ (molar)."""
    ln_mon = math.log(mon) if mon > 0 else 0.0

    if mg <= 0:
        return inv_tm_1m + (4.29 * gc_fraction - 3.95) * 1e-5 * ln_mon + 9.40e-6 * ln_mon**2

    ratio = math.sqrt(mg) / mon if mon > 0 else math.inf

    if ratio < 0.22:
        return inv_tm_1m + (4.29 * gc_fraction - 3.95) * 1e-5 * ln_mon + 9.40e-6 * ln_mon**2

    a, b, c, d, e, f, g = 3.92e-5, -9.11e-6, 6.26e-5, 1.42e-5, -4.82e-4, 5.25e-4, 8.31e-5

    if ratio < 6.0:
        a = 3.92e-5 * (0.843 - 0.352 * math.sqrt(mon) * ln_mon)
        d = 1.42e-5 * (1.279 - 4.03e-3 * ln_mon - 8.03e-3 * ln_mon**2)
        g = 8.31e-5 * (0.486 - 0.258 * ln_mon + 5.25e-3 * ln_mon**3)

    ln_mg = math.log(mg)

    return inv_tm_1m + a + b * ln_mg + gc_fraction * (c + d * ln_mg) + (e + f * ln_mg + g * ln_mg**2) / (2 * (length - 1))


def melting_temperature(
    sequence, *, monovalent_mM=50.0, magnesium_mM=0.0, dntp_mM=0.0, primer_uM=0.25, primer_excess=False,
    dmso_percent=0.0, formamide_percent=0.0, method="auto",
):
    """Tm in degrees C rounded to 0.1, or None for ambiguity codes or a length outside 8-120 nt.

    ``primer_excess`` treats the primer as being in large excess over its template (a PCR), instead of
    equal strands. ``method`` is ``santalucia``, ``owczarzy`` or ``auto`` (owczarzy when Mg2+ is given).
    """
    seq = _clean(sequence)

    if not (MIN_LENGTH <= len(seq) <= MAX_LENGTH) or set(seq) - set("ACGT"):
        return None

    mon = max(float(monovalent_mM), 0.0) / 1000
    mg = max(float(magnesium_mM), 0.0) / 1000
    dntp = max(float(dntp_mM), 0.0) / 1000
    strand = max(float(primer_uM), 1e-6) * 1e-6

    if method == "auto":
        method = "owczarzy" if mg > 0 else "santalucia"

    dh = ds = 0.0

    for i in range(len(seq) - 1):
        pair = seq[i:i + 2]
        h, s = NN[pair if pair in NN else ALIAS[pair]]
        dh += h
        ds += s

    for end in (seq[0], seq[-1]):
        if end in "GC":
            dh += 0.1
            ds += -2.8
        else:
            dh += 2.3
            ds += 4.1

    symmetric = seq == seq.translate(COMPLEMENT)[::-1]

    if symmetric:
        ds += -1.4

    x = 1 if (symmetric or primer_excess) else 4

    if method == "santalucia":
        ds += 0.368 * (len(seq) - 1) * math.log(max(mon, 1e-6))
        tm = dh * 1000 / (ds + R * math.log(strand / x)) - 273.15
    else:
        tm_1m = dh * 1000 / (ds + R * math.log(strand / x))
        gc = (seq.count("G") + seq.count("C")) / len(seq)
        tm = 1 / _owczarzy(1 / tm_1m, gc, len(seq), max(mon, 1e-9), free_magnesium(mg, dntp)) - 273.15

    tm -= DMSO_PER_PERCENT * float(dmso_percent) + FORMAMIDE_PER_PERCENT * float(formamide_percent)

    return round(tm, 1)
