const assert = require("assert");
const E = require("../../static/internal/lab_tools/eln_elements.js");

assert.strictEqual(E.list.length, 118);
assert.strictEqual(E.list[0].symbol, "H");
assert.strictEqual(E.list[117].symbol, "Og");
assert.strictEqual(E.bySymbol.Fe.z, 26);

// every element has a unique cell and the table shape is right
const cells = new Set(E.list.map(e => e.row + ":" + e.col));
assert.strictEqual(cells.size, 118);
assert.deepStrictEqual([E.bySymbol.H.row, E.bySymbol.H.col], [1, 1]);
assert.deepStrictEqual([E.bySymbol.He.row, E.bySymbol.He.col], [1, 18]);
assert.deepStrictEqual([E.bySymbol.Al.row, E.bySymbol.Al.col], [3, 13]);
assert.deepStrictEqual([E.bySymbol.Fe.row, E.bySymbol.Fe.col], [4, 8]);
assert.deepStrictEqual([E.bySymbol.Hf.row, E.bySymbol.Hf.col], [6, 4]);
assert.deepStrictEqual([E.bySymbol.Rn.row, E.bySymbol.Rn.col], [6, 18]);
assert.deepStrictEqual([E.bySymbol.Og.row, E.bySymbol.Og.col], [7, 18]);
assert.deepStrictEqual([E.bySymbol.La.row, E.bySymbol.La.col], [8, 3]);
assert.deepStrictEqual([E.bySymbol.Lu.row, E.bySymbol.Lu.col], [8, 17]);
assert.deepStrictEqual([E.bySymbol.U.row, E.bySymbol.U.col], [9, 6]);
assert.strictEqual(E.bySymbol.Na.category, "alkali");
assert.strictEqual(E.bySymbol.Cl.category, "halogen");
assert.strictEqual(E.bySymbol.Fe.category, "transition");

const near = (a, b) => Math.abs(a - b) < 0.01;
assert.ok(near(E.molarMass("C6H12O6").mass, 180.156));
assert.ok(near(E.molarMass("Ca(OH)2").mass, 74.093));
assert.ok(near(E.molarMass("NaCl").mass, 58.44));
assert.ok(near(E.molarMass("CuSO4·5H2O").mass, 249.685));
assert.ok(near(E.molarMass("Al2(SO4)3").mass, 342.132));
assert.ok(E.molarMass("Xx2").error);
assert.ok(E.molarMass("Ca(OH").error);
assert.ok(E.molarMass("").error);

console.log("eln elements ok");
