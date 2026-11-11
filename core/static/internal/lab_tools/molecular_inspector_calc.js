/*
 * Pure sequence calculations for the Molecular Registry inspector.
 * No DOM access, so the same file is tested with Node.
 */
(function (root, factory) {
    "use strict";

    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.BiobankMolecularCalc = factory();
    }
}(typeof self !== "undefined" ? self : this, function () {
    "use strict";

    const COMPLEMENT = {
        A: "T", T: "A", U: "A", G: "C", C: "G",
        R: "Y", Y: "R", S: "S", W: "W", K: "M", M: "K",
        B: "V", V: "B", D: "H", H: "D", N: "N",
    };

    const CODONS = {};
    const AMINO = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG";
    const BASES = "TCAG";

    for (let i = 0; i < 64; i++) {
        CODONS[
            BASES[Math.floor(i / 16)] +
            BASES[Math.floor(i / 4) % 4] +
            BASES[i % 4]
        ] = AMINO[i];
    }

    function clean(sequence) {
        return String(sequence || "").replace(/\s+/g, "").toUpperCase();
    }

    /** Slice 1-based inclusive coordinates; start > end wraps the origin. */
    function slice(sequence, start, end) {
        const seq = clean(sequence);
        const s = Number(start);
        const e = Number(end);

        if (!seq || !(s >= 1) || !(e >= 1) || s > seq.length || e > seq.length) {
            return "";
        }

        return s <= e
            ? seq.slice(s - 1, e)
            : seq.slice(s - 1) + seq.slice(0, e);
    }

    function gcPercent(sequence) {
        const seq = clean(sequence);
        let gc = 0;
        let total = 0;

        for (const base of seq) {
            if ("GCS".includes(base)) {
                gc += 1;
                total += 1;
            } else if ("ATUW".includes(base)) {
                total += 1;
            }
        }

        return total ? Math.round((gc / total) * 1000) / 10 : null;
    }

    function reverseComplement(sequence, rna) {
        const seq = clean(sequence);
        let out = "";

        for (let i = seq.length - 1; i >= 0; i--) {
            out += COMPLEMENT[seq[i]] || "N";
        }

        return rna ? out.replace(/T/g, "U") : out;
    }

    function translate(sequence, frame) {
        const seq = clean(sequence).replace(/U/g, "T");
        const offset = Math.max(0, Math.min(2, Number(frame) || 0));
        let protein = "";

        for (let i = offset; i + 3 <= seq.length; i += 3) {
            protein += CODONS[seq.slice(i, i + 3)] || "X";
        }

        return protein;
    }

    /** Every forward ORF (ATG..stop) of at least `min` amino acids. */
    function scanOrfs(seq, min, strand) {
        const found = [];

        for (let frame = 0; frame < 3; frame++) {
            let start = -1;

            for (let i = frame; i + 3 <= seq.length; i += 3) {
                const codon = seq.slice(i, i + 3);

                if (start < 0 && codon === "ATG") {
                    start = i;
                }

                if (start >= 0 && CODONS[codon] === "*") {
                    const length = (i - start) / 3;

                    if (length >= min) {
                        found.push({
                            start: start + 1,
                            end: i + 3,
                            aminoAcids: length,
                            frame: frame + 1,
                            strand,
                        });
                    }

                    start = -1;
                }
            }
        }

        return found;
    }

    /**
     * ORFs (ATG to stop, linear). options.strand: "+" (default), "-" or
     * "both". Coordinates are always on the forward strand, 1-based
     * inclusive; for "-" ORFs start < end still holds and frame counts
     * from the reverse complement's first base.
     */
    function findOrfs(sequence, minAminoAcids, options) {
        const seq = clean(sequence).replace(/U/g, "T");
        const min = Number(minAminoAcids) || 30;
        const which = (options && options.strand) || "+";
        let found = [];

        if (which === "+" || which === "both") {
            found = found.concat(scanOrfs(seq, min, "+"));
        }

        if (which === "-" || which === "both") {
            const length = seq.length;

            scanOrfs(reverseComplement(seq), min, "-").forEach(orf => {
                found.push({
                    start: length - orf.end + 1,
                    end: length - orf.start + 1,
                    aminoAcids: orf.aminoAcids,
                    frame: orf.frame,
                    strand: "-",
                });
            });
        }

        return found.sort((a, b) => b.aminoAcids - a.aminoAcids);
    }

    /** Longest forward ORF over the three frames, or null. */
    function longestOrf(sequence, minAminoAcids) {
        return findOrfs(sequence, minAminoAcids)[0] || null;
    }

    // SantaLucia (1998) unified nearest-neighbour parameters.
    const NN = {
        AA: [-7.9, -22.2], AT: [-7.2, -20.4], TA: [-7.2, -21.3],
        CA: [-8.5, -22.7], GT: [-8.4, -22.4], CT: [-7.8, -21.0],
        GA: [-8.2, -22.2], CG: [-10.6, -27.2], GC: [-9.8, -24.4],
        GG: [-8.0, -19.9],
    };
    const NN_ALIAS = {
        TT: "AA", TG: "CA", AC: "GT", AG: "CT", TC: "GA", CC: "GG",
    };

    const MG_DNTP_KA = 3.0e4;
    const TM_STORE = "biobank.tm-conditions.v1";

    /** Reaction conditions the Tm of every primer follows (set in the Primers window, kept in the browser). */
    const TM_PRESETS = {
        default: {label: "Default: 50 mM Na⁺, 250 nM, equal strands", monovalentMM: 50, magnesiumMM: 0, dntpMM: 0, primerUM: 0.25, primerExcess: false, dmsoPercent: 0, formamidePercent: 0},
        taq: {label: "PCR, Taq-like: 50 mM K⁺, 1.5 mM Mg²⁺, 0.8 mM dNTP, 0.2 µM primer", monovalentMM: 50, magnesiumMM: 1.5, dntpMM: 0.8, primerUM: 0.2, primerExcess: true, dmsoPercent: 0, formamidePercent: 0},
        salt: {label: "PCR, more salt: 100 mM K⁺, 2 mM Mg²⁺, 0.8 mM dNTP, 0.5 µM primer", monovalentMM: 100, magnesiumMM: 2, dntpMM: 0.8, primerUM: 0.5, primerExcess: true, dmsoPercent: 0, formamidePercent: 0},
    };
    let conditions = {};

    try {
        if (typeof window !== "undefined" && window.localStorage) {
            conditions = JSON.parse(window.localStorage.getItem(TM_STORE) || "{}") || {};
        }
    } catch (error) {
        conditions = {};
    }

    function setTmConditions(next) {
        conditions = Object.assign({}, next || {});

        try {
            if (typeof window !== "undefined" && window.localStorage) {
                window.localStorage.setItem(TM_STORE, JSON.stringify(conditions));
            }
        } catch (error) {
            // storage can be blocked; the conditions still apply for this page
        }
    }

    const getTmConditions = () => Object.assign({}, conditions);

    /** Mg2+ left (molar) after dNTPs bind it 1:1. */
    function freeMagnesium(mg, dntp) {
        if (mg <= 0) return 0;
        if (dntp <= 0) return mg;

        const b = 1 + MG_DNTP_KA * (mg + dntp);
        const bound = (b - Math.sqrt(b * b - 4 * MG_DNTP_KA * MG_DNTP_KA * mg * dntp)) / (2 * MG_DNTP_KA);

        return Math.max(mg - bound, 0);
    }

    /** 1/Tm (kelvin) corrected from 1 M Na+ to the given monovalent and free Mg2+ (Owczarzy et al. 2008). */
    function owczarzy(inv1M, gcFraction, length, mon, mg) {
        const lnMon = mon > 0 ? Math.log(mon) : 0;
        const monovalent = () => inv1M + (4.29 * gcFraction - 3.95) * 1e-5 * lnMon + 9.40e-6 * lnMon * lnMon;

        if (mg <= 0) return monovalent();

        const ratio = mon > 0 ? Math.sqrt(mg) / mon : Infinity;

        if (ratio < 0.22) return monovalent();

        let a = 3.92e-5;
        let d = 1.42e-5;
        let g = 8.31e-5;
        const b = -9.11e-6;
        const c = 6.26e-5;
        const e = -4.82e-4;
        const f = 5.25e-4;

        if (ratio < 6.0) {
            a = 3.92e-5 * (0.843 - 0.352 * Math.sqrt(mon) * lnMon);
            d = 1.42e-5 * (1.279 - 4.03e-3 * lnMon - 8.03e-3 * lnMon * lnMon);
            g = 8.31e-5 * (0.486 - 0.258 * lnMon + 5.25e-3 * Math.pow(lnMon, 3));
        }

        const lnMg = Math.log(mg);

        return inv1M + a + b * lnMg + gcFraction * (c + d * lnMg) + (e + f * lnMg + g * lnMg * lnMg) / (2 * (length - 1));
    }

    /**
     * Melting temperature in degrees C, nearest-neighbour method (SantaLucia 1998).
     * Returns null for sequences with ambiguity codes or outside 8-120 nt.
     *
     * Options (all optional; the defaults are 50 mM Na+, 250 nM strands, as before):
     *   monovalentMM, magnesiumMM, dntpMM, primerUM, primerExcess, dmsoPercent, formamidePercent,
     *   method: "santalucia" | "owczarzy" | "auto" (owczarzy when Mg2+ is given).
     * The older sodiumMolar / strandMolar options still work.
     */
    function meltingTemperature(sequence, options) {
        const seq = clean(sequence).replace(/U/g, "T");
        const opts = options || conditions;
        const monMolar = opts.monovalentMM !== undefined ? Math.max(Number(opts.monovalentMM), 0) / 1000 : (Number(opts.sodiumMolar) || 0.05);
        const mg = Math.max(Number(opts.magnesiumMM) || 0, 0) / 1000;
        const dntp = Math.max(Number(opts.dntpMM) || 0, 0) / 1000;
        const strand = opts.primerUM !== undefined ? Math.max(Number(opts.primerUM), 1e-6) * 1e-6 : (Number(opts.strandMolar) || 250e-9);
        let method = opts.method || "auto";

        if (seq.length < 8 || seq.length > 120 || /[^ACGT]/.test(seq)) {
            return null;
        }

        if (method === "auto") method = mg > 0 ? "owczarzy" : "santalucia";

        let dh = 0;
        let ds = 0;

        for (let i = 0; i + 1 < seq.length; i++) {
            const pair = seq.slice(i, i + 2);
            const key = NN[pair] ? pair : NN_ALIAS[pair];
            dh += NN[key][0];
            ds += NN[key][1];
        }

        for (const end of [seq[0], seq[seq.length - 1]]) {
            if (end === "G" || end === "C") {
                dh += 0.1;
                ds += -2.8;
            } else {
                dh += 2.3;
                ds += 4.1;
            }
        }

        const selfComplementary = seq === reverseComplement(seq);

        if (selfComplementary) {
            ds += -1.4;
        }

        const R = 1.987;
        const x = selfComplementary || opts.primerExcess ? 1 : 4;
        let tm;

        if (method === "santalucia") {
            ds += 0.368 * (seq.length - 1) * Math.log(Math.max(monMolar, 1e-6));
            tm = (dh * 1000) / (ds + R * Math.log(strand / x)) - 273.15;
        } else {
            const tm1M = (dh * 1000) / (ds + R * Math.log(strand / x));
            const gc = (seq.split("G").length - 1 + seq.split("C").length - 1) / seq.length;

            tm = 1 / owczarzy(1 / tm1M, gc, seq.length, Math.max(monMolar, 1e-9), freeMagnesium(mg, dntp)) - 273.15;
        }

        tm -= 0.6 * (Number(opts.dmsoPercent) || 0) + 0.65 * (Number(opts.formamidePercent) || 0);

        return Math.round(tm * 10) / 10;
    }

    /** Count of G/C among the last five bases (3' clamp) and longest run. */
    function primerChecks(sequence) {
        const seq = clean(sequence);
        const tail = seq.slice(-5);
        let longest = 0;
        let run = 0;
        let previous = "";

        for (const base of seq) {
            run = base === previous ? run + 1 : 1;
            previous = base;
            longest = Math.max(longest, run);
        }

        return {
            clampGc: (tail.match(/[GC]/g) || []).length,
            longestRun: longest,
            endsWithGc: /[GC]$/.test(seq),
        };
    }

    const RESIDUE_MASS = {
        A: 71.0788, R: 156.1875, N: 114.1038, D: 115.0886, C: 103.1388,
        E: 129.1155, Q: 128.1307, G: 57.0519, H: 137.1411, I: 113.1594,
        L: 113.1594, K: 128.1741, M: 131.1926, F: 147.1766, P: 97.1167,
        S: 87.0782, T: 101.1051, W: 186.2132, Y: 163.1760, V: 99.1326,
    };
    const WATER = 18.01524;

    function chargeAtPh(counts, ph) {
        const pos = (pka, n) => n / (1 + Math.pow(10, ph - pka));
        const neg = (pka, n) => n / (1 + Math.pow(10, pka - ph));

        return pos(8.6, 1) + pos(10.8, counts.K || 0) +
            pos(12.5, counts.R || 0) + pos(6.5, counts.H || 0) -
            neg(3.6, 1) - neg(3.9, counts.D || 0) - neg(4.1, counts.E || 0) -
            neg(8.5, counts.C || 0) - neg(10.1, counts.Y || 0);
    }

    function proteinProperties(sequence) {
        const seq = clean(sequence).replace(/\*/g, "");
        const counts = {};
        let mass = WATER;
        let known = 0;

        for (const residue of seq) {
            counts[residue] = (counts[residue] || 0) + 1;

            if (RESIDUE_MASS[residue]) {
                mass += RESIDUE_MASS[residue];
                known += 1;
            }
        }

        if (!known) {
            return null;
        }

        let low = 0;
        let high = 14;

        for (let i = 0; i < 60; i++) {
            const mid = (low + high) / 2;

            if (chargeAtPh(counts, mid) > 0) {
                low = mid;
            } else {
                high = mid;
            }
        }

        const cystines = Math.floor((counts.C || 0) / 2);

        return {
            residues: seq.length,
            massDa: Math.round(mass * 10) / 10,
            isoelectricPoint: Math.round(((low + high) / 2) * 100) / 100,
            chargeAt74: (Math.round(chargeAtPh(counts, 7.4) * 10) / 10) || 0,
            extinction280: (counts.W || 0) * 5500 +
                (counts.Y || 0) * 1490 + cystines * 125,
            ambiguous: seq.length - known,
        };
    }

    return {
        clean,
        slice,
        gcPercent,
        reverseComplement,
        translate,
        findOrfs,
        longestOrf,
        meltingTemperature,
        setTmConditions,
        getTmConditions,
        TM_PRESETS,
        primerChecks,
        proteinProperties,
    };
}));
