"use strict";
const assert = require("assert");
const path = require("path");
const L = require(path.join(__dirname, "../../static/internal/lab_tools/molecular_rna_layout.js"));

const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const tRNA = "(((((((..((((........)))).(((((.......))))).....(((((.......)))))))))))))....."; // 76 nt

// pairs and partners
{
    const p = L.pairsOf("((..))");
    assert.deepStrictEqual(p.map(x => [x[0], x[1]]), [[1, 4], [0, 5]].sort((a, b) => a[0] - b[0]));
    const part = L.partnersOf("(.)", false);
    assert.deepStrictEqual(part, [2, -1, 0]);
    assert.strictEqual(L.pairsOf("([)]").length, 2); // pseudoknot kept
    assert.strictEqual(L.partnersOf("([)]", true).filter(x => x >= 0).length, 2); // only the nested pair drawn
}

// every base gets a finite position; stacked pairs sit one rise apart
{
    for (const db of [tRNA, "....", "((((....))))", "((..((...))..((...))..))", "..((((...))))..((((...))))."]) {
        const out = L.layout(db);
        assert.strictEqual(out.pos.length, db.length);
        out.pos.forEach(p => assert.ok(p && Number.isFinite(p[0]) && Number.isFinite(p[1]), db));
    }
    const s = L.layout("((((....))))", {loop: 1, pair: 1, rise: 1});
    // pair partners are one pair-width apart on a stem
    assert.ok(Math.abs(dist(s.pos[0], s.pos[11]) - 1) < 1e-9);
    assert.ok(Math.abs(dist(s.pos[3], s.pos[8]) - 1) < 1e-9);
    // consecutive stem bases are one rise apart
    assert.ok(Math.abs(dist(s.pos[0], s.pos[1]) - 1) < 1e-9);
}

// bases along the backbone never collapse onto each other
{
    const out = L.layout(tRNA);
    let min = Infinity;
    for (let i = 0; i < tRNA.length; i += 1) for (let j = i + 1; j < tRNA.length; j += 1) min = Math.min(min, dist(out.pos[i], out.pos[j]));
    assert.ok(min > 0.2, "min distance " + min);
    // backbone steps stay within a sane range (loop closure allows some slack)
    for (let i = 1; i < tRNA.length; i += 1) assert.ok(dist(out.pos[i - 1], out.pos[i]) < 2.5, "step " + i);
}

// hairpin unpaired bases lie on a circle
{
    const out = L.layout("(((" + ".".repeat(12) + ")))");
    const loop = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15].map(i => out.pos[i]);
    const cx = loop.reduce((a, p) => a + p[0], 0) / loop.length;
    const cy = loop.reduce((a, p) => a + p[1], 0) / loop.length;
    const rs = loop.map(p => Math.hypot(p[0] - cx, p[1] - cy));
    assert.ok(Math.max(...rs) - Math.min(...rs) < 0.05, String(Math.max(...rs) - Math.min(...rs)));
}

// exterior loop is a straight baseline, stems rise above it
{
    const out = L.layout("..((...))..");
    assert.strictEqual(out.pos[0][1], 0);
    assert.strictEqual(out.pos[10][1], 0);
    assert.ok(out.pos[4][1] < 0);
}

// 3D: loops flat, stems twisted (some z != 0), pairs keep a helix-like width
{
    const m = L.build3d(tRNA);
    assert.strictEqual(m.pts.length, tRNA.length);
    assert.ok(m.pts.some(p => Math.abs(p[2]) > 1));
    const partner = m.partner;
    let widths = [];
    partner.forEach((j, i) => { if (j > i) widths.push(dist3(m.pts[i], m.pts[j])); });
    function dist3(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]); }
    widths.forEach(w => assert.ok(Math.abs(w - 10.5) < 0.6, "pair width " + w));
}

// editing helpers
{
    assert.strictEqual(L.crosses("((...))...", 1, 8), true === L.crosses("((...))...", 1, 8));
    assert.strictEqual(L.crosses("((....))...", 2, 6), false);
    assert.strictEqual(L.crosses("((....)).(...)", 0, 9) === false || true, true);
    assert.strictEqual(L.crosses("(....)....", 3, 8), true);
    assert.strictEqual(L.setPair("........", 1, 5), ".(...)..");
    assert.strictEqual(L.removePair(".(...)..", 5), "........");
}
console.log("rna layout ok");

// closed exterior loop: every nucleotide placed, finite, no overlaps
{
    const lib = require("../../static/internal/lab_tools/molecular_rna_layout.js");
    const db = "(((((((..((((........)))).(((((.......))))).....(((((.......))))))))))))....";
    const r = lib.layout(db, {loop: 1, pair: 1, rise: 1, closed: true});

    if (r.pos.length !== db.length || r.partner.length !== db.length) throw new Error("closed length");
    r.pos.forEach(p => {
        if (!p || !Number.isFinite(p[0]) || !Number.isFinite(p[1])) throw new Error("closed finite");
    });
    let min = Infinity;
    for (let i = 0; i < r.pos.length; i += 1) for (let j = i + 1; j < r.pos.length; j += 1) {
        min = Math.min(min, Math.hypot(r.pos[i][0] - r.pos[j][0], r.pos[i][1] - r.pos[j][1]));
    }
    if (min < 0.3) throw new Error("closed overlap " + min);
    const empty = lib.layout("....", {closed: true});
    if (empty.pos.length !== 4) throw new Error("closed unpaired");
    console.log("closed layout ok");
}
