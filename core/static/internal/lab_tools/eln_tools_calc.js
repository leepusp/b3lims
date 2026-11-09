/*
 * Bench calculators (pure functions, no DOM): dilution, solution/molarity,
 * buffer or stock recipes, master mix and colony counts.
 * Used by the ELN Tools panel and covered by tests/js/test_eln_tools_calc.cjs.
 */
(function (root, factory) {
    "use strict";

    if (typeof module === "object" && module.exports) module.exports = factory();
    else root.BiobankElnCalc = factory();
})(typeof self !== "undefined" ? self : this, function () {
    "use strict";

    const num = (v) => {
        if (v === "" || v === null || v === undefined) return null;

        const n = Number(String(v).replace(",", "."));

        return Number.isFinite(n) ? n : null;
    };

    /* C1·V1 = C2·V2: exactly one of the four may be empty. */
    function dilution(c1, v1, c2, v2) {
        const vals = {c1: num(c1), v1: num(v1), c2: num(c2), v2: num(v2)};
        const empty = Object.keys(vals).filter((k) => vals[k] === null);

        if (empty.length !== 1) return {error: "Leave exactly one field empty."};
        if (Object.values(vals).some((v) => v !== null && v < 0)) return {error: "Values must be positive."};

        const [k] = empty;
        const {c1: a, v1: b, c2: c, v2: d} = vals;
        let r;

        if (k === "c1") r = (c * d) / b;
        else if (k === "v1") r = (c * d) / a;
        else if (k === "c2") r = (a * b) / d;
        else r = (a * b) / c;

        if (!Number.isFinite(r)) return {error: "Cannot divide by zero."};

        vals[k] = r;

        const out = {solved: k, value: r, c1: vals.c1, v1: vals.v1, c2: vals.c2, v2: vals.v2};

        out.diluent = out.v2 - out.v1;
        out.warning = out.c2 > out.c1 ? "Final concentration is higher than the stock." : "";

        return out;
    }

    /* mass (mg) = C (mM) · V (mL) · MW (g/mol) / 1000. One of conc, volume, mass may be empty. */
    function solution(mw, concMM, volMl, massMg) {
        const m = num(mw);
        const vals = {conc: num(concMM), vol: num(volMl), mass: num(massMg)};
        const empty = Object.keys(vals).filter((k) => vals[k] === null);

        if (!m || m <= 0) return {error: "Enter the molecular weight."};
        if (empty.length !== 1) return {error: "Leave exactly one of concentration, volume or mass empty."};

        const k = empty[0];

        if (k === "mass") vals.mass = (vals.conc * vals.vol * m) / 1000;
        else if (k === "conc") vals.conc = (vals.mass * 1000) / (m * vals.vol);
        else vals.vol = (vals.mass * 1000) / (m * vals.conc);

        if (!Number.isFinite(vals.mass + vals.conc + vals.vol)) return {error: "Cannot divide by zero."};

        return {solved: k, mw: m, conc: vals.conc, vol: vals.vol, mass: vals.mass};
    }

    /*
     * Recipe from stocks: each component has a stock and a final concentration
     * (same unit; "Nx" stocks use stock=N, final=1). Water fills to the final volume.
     */
    function recipe(finalVolume, components) {
        const vf = num(finalVolume);

        if (!vf || vf <= 0) return {error: "Enter the final volume."};

        const rows = [];
        let used = 0;

        for (const c of components) {
            const stock = num(c.stock);
            const final = num(c.final);

            if (!c.name && stock === null && final === null) continue;
            if (!stock || stock <= 0 || final === null || final < 0) {
                return {error: `Check stock and final values for "${c.name || "component"}".`};
            }
            if (final > stock) return {error: `"${c.name || "component"}": final is higher than the stock.`};

            const vol = (final * vf) / stock;

            used += vol;
            rows.push({name: c.name || "", stock, final, volume: vol});
        }

        if (used > vf + 1e-9) return {error: "The components add up to more than the final volume."};

        return {finalVolume: vf, rows, water: vf - used};
    }

    /* Master mix: per-reaction volumes scaled to n reactions plus overage (%). */
    function masterMix(reactions, overagePct, components) {
        const n = num(reactions);
        const over = num(overagePct) || 0;

        if (!n || n <= 0) return {error: "Enter the number of reactions."};

        const factor = n * (1 + over / 100);
        const rows = components
            .filter((c) => c.name || num(c.perReaction) !== null)
            .map((c) => {
                const per = num(c.perReaction) || 0;

                return {name: c.name || "", perReaction: per, total: per * factor};
            });

        return {
            reactions: n,
            overage: over,
            factor,
            rows,
            perReactionTotal: rows.reduce((a, r) => a + r.perReaction, 0),
            total: rows.reduce((a, r) => a + r.total, 0),
        };
    }

    /* CFU/mL = colonies / (plated mL · dilution factor); dilution as exponent (e.g. 6 for 10^-6). */
    function cfu(colonies, plateMl, dilutionExp) {
        const c = num(colonies);
        const v = num(plateMl);
        const e = num(dilutionExp);

        if (c === null || c < 0 || !v || v <= 0 || e === null) return {error: "Enter colonies, plated volume and dilution."};

        const perMl = c / (v * Math.pow(10, -e));
        const note = c < 30 ? "Fewer than 30 colonies: statistically weak." : (c > 300 ? "More than 300 colonies: too many to count reliably." : "");

        return {perMl, note};
    }

    function fmt(n, digits) {
        if (!Number.isFinite(n)) return "";
        if (n !== 0 && (Math.abs(n) >= 1e6 || Math.abs(n) < 1e-3)) return n.toExponential(digits === undefined ? 3 : digits);

        return String(Number(n.toPrecision(digits === undefined ? 4 : digits + 1)));
    }

    return {dilution, solution, recipe, masterMix, cfu, fmt, num};
});
