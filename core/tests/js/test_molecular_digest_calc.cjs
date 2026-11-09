"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

const calc = require(path.resolve(
  __dirname,
  "../../static/internal/lab_tools/molecular_digest_calc.js"
));

// G^AATTC: cut after the first base of the site.
assert.deepEqual(calc.cutPositions("AAAGAATTCAAA", "EcoRI", false), [4]);
assert.deepEqual(calc.cutPositions("AAAAAAAAAAAA", "EcoRI", false), []);

// NdeI CA^TATG, site at 4..9 (1-based) so the cut follows base 5.
assert.deepEqual(calc.cutPositions("GGGCATATGGGG", "NdeI", false), [5]);

// Ambiguity codes: BstAPI GCANNNNNTGC cuts after 7 bases.
assert.deepEqual(calc.cutPositions("AAGCAAAAAATGCAA", "BstAPI", false), [2 + 7]);

// A site spanning the origin of a circular sequence is found; linear misses it.
const wrapped = "ATTCAAAAAAAAAAAAG" + "GA"; // ...GGA|ATTC => GAATTC across origin
const wrapSeq = "ATTC" + "A".repeat(10) + "GA";
assert.equal(calc.cutPositions(wrapSeq, "EcoRI", true).length, 1);
assert.equal(calc.cutPositions(wrapSeq, "EcoRI", false).length, 0);
assert.ok(wrapped.length > 0);

// Linear digest: cuts split into n+1 fragments that add up to the length.
const linear = "A".repeat(20) + "GAATTC" + "A".repeat(30) + "GGATCC" + "A".repeat(10);
const lin = calc.digest(linear, ["EcoRI", "BamHI"], false);
assert.equal(lin.length, 3);
assert.equal(lin.reduce((sum, item) => sum + item.length, 0), linear.length);
assert.deepEqual(lin.map(item => item.start), [1, 22, 58]);

// Circular digest: n cuts give n fragments that add up to the length.
const circ = calc.digest(linear, ["EcoRI", "BamHI"], true);
assert.equal(circ.length, 2);
assert.equal(circ.reduce((sum, item) => sum + item.length, 0), linear.length);

// One cut in a circular molecule opens it: one fragment with the full length.
const single = calc.digest(linear, ["EcoRI"], true);
assert.equal(single.length, 1);
assert.equal(single[0].length, linear.length);

// No cut: the molecule stays whole.
const none = calc.digest(linear, ["SalI"], true);
assert.equal(none.length, 1);
assert.equal(none[0].uncut, true);

// Counts: unique cutters come first.
const counts = calc.catalogCounts(linear, false);
assert.equal(counts[0].cuts.length, 0);
assert.equal(counts.find(item => item.name === "EcoRI").cuts.length, 1);

// Gel positions: bigger fragments run less.
assert.ok(calc.gelPosition(5000) < calc.gelPosition(500));
assert.equal(calc.gelPosition(10000), 0);
assert.equal(calc.gelPosition(1), 1);

// Type IIS: BsaI GGTCTC(1/5) cuts outside its site, on either strand.
const forwardIIS = calc.cutSites("A".repeat(4) + "GGTCTC" + "A".repeat(20), "BsaI", false);
assert.equal(forwardIIS.length, 1);
assert.equal(forwardIIS[0].strand, "+");
assert.equal(forwardIIS[0].position, 4 + 7);
assert.equal(forwardIIS[0].bottom, 4 + 11);
assert.equal(forwardIIS[0].overhang, 4);

const reverseIIS = calc.cutSites("A".repeat(16) + "GAGACC" + "A".repeat(10), "BsaI", false);
assert.equal(reverseIIS.length, 1);
assert.equal(reverseIIS[0].strand, "-");
assert.equal(reverseIIS[0].position, 16 + 6 - 11);
assert.equal(reverseIIS[0].bottom, 16 + 6 - 7);
assert.equal(calc.byName("BsaI").typeIIS, true);
assert.equal(calc.describeEnds(calc.byName("EcoRI")), "5' overhang 4");
assert.equal(calc.describeEnds(calc.byName("KpnI")), "3' overhang 4");
assert.equal(calc.describeEnds(calc.byName("EcoRV")), "blunt");

// A palindromic enzyme is not counted twice.
assert.equal(calc.cutSites("AAAGAATTCAAA", "EcoRI", false).length, 1);

// A type IIS cut that would fall outside a linear molecule does not count.
assert.equal(calc.cutSites("GGTCTCAAA", "BsaI", false).length, 0);

// A circular type IIS cut wraps around the origin.
assert.equal(calc.cutSites("GGTCTCA" + "A".repeat(3), "BsaI", true)[0].position, 7);

console.log("molecular digest calc: OK");
