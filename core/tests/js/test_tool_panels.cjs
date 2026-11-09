"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dir = path.join(__dirname, "../../static/internal/lab_tools");

function load(file, hostId) {
    const host = {
        append() {}, replaceChildren() {}, addEventListener() {}, style: {},
    };
    const node = () => ({
        append() {}, replaceChildren() {}, addEventListener() {}, style: {}, classList: {add() {}, remove() {}, toggle() {}},
        setAttribute() {}, appendChild() {}, remove() {}, value: "", dataset: {},
    });
    const sandbox = {
        window: {},
        document: {
            getElementById: id => (id === hostId ? host : id === "tool-workbench" ? {dataset: {}} : null),
            createElement: node,
            createElementNS: node,
            dispatchEvent() {},
            addEventListener() {},
            querySelector: () => null,
        },
        CustomEvent: function () {},
        navigator: {},
    };

    sandbox.window.window = sandbox.window;
    vm.runInNewContext(fs.readFileSync(path.join(dir, file), "utf8"), sandbox);

    return sandbox.window;
}

const chem = load("tool_chemical_panel.js", "tw-chemical").BiobankChemical;
const near = (a, b, eps) => assert(Math.abs(a - b) < eps, `${a} != ${b}`);

// Aspirin
near(chem.masses(chem.parseFormula("C9H8O4")).average, 180.157, 0.01);
near(chem.masses(chem.parseFormula("C9H8O4")).exact, 180.04226, 0.0005);
// Parentheses and hydrates
assert.strictEqual(JSON.stringify(chem.parseFormula("Ca(OH)2")), JSON.stringify({Ca: 1, O: 2, H: 2}));
assert.strictEqual(JSON.stringify(chem.parseFormula("CuSO4.5H2O")), JSON.stringify({Cu: 1, S: 1, O: 9, H: 10}));
assert.strictEqual(chem.parseFormula("Xx2"), null);
assert.strictEqual(chem.parseFormula("C6H12O6)"), null);

const asm = load("tool_assembly_panel.js", "tw-assembly").BiobankAssembly;
const A = "ATGGCTAGCTAGGATCCGATTACAGGCT";
const B = "GATTACAGGCTAAAGGTTCCATCGATCGA"; // overlaps A's last 11 bp "GATTACAGGCT"

asm.setState({parts: [], method: "overlap", minOverlap: 10, circular: false});
asm.addPart("A", A);
asm.addPart("B", B);

let out = asm.assemble();

assert.strictEqual(out.seq, A + B.slice(11));
assert.strictEqual(out.junctions[0].overlap, 11);
assert(out.junctions[0].ok);

// No overlap → flagged, but still joined
asm.setState({parts: [{id: 1, name: "A", seq: "AAAACCCCGGGG"}, {id: 2, name: "B", seq: "TTTTTTTTTTTT"}], method: "overlap", minOverlap: 10, circular: false, nextId: 3});
out = asm.assemble();
assert(!out.junctions[0].ok);

// Direct join and reverse complement
asm.setState({parts: [{id: 1, name: "A", seq: "AAAC"}, {id: 2, name: "B", seq: "GGGT", rc: true}], method: "direct", circular: false, nextId: 3});
assert.strictEqual(asm.assemble().seq, "AAAC" + "ACCC");

// Circular overlap: last part's end overlaps the first part's start
const first = "GGATCCATGAAAGCTTGGAAATTTCCC";
const last = "TTTGGGCCCAAATTTGGATCCATGAAA"; // ends with first's 15-mer start
asm.setState({parts: [{id: 1, name: "F", seq: first}, {id: 2, name: "L", seq: last}], method: "overlap", minOverlap: 12, circular: true, nextId: 3});
out = asm.assemble();
assert(out.junctions[1].ok && out.junctions[1].overlap >= 12 && !out.junctions[0].ok, JSON.stringify(out.junctions));

console.log("tool panels ok");
