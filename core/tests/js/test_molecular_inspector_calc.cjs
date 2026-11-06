"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

const calc = require(path.resolve(
  __dirname,
  "../../static/internal/lab_tools/molecular_inspector_calc.js"
));

// Basic sequence operations.
assert.equal(calc.reverseComplement("ATGC"), "GCAT");
assert.equal(calc.reverseComplement("atgn"), "NCAT");
assert.equal(calc.reverseComplement("AUGC", true), "GCAU");
assert.equal(calc.gcPercent("ATGC"), 50);
assert.equal(calc.gcPercent(""), null);
assert.equal(calc.translate("ATGGCTAGC"), "MAS");
assert.equal(calc.translate("AATGGCTAGC", 1), "MAS");
assert.equal(calc.translate("AUGGCU"), "MA");

// Coordinates are 1-based inclusive; start > end wraps the origin.
assert.equal(calc.slice("ACGTACGT", 2, 4), "CGT");
assert.equal(calc.slice("ACGTACGT", 7, 2), "GTAC");
assert.equal(calc.slice("ACGT", 0, 2), "");
assert.equal(calc.slice("ACGT", 1, 9), "");

// Longest forward ORF.
const orf = calc.longestOrf("CC" + "ATG" + "GCT".repeat(40) + "TAA" + "GG", 30);
assert.deepEqual(
  {start: orf.start, end: orf.end, aa: orf.aminoAcids, frame: orf.frame},
  {start: 3, end: 128, aa: 41, frame: 3}
);
assert.equal(calc.longestOrf("ATGGCTTAA", 30), null);

const two = calc.findOrfs(
  "ATG" + "GCT".repeat(35) + "TAA" + "CC" + "ATG" + "GCT".repeat(60) + "TGA", 30
);
assert.deepEqual(two.map(o => o.aminoAcids), [61, 36]);

// Melting temperature: ordered by GC and refused outside its range.
const at = calc.meltingTemperature("ATATATATATATATATATAT");
const gc = calc.meltingTemperature("GCGCGCGCGCGCGCGCGCGC");
const mixed = calc.meltingTemperature("ATGGCTAGCAAAGGAGAAGAAC");

assert.ok(at < mixed && mixed < gc, `${at} < ${mixed} < ${gc}`);
assert.ok(mixed > 50 && mixed < 65, String(mixed));
assert.equal(calc.meltingTemperature("ATGC"), null);
assert.equal(calc.meltingTemperature("ATGCNNNNATGC"), null);
assert.ok(
  calc.meltingTemperature("ATGGCTAGCAAAGGAGAAGAAC", {sodiumMolar: 0.5}) > mixed
);

// Primer checks.
assert.deepEqual(calc.primerChecks("ATGGCTAGCAAAGGAGAAGAAC"), {
  clampGc: 2, longestRun: 3, endsWithGc: true,
});

// Protein properties (average masses, ExPASy-style).
const props = calc.proteinProperties("ACDEFGHIKLMNPQRSTVWY");

assert.ok(Math.abs(props.massDa - 2395.7) < 0.5, String(props.massDa));
assert.equal(props.residues, 20);
assert.equal(props.extinction280, 5500 + 1490);
assert.ok(props.isoelectricPoint > 6 && props.isoelectricPoint < 8.5);
assert.equal(calc.proteinProperties("XXXX"), null);

const acidic = calc.proteinProperties("DDDDEEEE");
const basic = calc.proteinProperties("KKKKRRRR");

assert.ok(acidic.isoelectricPoint < 4.5);
assert.ok(basic.isoelectricPoint > 10);
assert.ok(acidic.chargeAt74 < 0 && basic.chargeAt74 > 0);

console.log("molecular inspector calc: OK");
