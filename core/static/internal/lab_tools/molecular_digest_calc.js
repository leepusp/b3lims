/*
 * Restriction digest calculations for the Molecular Registry workbench.
 *
 * Pure functions, no DOM. Loaded by the page and by the Node tests
 * (core/tests/js/test_molecular_digest_calc.cjs).
 *
 * Only palindromic recognition sites are catalogued, so scanning the top
 * strand finds every site. `cut` is the number of bases from the start of the
 * site to the top-strand cut (G^AATTC has cut 1).
 */
(function (root, factory) {
    "use strict";

    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.BiobankDigestCalc = factory();
    }
}(typeof self !== "undefined" ? self : this, function () {
    "use strict";

    const CATALOG = [
        {name: "AflII", site: "CTTAAG", cut: 1},
        {name: "AgeI", site: "ACCGGT", cut: 1},
        {name: "ApaI", site: "GGGCCC", cut: 5},
        {name: "AvrII", site: "CCTAGG", cut: 1},
        {name: "BamHI", site: "GGATCC", cut: 1},
        {name: "BglII", site: "AGATCT", cut: 1},
        {name: "BspHI", site: "TCATGA", cut: 1},
        {name: "BsrGI", site: "TGTACA", cut: 1},
        {name: "BstAPI", site: "GCANNNNNTGC", cut: 7},
        {name: "ClaI", site: "ATCGAT", cut: 2},
        {name: "DraI", site: "TTTAAA", cut: 3},
        {name: "EcoRI", site: "GAATTC", cut: 1},
        {name: "EcoRV", site: "GATATC", cut: 3},
        {name: "HindIII", site: "AAGCTT", cut: 1},
        {name: "HpaI", site: "GTTAAC", cut: 3},
        {name: "KpnI", site: "GGTACC", cut: 5},
        {name: "MluI", site: "ACGCGT", cut: 1},
        {name: "NaeI", site: "GCCGGC", cut: 3},
        {name: "NcoI", site: "CCATGG", cut: 1},
        {name: "NdeI", site: "CATATG", cut: 2},
        {name: "NheI", site: "GCTAGC", cut: 1},
        {name: "NotI", site: "GCGGCCGC", cut: 2},
        {name: "NsiI", site: "ATGCAT", cut: 5},
        {name: "PstI", site: "CTGCAG", cut: 5},
        {name: "PvuI", site: "CGATCG", cut: 4},
        {name: "PvuII", site: "CAGCTG", cut: 3},
        {name: "SacI", site: "GAGCTC", cut: 5},
        {name: "SacII", site: "CCGCGG", cut: 4},
        {name: "SalI", site: "GTCGAC", cut: 1},
        {name: "ScaI", site: "AGTACT", cut: 3},
        {name: "SmaI", site: "CCCGGG", cut: 3},
        {name: "SpeI", site: "ACTAGT", cut: 1},
        {name: "SphI", site: "GCATGC", cut: 5},
        {name: "SspI", site: "AATATT", cut: 3},
        {name: "StuI", site: "AGGCCT", cut: 3},
        {name: "XbaI", site: "TCTAGA", cut: 1},
        {name: "XhoI", site: "CTCGAG", cut: 1},
        {name: "XmaI", site: "CCCGGG", cut: 1},
    ];

    const IUPAC = {
        A: "A", C: "C", G: "G", T: "T", N: "[ACGT]",
    };

    function clean(sequence) {
        return String(sequence || "").toUpperCase().replace(/[^A-Z]/g, "")
            .replace(/U/g, "T");
    }

    function pattern(site) {
        return site.split("").map(letter => IUPAC[letter] || letter).join("");
    }

    function byName(name) {
        return CATALOG.find(item => item.name === name) || null;
    }

    /**
     * Cut positions of one enzyme: each value is the count of bases that
     * precede the cut on the top strand (1..length-1, or 0 / length for a cut
     * at the very end of a circular sequence), sorted ascending.
     */
    function cutPositions(sequence, enzyme, circular) {
        const seq = clean(sequence);
        const item = typeof enzyme === "string" ? byName(enzyme) : enzyme;

        if (!item || !seq) return [];

        const width = item.site.length;
        const text = circular ? seq + seq.slice(0, width - 1) : seq;
        const expression = new RegExp("(?=(" + pattern(item.site) + "))", "g");
        const cuts = [];
        let match;

        while ((match = expression.exec(text)) !== null) {
            const start = match.index;

            if (start < seq.length) {
                const cut = start + item.cut;

                if (circular) {
                    cuts.push(cut % seq.length);
                } else if (cut > 0 && cut < seq.length) {
                    cuts.push(cut);
                }
            }

            expression.lastIndex = match.index + 1;
        }

        return Array.from(new Set(cuts)).sort((a, b) => a - b);
    }

    /** Every catalogued enzyme with how often it cuts, fewest cuts first. */
    function catalogCounts(sequence, circular) {
        return CATALOG.map(item => ({
            name: item.name,
            site: item.site,
            cut: item.cut,
            cuts: cutPositions(sequence, item, circular),
        })).sort((a, b) => (
            a.cuts.length - b.cuts.length || a.name.localeCompare(b.name)
        ));
    }

    /**
     * Fragments after cutting with the chosen enzymes.
     * Each fragment: {start, end, length}, 1-based inclusive; a circular
     * fragment that crosses the origin has start > end.
     */
    function digest(sequence, enzymes, circular) {
        const length = clean(sequence).length;
        const cuts = Array.from(new Set(
            enzymes.flatMap(name => cutPositions(sequence, name, circular))
        )).sort((a, b) => a - b);

        if (!length) return [];

        if (!cuts.length) {
            return [{start: 1, end: length, length, uncut: true}];
        }

        const fragments = [];

        if (circular) {
            cuts.forEach((cut, index) => {
                const next = cuts[(index + 1) % cuts.length];
                const size = index + 1 < cuts.length
                    ? next - cut
                    : length - cut + cuts[0];

                fragments.push({
                    start: (cut % length) + 1,
                    end: next === 0 ? length : next,
                    length: cuts.length === 1 ? length : size,
                });
            });
        } else {
            const edges = [0].concat(cuts, [length]);

            for (let i = 0; i + 1 < edges.length; i++) {
                fragments.push({
                    start: edges[i] + 1,
                    end: edges[i + 1],
                    length: edges[i + 1] - edges[i],
                });
            }
        }

        return fragments;
    }

    /** Vertical band position (0 = well, 1 = bottom) on a log scale. */
    function gelPosition(size, min, max) {
        const low = Math.log10(min || 100);
        const high = Math.log10(max || 10000);
        const value = Math.log10(Math.max(size, 1));
        const fraction = (high - value) / (high - low);

        return Math.max(0, Math.min(1, fraction));
    }

    const LADDER = [10000, 8000, 6000, 5000, 4000, 3000, 2000, 1500, 1000, 500];

    return {
        CATALOG,
        LADDER,
        byName,
        cutPositions,
        catalogCounts,
        digest,
        gelPosition,
    };
}));
