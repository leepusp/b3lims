const assert = require("assert");
const c = require("../../static/internal/lab_tools/eln_tools_calc.js");

let r = c.dilution(10, "", 1, 100);
assert.strictEqual(r.solved, "v1");
assert.strictEqual(r.value, 10);
assert.strictEqual(r.diluent, 90);
assert.ok(c.dilution(1, 1, 1, 1).error);
assert.strictEqual(c.dilution(10, 10, "", 100).value, 1);
assert.ok(c.dilution(1, 1, 10, "").warning);

r = c.solution(58.44, 150, 100, "");
assert.ok(Math.abs(r.mass - 876.6) < 1e-6);
assert.ok(Math.abs(c.solution(58.44, "", 100, 876.6).conc - 150) < 1e-6);
assert.ok(Math.abs(c.solution(58.44, 150, "", 876.6).vol - 100) < 1e-6);
assert.ok(c.solution("", 1, 1, "").error);

r = c.recipe(100, [{name: "Tris", stock: 1000, final: 50}, {name: "NaCl", stock: 5000, final: 150}]);
assert.ok(Math.abs(r.water - (100 - 5 - 3)) < 1e-9);
assert.ok(c.recipe(10, [{name: "x", stock: 1, final: 2}]).error);
assert.ok(Math.abs(c.recipe(50, [{name: "Buffer", stock: 10, final: 1}]).rows[0].volume - 5) < 1e-9);

r = c.masterMix(10, 10, [{name: "Buffer", perReaction: 2}, {name: "Water", perReaction: 8}]);
assert.ok(Math.abs(r.total - 110) < 1e-9);
assert.strictEqual(r.perReactionTotal, 10);

r = c.cfu(150, 0.1, 6);
assert.ok(Math.abs(r.perMl - 1.5e9) < 1);
assert.ok(c.cfu(10, 0.1, 6).note);
assert.ok(c.cfu("", 1, 1).error);

console.log("eln calc ok");
