/*
 * RNA secondary-structure layout (pure functions, no DOM).
 *
 * layout(db, opts) turns a dot-bracket string into x/y coordinates with the
 * classic "loop" drawing: the exterior loop is a baseline, every helix is a
 * straight ladder, every other loop is a circle whose points are its unpaired
 * bases and the base pairs of the helices that leave it.
 *
 * With opts {loop, pair, rise} = (6, 10.5, 2.8) the same algorithm yields an
 * idealised A-form-like geometry, and build3d() twists each helix around its
 * axis to give an illustrative 3D model (not a prediction).
 */
(function (root, factory) {
    "use strict";

    if (typeof module === "object" && module.exports) module.exports = factory();
    else root.BiobankRnaLayout = factory();
})(typeof self !== "undefined" ? self : this, function () {
    "use strict";

    const OPEN = "([{<";
    const CLOSE = ")]}>";

    function pairsOf(db) {
        const stacks = {"(": [], "[": [], "{": [], "<": []};
        const out = [];

        for (let i = 0; i < db.length; i += 1) {
            const c = db[i];

            if (OPEN.indexOf(c) >= 0) stacks[c].push(i);
            else {
                const k = CLOSE.indexOf(c);

                if (k >= 0 && stacks[OPEN[k]].length) out.push([stacks[OPEN[k]].pop(), i, k > 0]);
            }
        }

        return out.sort((a, b) => a[0] - b[0]);
    }

    function partnersOf(db, nestedOnly) {
        const partner = new Array(db.length).fill(-1);

        pairsOf(db).forEach(([i, j, knot]) => {
            if (nestedOnly && knot) return;

            partner[i] = j;
            partner[j] = i;
        });

        return partner;
    }

    function layout(db, opts) {
        const o = Object.assign({loop: 1, pair: 1, rise: 1, closed: false}, opts || {});

        if (o.closed && db.length) {
            // Close the exterior loop into a circle by enclosing the whole
            // molecule in a virtual pair, then drop the virtual positions.
            const m = db.length;
            const r = layout("(" + db + ")", Object.assign({}, o, {closed: false}));

            if (r.partner[0] === m + 1) {
                return {
                    pos: r.pos.slice(1, m + 1),
                    partner: r.partner.slice(1, m + 1).map(x => (x < 1 || x > m ? -1 : x - 1)),
                    helices: r.helices
                        .map(h => ({u: h.u, rows: h.rows.filter(([i, j]) => i > 0 && j < m + 1).map(([i, j]) => [i - 1, j - 1])}))
                        .filter(h => h.rows.length),
                };
            }
        }

        const n = db.length;
        const partner = partnersOf(db, true);
        const pos = new Array(n);
        const helices = [];

        function helix(i, j, A, B, u) {
            const rows = [];

            rows.push([i, j]);
            pos[i] = A;
            pos[j] = B;

            while (i + 1 < j - 1 && partner[i + 1] === j - 1) {
                A = [A[0] + u[0] * o.rise, A[1] + u[1] * o.rise];
                B = [B[0] + u[0] * o.rise, B[1] + u[1] * o.rise];
                i += 1;
                j -= 1;
                pos[i] = A;
                pos[j] = B;
                rows.push([i, j]);
            }

            helices.push({rows, u});

            const items = [];
            let t = i + 1;

            while (t < j) {
                if (partner[t] > t && partner[t] < j) {
                    items.push({k: t, l: partner[t]});
                    t = partner[t] + 1;
                } else {
                    items.push({u: t});
                    t += 1;
                }
            }

            if (!items.length) return;

            // Slots around the loop: i, (unpaired | k,l)..., j.
            const slots = [{idx: i}];

            items.forEach(it => {
                if (it.u !== undefined) slots.push({idx: it.u});
                else {
                    slots.push({idx: it.k, helix: it});
                    slots.push({idx: it.l, partnerOf: it});
                }
            });
            slots.push({idx: j});

            const chords = slots.map((s, idx) => {
                const next = slots[(idx + 1) % slots.length];

                return s.helix && next.partnerOf === s.helix ? o.pair : (
                    idx === slots.length - 1 ? o.pair : o.loop
                );
            });
            const perimeter = chords.reduce((a, b) => a + b, 0);
            const W = Math.hypot(B[0] - A[0], B[1] - A[1]);
            let R = perimeter / (2 * Math.PI);

            R = Math.max(R, (W / 2) * 1.02);

            const h = Math.sqrt(Math.max(R * R - (W / 2) * (W / 2), 0));
            const M = [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2];
            const C = [M[0] + u[0] * h, M[1] + u[1] * h];
            const thA = Math.atan2(A[1] - C[1], A[0] - C[0]);
            const thB = Math.atan2(B[1] - C[1], B[0] - C[0]);
            let d = thB - thA;

            while (d > Math.PI) d -= 2 * Math.PI;
            while (d <= -Math.PI) d += 2 * Math.PI;

            const dir = d > 0 ? -1 : 1;
            let cum = 0;

            slots.forEach((s, idx) => {
                if (idx > 0 && idx < slots.length - 1) {
                    const a = thA + dir * 2 * Math.PI * (cum / perimeter);

                    pos[s.idx] = [C[0] + R * Math.cos(a), C[1] + R * Math.sin(a)];
                }

                cum += chords[idx];
            });

            slots.forEach(s => {
                if (!s.helix) return;

                const a = pos[s.helix.k];
                const b = pos[s.helix.l];
                const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
                let v = [m[0] - C[0], m[1] - C[1]];
                const len = Math.hypot(v[0], v[1]) || 1;

                v = [v[0] / len, v[1] / len];
                helix(s.helix.k, s.helix.l, a, b, v);
            });
        }

        let x = 0;
        let k = 0;

        while (k < n) {
            if (partner[k] > k) {
                const l = partner[k];

                helix(k, l, [x, 0], [x + o.pair, 0], [0, -1]);
                x += o.pair + o.loop;
                k = l + 1;
            } else {
                pos[k] = [x, 0];
                x += o.loop;
                k += 1;
            }
        }

        return {pos, partner, helices};
    }

    function bounds(pos) {
        let x0 = Infinity;
        let y0 = Infinity;
        let x1 = -Infinity;
        let y1 = -Infinity;

        pos.forEach(p => {
            if (!p) return;

            x0 = Math.min(x0, p[0]);
            y0 = Math.min(y0, p[1]);
            x1 = Math.max(x1, p[0]);
            y1 = Math.max(y1, p[1]);
        });

        return {x0, y0, x1, y1};
    }

    /* Illustrative 3D: helices twisted around their axis, loops flat. */
    function build3d(db) {
        const base = layout(db, {loop: 6, pair: 10.5, rise: 2.8, closed: true});
        const pts = base.pos.map(p => [p[0], p[1], 0]);
        const TWIST = (32.7 * Math.PI) / 180;

        base.helices.forEach(hx => {
            hx.rows.forEach(([i, j], r) => {
                const A = base.pos[i];
                const B = base.pos[j];
                const M = [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2];
                const h = [(B[0] - A[0]) / 2, (B[1] - A[1]) / 2];
                const half = Math.hypot(h[0], h[1]);
                const th = r * TWIST;
                const c = Math.cos(th);
                const s = Math.sin(th);

                pts[i] = [M[0] - h[0] * c, M[1] - h[1] * c, half * s];
                pts[j] = [M[0] + h[0] * c, M[1] + h[1] * c, -half * s];
            });
        });

        return {pts, partner: base.partner};
    }

    /* Would adding pair (a, b) cross an existing nested pair? */
    function crosses(db, a, b) {
        const lo = Math.min(a, b);
        const hi = Math.max(a, b);

        return pairsOf(db).some(([p, q]) => (p < lo && lo < q && q < hi) || (lo < p && p < hi && hi < q));
    }

    function setPair(db, a, b) {
        const arr = db.split("");

        arr[Math.min(a, b)] = "(";
        arr[Math.max(a, b)] = ")";

        return arr.join("");
    }

    function removePair(db, i) {
        const partner = partnersOf(db, false);
        const arr = db.split("");

        if (partner[i] >= 0) {
            arr[i] = ".";
            arr[partner[i]] = ".";
        }

        return arr.join("");
    }

    return {pairsOf, partnersOf, layout, bounds, build3d, crosses, setPair, removePair};
});
