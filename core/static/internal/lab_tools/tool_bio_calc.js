/*
 * Pure calculations for the RNA and Protein workbenches: composition, mass,
 * charge, isoelectric point, hydropathy, translation and a simplified RNA
 * secondary-structure prediction. No DOM; tested with Node.
 */
(function (root, factory) {
    "use strict";

    if (typeof module === "object" && module.exports) module.exports = factory();
    else root.BiobankBioCalc = factory();
}(typeof self !== "undefined" ? self : this, function () {
    "use strict";

    const cleanLetters = text => String(text || "").replace(/^>.*$/gm, "").replace(/[^A-Za-z*]/g, "").toUpperCase();
    const toRna = text => cleanLetters(text).replace(/T/g, "U");
    const toDna = text => cleanLetters(text).replace(/U/g, "T");
    const COMP = {A: "T", T: "A", G: "C", C: "G", U: "A", R: "Y", Y: "R", K: "M", M: "K", S: "S", W: "W", B: "V", V: "B", D: "H", H: "D", N: "N"};

    function reverseComplement(text, rna) {
        const out = cleanLetters(text).split("").reverse().map(ch => COMP[ch] || "N").join("");

        return rna ? out.replace(/T/g, "U") : out;
    }

    /* ---------- RNA ---------- */

    // Nucleotide monophosphate residue masses (NMP − H2O), g/mol.
    const NT_MASS = {A: 329.2056, C: 305.1808, G: 345.2050, U: 306.1661};

    function rnaReport(text) {
        const seq = toRna(text);
        const counts = {A: 0, C: 0, G: 0, U: 0, other: 0};

        for (const ch of seq) {
            if (counts[ch] !== undefined && ch !== "other") counts[ch] += 1;
            else counts.other += 1;
        }

        const known = counts.A + counts.C + counts.G + counts.U;
        // Single strand with a 5' hydroxyl: residues + water − one phosphate (HPO3).
        const mass = known ? counts.A * NT_MASS.A + counts.C * NT_MASS.C + counts.G * NT_MASS.G + counts.U * NT_MASS.U + 18.0153 - 79.9799 : 0;

        return {
            length: seq.length,
            counts,
            gc: known ? (counts.G + counts.C) / known * 100 : 0,
            mass,
            // ε260 (nearest-neighbour is better; this is the common additive estimate), M⁻¹cm⁻¹.
            epsilon260: counts.A * 15400 + counts.C * 7200 + counts.G * 11500 + counts.U * 9900,
        };
    }

    /* ---------- protein ---------- */

    const RESIDUE_MASS = {
        A: 71.0788, R: 156.1875, N: 114.1038, D: 115.0886, C: 103.1388, E: 129.1155, Q: 128.1307, G: 57.0519,
        H: 137.1411, I: 113.1594, L: 113.1594, K: 128.1741, M: 131.1926, F: 147.1766, P: 97.1167, S: 87.0782,
        T: 101.1051, W: 186.2132, Y: 163.1760, V: 99.1326,
    };
    const KYTE = {
        A: 1.8, R: -4.5, N: -3.5, D: -3.5, C: 2.5, Q: -3.5, E: -3.5, G: -0.4, H: -3.2, I: 4.5,
        L: 3.8, K: -3.9, M: 1.9, F: 2.8, P: -1.6, S: -0.8, T: -0.7, W: -0.9, Y: -1.3, V: 4.2,
    };
    const WATER = 18.01524;
    const AMINO = "ACDEFGHIKLMNPQRSTVWY".split("");

    function chargeAt(counts, ph) {
        const pos = (pka, n) => n / (1 + Math.pow(10, ph - pka));
        const neg = (pka, n) => n / (1 + Math.pow(10, pka - ph));

        return pos(8.6, 1) + pos(10.8, counts.K || 0) + pos(12.5, counts.R || 0) + pos(6.5, counts.H || 0)
            - neg(3.6, 1) - neg(3.9, counts.D || 0) - neg(4.1, counts.E || 0) - neg(8.5, counts.C || 0) - neg(10.1, counts.Y || 0);
    }

    function proteinReport(text, ph) {
        const seq = cleanLetters(text).replace(/\*/g, "");
        const counts = {};
        let mass = WATER;
        let known = 0;
        let kyte = 0;

        for (const ch of seq) {
            counts[ch] = (counts[ch] || 0) + 1;

            if (RESIDUE_MASS[ch]) {
                mass += RESIDUE_MASS[ch];
                kyte += KYTE[ch];
                known += 1;
            }
        }

        if (!known) return null;

        let low = 0;
        let high = 14;

        for (let i = 0; i < 60; i += 1) {
            const mid = (low + high) / 2;

            if (chargeAt(counts, mid) > 0) low = mid; else high = mid;
        }

        const w = counts.W || 0;
        const y = counts.Y || 0;
        const cystines = Math.floor((counts.C || 0) / 2);
        const n = known;
        const pH = ph === undefined ? 7.4 : Number(ph);

        return {
            length: seq.length,
            known,
            counts,
            mass,
            pI: (low + high) / 2,
            charge: chargeAt(counts, pH),
            ph: pH,
            // Pace et al.: ε280 of the folded protein (cystines) and of the reduced one.
            epsilon280: w * 5500 + y * 1490 + cystines * 125,
            epsilon280Reduced: w * 5500 + y * 1490,
            gravy: kyte / n,
            aliphatic: ((counts.A || 0) + 2.9 * (counts.V || 0) + 3.9 * ((counts.I || 0) + (counts.L || 0))) / n * 100,
            composition: AMINO.map(a => [a, counts[a] || 0]),
        };
    }

    // Kyte–Doolittle moving average (odd window), one value per residue (null at the edges).
    function hydropathy(text, windowSize) {
        const seq = cleanLetters(text).replace(/\*/g, "");
        const size = Math.max(3, Math.min(41, (Math.round(Number(windowSize) || 9) | 1)));
        const half = (size - 1) / 2;
        const out = [];

        for (let i = 0; i < seq.length; i += 1) {
            if (i < half || i >= seq.length - half) {
                out.push(null);
                continue;
            }

            let sum = 0;

            for (let k = i - half; k <= i + half; k += 1) sum += KYTE[seq[k]] || 0;

            out.push(sum / size);
        }

        return out;
    }

    /* ---------- translation ---------- */

    const BASES = "TCAG";
    const AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG";
    const CODON = {};

    for (let a = 0; a < 4; a += 1) {
        for (let b = 0; b < 4; b += 1) {
            for (let c = 0; c < 4; c += 1) CODON[BASES[a] + BASES[b] + BASES[c]] = AAS[a * 16 + b * 4 + c];
        }
    }

    function translate(text, frame) {
        const dna = toDna(text);
        let out = "";

        for (let i = Number(frame) || 0; i + 3 <= dna.length; i += 3) out += CODON[dna.slice(i, i + 3)] || "X";

        return out;
    }

    // Six-frame ORFs (ATG … stop) of at least `min` residues; positions are 1-based on the given strand's coordinates.
    function findOrfs(text, min) {
        const dna = toDna(text);
        const minLen = Math.max(1, Number(min) || 30);
        const found = [];

        [["+", dna], ["-", reverseComplement(dna)]].forEach(([strand, seq]) => {
            for (let frame = 0; frame < 3; frame += 1) {
                const protein = translate(seq, frame);
                let start = -1;

                for (let i = 0; i <= protein.length; i += 1) {
                    const aa = i < protein.length ? protein[i] : "*";

                    if (start < 0 && aa === "M") start = i;

                    if (aa === "*" || i === protein.length) {
                        if (start >= 0 && i - start >= minLen) {
                            found.push({
                                strand,
                                frame: frame + 1,
                                start: frame + start * 3 + 1,
                                end: frame + i * 3 + (aa === "*" ? 3 : 0),
                                protein: protein.slice(start, i),
                                stop: aa === "*",
                            });
                        }

                        start = -1;
                    }
                }
            }
        });

        return found.sort((a, b) => b.protein.length - a.protein.length);
    }

    /* ---------- RNA secondary structure (simplified Zuker) ---------- */

    const RT = 0.6163;
    const STACK = {
        AAUU: -0.93, AUUA: -1.10, UAAU: -1.33, CUGA: -2.08, CAGU: -2.11, GUCA: -2.24, GACU: -2.35, CGGC: -2.36, GGCC: -3.26, GCCG: -3.42,
    };

    function pairType(a, b) {
        const p = a + b;

        return p === "AU" || p === "UA" || p === "GC" || p === "CG" || p === "GU" || p === "UG" ? p : "";
    }

    function stackEnergy(a, b, c, d) {
        // Pair (a,b) followed by pair (c,d) towards the inside: 5'-a c-3' / 3'-b d-5'.
        const key = a + c + b + d;
        const mirror = d + b + c + a;

        if (STACK[key] !== undefined) return STACK[key];
        if (STACK[mirror] !== undefined) return STACK[mirror];

        const wobble = pairType(a, b) === "GU" || pairType(a, b) === "UG" || pairType(c, d) === "GU" || pairType(c, d) === "UG";

        if (wobble) {
            const other = [pairType(a, b), pairType(c, d)].filter(t => t !== "GU" && t !== "UG")[0];

            return other === "GC" || other === "CG" ? -1.4 : other ? -0.6 : -0.5;
        }

        return -1.0;
    }

    const loopInit = (table, n) => (table[n] !== undefined ? table[n] : table[table.length - 1] + 1.75 * RT * Math.log(n / (table.length - 1)));
    const HAIRPIN = [Infinity, Infinity, Infinity, 5.4, 5.6, 5.7, 5.4, 6.0, 5.5, 6.4];
    const BULGE = [0, 3.8, 2.8, 3.2, 3.6, 4.0, 4.4, 4.59, 4.7, 4.8, 4.9];
    const INTERIOR = [0, 0, 0.5, 1.6, 1.1, 2.0, 2.0, 2.2, 2.3, 2.4, 2.5];
    const MULTI = {a: 3.4, b: 0, c: 0.4};
    const MAX_FOLD = 600;
    const MAX_LOOP = 30;

    function hairpinEnergy(seq, i, j) {
        const n = j - i - 1;

        if (n < 3) return Infinity;

        let e = loopInit(HAIRPIN, n);

        if (n > 3) e -= 0.8; // terminal mismatch bonus

        const t = pairType(seq[i], seq[j]);

        if (t !== "GC" && t !== "CG") e += 0.5;

        return e;
    }

    function interiorEnergy(seq, i, j, p, q) {
        const n1 = p - i - 1;
        const n2 = j - q - 1;

        if (n1 === 0 && n2 === 0) return stackEnergy(seq[i], seq[j], seq[p], seq[q]);

        const terminal = pt => (pt === "GC" || pt === "CG" ? 0 : 0.5);
        let e;

        if (n1 === 0 || n2 === 0) {
            const n = n1 + n2;

            e = loopInit(BULGE, n);

            if (n === 1) e += stackEnergy(seq[i], seq[j], seq[p], seq[q]) + 0; // single bulge keeps the stack
            else e += terminal(pairType(seq[i], seq[j])) + terminal(pairType(seq[p], seq[q]));
        } else {
            e = loopInit(INTERIOR, n1 + n2) + Math.min(3.0, 0.6 * Math.abs(n1 - n2))
                + terminal(pairType(seq[i], seq[j])) + terminal(pairType(seq[p], seq[q]));

            if (n1 === 1 && n2 === 1) e = 0.5 + terminal(pairType(seq[i], seq[j])) * 0.5 + terminal(pairType(seq[p], seq[q])) * 0.5;
        }

        return e;
    }

    // Minimum free energy structure of a short RNA with a simplified nearest-neighbour model (not ViennaRNA).
    function foldRna(text) {
        const seq = toRna(text).replace(/[^ACGU]/g, "N");
        const n = seq.length;

        if (n < 5) return {structure: ".".repeat(n), energy: 0, pairs: 0, length: n};
        if (n > MAX_FOLD) throw new Error("Prediction is limited to " + MAX_FOLD + " nt in the browser; select a shorter region.");

        const INF = 1e9;
        const V = Array.from({length: n}, () => new Float64Array(n).fill(INF));
        const WM = Array.from({length: n + 1}, () => new Float64Array(n + 1).fill(INF));

        for (let span = 4; span < n; span += 1) {
            for (let i = 0; i + span < n; i += 1) {
                const j = i + span;

                if (pairType(seq[i], seq[j])) {
                    let best = hairpinEnergy(seq, i, j);

                    for (let p = i + 1; p < j - 4; p += 1) {
                        const n1 = p - i - 1;

                        if (n1 > MAX_LOOP) break;

                        for (let q = j - 1; q > p + 3; q -= 1) {
                            const n2 = j - q - 1;

                            if (n1 + n2 > MAX_LOOP) break;

                            if (V[p][q] < INF && pairType(seq[p], seq[q])) {
                                const e = V[p][q] + interiorEnergy(seq, i, j, p, q);

                                if (e < best) best = e;
                            }
                        }
                    }

                    for (let k = i + 5; k < j - 5; k += 1) {
                        const e = WM[i + 1][k] + WM[k + 1][j - 1] + MULTI.a + MULTI.c;

                        if (e < best) best = e;
                    }

                    V[i][j] = best;
                }
            }

            for (let i = 0; i + span < n; i += 1) {
                const j = i + span;
                let best = Math.min(WM[i + 1][j] + MULTI.b, WM[i][j - 1] + MULTI.b, V[i][j] + MULTI.c);

                for (let k = i + 1; k < j; k += 1) {
                    const e = WM[i][k] + WM[k + 1][j];

                    if (e < best) best = e;
                }

                WM[i][j] = best;
            }
        }

        // Exterior loop.
        const W = new Float64Array(n + 1).fill(0);
        const from = new Int32Array(n + 1).fill(-1);

        for (let j = 1; j <= n; j += 1) {
            W[j] = W[j - 1];
            from[j] = -1;

            for (let i = 0; i < j - 4; i += 1) {
                if (V[i][j - 1] < INF) {
                    const e = W[i] + V[i][j - 1];

                    if (e < W[j]) {
                        W[j] = e;
                        from[j] = i;
                    }
                }
            }
        }

        const pairs = [];

        function traceV(i, j) {
            pairs.push([i, j]);

            const target = V[i][j];

            if (Math.abs(target - hairpinEnergy(seq, i, j)) < 1e-6) return;

            for (let p = i + 1; p < j - 4; p += 1) {
                if (p - i - 1 > MAX_LOOP) break;

                for (let q = j - 1; q > p + 3; q -= 1) {
                    if (p - i - 1 + j - q - 1 > MAX_LOOP) break;

                    if (V[p][q] < INF && pairType(seq[p], seq[q]) && Math.abs(V[p][q] + interiorEnergy(seq, i, j, p, q) - target) < 1e-6) {
                        traceV(p, q);

                        return;
                    }
                }
            }

            for (let k = i + 5; k < j - 5; k += 1) {
                if (Math.abs(WM[i + 1][k] + WM[k + 1][j - 1] + MULTI.a + MULTI.c - target) < 1e-6) {
                    traceWM(i + 1, k);
                    traceWM(k + 1, j - 1);

                    return;
                }
            }
        }

        function traceWM(i, j) {
            if (j - i < 4 || WM[i][j] >= INF) return;

            const target = WM[i][j];

            if (Math.abs(target - (WM[i + 1][j] + MULTI.b)) < 1e-6) return traceWM(i + 1, j);
            if (Math.abs(target - (WM[i][j - 1] + MULTI.b)) < 1e-6) return traceWM(i, j - 1);
            if (V[i][j] < INF && Math.abs(target - (V[i][j] + MULTI.c)) < 1e-6) return traceV(i, j);

            for (let k = i + 1; k < j; k += 1) {
                if (Math.abs(target - (WM[i][k] + WM[k + 1][j])) < 1e-6) {
                    traceWM(i, k);

                    return traceWM(k + 1, j);
                }
            }

            return undefined;
        }

        let j = n;

        while (j > 0) {
            if (from[j] === -1) {
                j -= 1;
            } else {
                const i = from[j];

                traceV(i, j - 1);
                j = i;
            }
        }

        const chars = new Array(n).fill(".");

        pairs.forEach(([a, b]) => {
            chars[a] = "(";
            chars[b] = ")";
        });

        return {structure: chars.join(""), energy: W[n], pairs: pairs.length, length: n};
    }

    // Validates a dot-bracket string against a sequence; returns the base pairs (0-based) or an error.
    function parseDotBracket(structure, text) {
        const seq = text === undefined ? null : toRna(text);
        const s = String(structure || "").replace(/\s+/g, "");
        const stack = [];
        const pairs = [];

        if (seq !== null && s.length !== seq.length) return {error: "The structure has " + s.length + " characters but the sequence has " + seq.length + " nt."};

        for (let i = 0; i < s.length; i += 1) {
            if (s[i] === "(") stack.push(i);
            else if (s[i] === ")") {
                if (!stack.length) return {error: "Unbalanced ')' at position " + (i + 1) + "."};

                pairs.push([stack.pop(), i]);
            } else if (s[i] !== ".") return {error: "Only '.', '(' and ')' are accepted (found '" + s[i] + "' at " + (i + 1) + ")."};
        }

        if (stack.length) return {error: "Unbalanced '(' at position " + (stack[0] + 1) + "."};

        return {pairs: pairs.sort((a, b) => a[0] - b[0])};
    }

    return {
        cleanLetters, toRna, toDna, reverseComplement, rnaReport, proteinReport, hydropathy, chargeAt,
        translate, findOrfs, foldRna, parseDotBracket, pairType, MAX_FOLD, AMINO,
    };
}));
