/*
 * Restriction digest calculations for the Molecular Registry workbench.
 *
 * Pure functions, no DOM. Loaded by the page and by the Node tests
 * (core/tests/js/test_molecular_digest_calc.cjs).
 *
 * Palindromic and type IIS enzymes. Sites are scanned on both strands, so a
 * non-palindromic site is found whichever way it points. `cut` is the number
 * of bases from the start of the site to the cut on the strand that carries
 * it (G^AATTC has cut 1).
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

    /*
     * Offsets are bases from the start of the recognition site (on the strand
     * that carries it) to the cut on that strand (`cut`) and to the cut on the
     * opposite strand (`bottom`, same coordinates). For palindromic enzymes
     * `bottom` is site.length - cut. Type IIS enzymes cut outside the site
     * (cut or bottom beyond site.length) and are not palindromic, so both
     * strands are scanned.
     */
    const ENZYMES = [
        ["AatII", "GACGTC", 5], ["AccI", "GTMKAC", 2], ["AclI", "AACGTT", 2],
        ["AfeI", "AGCGCT", 3], ["AflII", "CTTAAG", 1], ["AgeI", "ACCGGT", 1],
        ["AhdI", "GACNNNNNGTC", 6], ["AluI", "AGCT", 2], ["ApaI", "GGGCCC", 5],
        ["ApaLI", "GTGCAC", 1], ["AscI", "GGCGCGCC", 2], ["AseI", "ATTAAT", 2],
        ["AsiSI", "GCGATCGC", 5], ["AvaI", "CYCGRG", 1], ["AvrII", "CCTAGG", 1],
        ["BamHI", "GGATCC", 1], ["BclI", "TGATCA", 1], ["BglII", "AGATCT", 1],
        ["BmtI", "GCTAGC", 5], ["BspEI", "TCCGGA", 1], ["BspHI", "TCATGA", 1],
        ["BsrGI", "TGTACA", 1], ["BssHII", "GCGCGC", 1], ["BstAPI", "GCANNNNNTGC", 7],
        ["BstBI", "TTCGAA", 2], ["BstEII", "GGTNACC", 1], ["BstXI", "CCANNNNNNTGG", 8],
        ["BstZ17I", "GTATAC", 3], ["BsiWI", "CGTACG", 1], ["Bsu36I", "CCTNAGG", 2],
        ["ClaI", "ATCGAT", 2], ["DpnII", "GATC", 0], ["DraI", "TTTAAA", 3],
        ["Eco53kI", "GAGCTC", 3], ["EcoNI", "CCTNNNNNAGG", 5], ["EcoRI", "GAATTC", 1],
        ["EcoRV", "GATATC", 3], ["FseI", "GGCCGGCC", 6], ["HaeIII", "GGCC", 2],
        ["HincII", "GTYRAC", 3], ["HindIII", "AAGCTT", 1], ["HpaI", "GTTAAC", 3],
        ["HpaII", "CCGG", 1], ["KasI", "GGCGCC", 1], ["KpnI", "GGTACC", 5],
        ["MfeI", "CAATTG", 1], ["MluI", "ACGCGT", 1], ["MscI", "TGGCCA", 3],
        ["MseI", "TTAA", 1], ["NaeI", "GCCGGC", 3], ["NarI", "GGCGCC", 2],
        ["NcoI", "CCATGG", 1], ["NdeI", "CATATG", 2], ["NheI", "GCTAGC", 1],
        ["NotI", "GCGGCCGC", 2], ["NruI", "TCGCGA", 3], ["NsiI", "ATGCAT", 5],
        ["PacI", "TTAATTAA", 5], ["PciI", "ACATGT", 1], ["PmeI", "GTTTAAAC", 4],
        ["PmlI", "CACGTG", 3], ["PspOMI", "GGGCCC", 1], ["PstI", "CTGCAG", 5],
        ["PvuI", "CGATCG", 4], ["PvuII", "CAGCTG", 3], ["RsaI", "GTAC", 2],
        ["SacI", "GAGCTC", 5], ["SacII", "CCGCGG", 4], ["SalI", "GTCGAC", 1],
        ["ScaI", "AGTACT", 3], ["SfiI", "GGCCNNNNNGGCC", 8], ["SfoI", "GGCGCC", 3],
        ["SgrAI", "CRCCGGYG", 2], ["SmaI", "CCCGGG", 3], ["SnaBI", "TACGTA", 3],
        ["SpeI", "ACTAGT", 1], ["SphI", "GCATGC", 5], ["SspI", "AATATT", 3],
        ["StuI", "AGGCCT", 3], ["SwaI", "ATTTAAAT", 4], ["TaqI", "TCGA", 1],
        ["XbaI", "TCTAGA", 1], ["XhoI", "CTCGAG", 1], ["XmaI", "CCCGGG", 1],
        ["XmnI", "GAANNNNTTC", 5],
    ].map(([name, site, cut]) => ({name, site, cut, bottom: site.length - cut}));

    /* Type IIS: [name, site, cut on the site strand, cut on the other strand]. */
    const TYPE_IIS = [
        ["AarI", "CACCTGC", 11, 15], ["AcuI", "CTGAAG", 22, 20],
        ["BbsI", "GAAGAC", 8, 12], ["BpmI", "CTGGAG", 22, 20],
        ["BsaI", "GGTCTC", 7, 11], ["BseRI", "GAGGAG", 16, 14],
        ["BsgI", "GTGCAG", 22, 20], ["BsmI", "GAATGC", 7, 5],
        ["BsmBI", "CGTCTC", 7, 11], ["BsmFI", "GGGAC", 15, 19],
        ["BtsI", "GCAGTG", 8, 6], ["EarI", "CTCTTC", 7, 10],
        ["EciI", "GGCGGA", 17, 15], ["FokI", "GGATG", 14, 18],
        ["HgaI", "GACGC", 10, 15], ["MlyI", "GAGTC", 10, 10],
        ["MmeI", "TCCRAC", 26, 24], ["SapI", "GCTCTTC", 8, 11],
    ].map(([name, site, cut, bottom]) => ({name, site, cut, bottom, typeIIS: true}));

    const CATALOG = ENZYMES.concat(TYPE_IIS)
        .sort((a, b) => a.name.localeCompare(b.name));

    const IUPAC = {
        A: "A", C: "C", G: "G", T: "T", N: "[ACGT]",
        R: "[AG]", Y: "[CT]", K: "[GT]", M: "[AC]", S: "[CG]", W: "[AT]",
        B: "[CGT]", D: "[AGT]", H: "[ACT]", V: "[ACG]",
    };
    const COMPLEMENT = {
        A: "T", C: "G", G: "C", T: "A", N: "N", R: "Y", Y: "R", K: "M",
        M: "K", S: "S", W: "W", B: "V", V: "B", D: "H", H: "D",
    };

    function clean(sequence) {
        return String(sequence || "").toUpperCase().replace(/[^A-Z]/g, "")
            .replace(/U/g, "T");
    }

    function pattern(site) {
        return site.split("").map(letter => IUPAC[letter] || letter).join("");
    }

    function reverseComplementSite(site) {
        return site.split("").reverse().map(letter => COMPLEMENT[letter] || letter).join("");
    }

    function byName(name) {
        return CATALOG.find(item => item.name === name) || null;
    }

    function isPalindromic(item) {
        return reverseComplementSite(item.site) === item.site;
    }

    /**
     * Every cut of one enzyme, on both strands for non-palindromic sites.
     * position: bases preceding the cut on the top strand; bottom: the same
     * for the bottom strand; strand: orientation of the site; overhang > 0 is
     * a 5' overhang, < 0 a 3' overhang, 0 is blunt. A circular cut at the very
     * end is reported as 0.
     */
    function cutSites(sequence, enzyme, circular) {
        const seq = clean(sequence);
        const item = typeof enzyme === "string" ? byName(enzyme) : enzyme;

        if (!item || !seq) return [];

        const width = item.site.length;
        const length = seq.length;
        const text = circular ? seq + seq.slice(0, width - 1) : seq;
        const bottomOffset = item.bottom === undefined ? width - item.cut : item.bottom;
        const sites = [];
        const orientations = [{strand: "+", site: item.site}];

        if (!isPalindromic(item)) {
            orientations.push({strand: "-", site: reverseComplementSite(item.site)});
        }

        orientations.forEach(orientation => {
            const expression = new RegExp("(?=(" + pattern(orientation.site) + "))", "g");
            let match;

            while ((match = expression.exec(text)) !== null) {
                const start = match.index;

                expression.lastIndex = match.index + 1;

                if (start >= length) continue;

                let top;
                let bottom;

                if (orientation.strand === "+") {
                    top = start + item.cut;
                    bottom = start + bottomOffset;
                } else {
                    top = start + width - bottomOffset;
                    bottom = start + width - item.cut;
                }

                if (circular) {
                    top = ((top % length) + length) % length;
                    bottom = ((bottom % length) + length) % length;
                } else if (top <= 0 || top >= length || bottom <= 0 || bottom >= length) {
                    continue;
                }

                sites.push({
                    enzyme: item.name,
                    position: top,
                    bottom,
                    strand: orientation.strand,
                    siteStart: start,
                    siteEnd: start + width,
                    overhang: bottomOffset - item.cut,
                });
            }
        });

        return sites.sort((a, b) => a.position - b.position);
    }

    /**
     * Cut positions of one enzyme: each value is the count of bases that
     * precede the cut on the top strand (1..length-1, or 0 for a cut at the
     * very end of a circular sequence), sorted ascending.
     */
    function cutPositions(sequence, enzyme, circular) {
        return Array.from(new Set(
            cutSites(sequence, enzyme, circular).map(site => site.position)
        )).sort((a, b) => a - b);
    }

    /** "5' overhang 4", "3' overhang 2" or "blunt". */
    function describeEnds(item) {
        const bottom = item.bottom === undefined ? item.site.length - item.cut : item.bottom;
        const diff = bottom - item.cut;

        return diff === 0 ? "blunt" : (diff > 0 ? "5' overhang " + diff : "3' overhang " + (-diff));
    }

    /** Every catalogued enzyme with how often it cuts, fewest cuts first. */
    function catalogCounts(sequence, circular) {
        return CATALOG.map(item => ({
            name: item.name,
            site: item.site,
            cut: item.cut,
            bottom: item.bottom === undefined ? item.site.length - item.cut : item.bottom,
            typeIIS: Boolean(item.typeIIS),
            ends: describeEnds(item),
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
        cutSites,
        describeEnds,
        isPalindromic,
        catalogCounts,
        digest,
        gelPosition,
    };
}));
