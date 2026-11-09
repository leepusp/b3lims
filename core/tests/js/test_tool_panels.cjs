"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const dir = path.join(__dirname, "../../static/internal/lab_tools");

function load(file, hostId) {
    const host = {
        append() {}, replaceChildren() {}, addEventListener() {}, style: {}, dataset: {}, querySelectorAll: () => [],
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
            createTextNode: () => ({}),
            createElementNS: node,
            dispatchEvent() {},
            addEventListener() {},
            querySelector: () => null,
            querySelectorAll: () => [],
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

// SMILES / MOL → formula
function smilesFormula(text) {
    const mol = chem.parseSmiles(text);

    return mol ? chem.prettyFormula(chem.formulaOf(mol).counts) : null;
}

assert.strictEqual(smilesFormula("CC(=O)Oc1ccccc1C(=O)O"), "C9H8O4");
assert.strictEqual(smilesFormula("CCO"), "C2H6O");
assert.strictEqual(smilesFormula("c1ccccc1"), "C6H6");
assert.strictEqual(smilesFormula("c1ccncc1"), "C5H5N");
assert.strictEqual(smilesFormula("c1cc[nH]c1"), "C4H5N");
assert.strictEqual(smilesFormula("CC(=O)[O-].[Na+]"), "C2H3NaO2");
assert.strictEqual(smilesFormula("[NH4+]"), "H4N");
assert.strictEqual(smilesFormula("O=C=O"), "CO2");
assert.strictEqual(smilesFormula("c1ccc2ccccc2c1"), "C10H8");
assert.strictEqual(smilesFormula("ClCCBr"), "C2H4BrCl");
assert.strictEqual(smilesFormula("C1CC"), null);
assert.strictEqual(smilesFormula("C(C"), null);
assert.strictEqual(smilesFormula("Xyz"), null);

const molText = [
    "ethanol", "  test", "",
    "  3  2  0  0  0  0  0  0  0  0999 V2000",
    "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0",
    "    1.2000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0",
    "    2.4000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0",
    "  1  2  1  0", "  2  3  1  0", "M  END", ""].join("\n");

assert.strictEqual(chem.prettyFormula(chem.formulaOf(chem.parseMol(molText)).counts), "C2H6O");
assert.strictEqual(chem.parseMol("nope"), null);

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

// ---- working sequence shim used by Digest / Primers / Cloning on tool pages ----
{
    const listeners = [];
    const node = () => ({append() {}, replaceChildren() {}, addEventListener() {}, style: {}, classList: {add() {}, remove() {}, toggle() {}}, setAttribute() {}, value: "", dataset: {}, hidden: false});
    const rootNode = Object.assign(node(), {dispatchEvent: event => listeners.push(event.type)});
    const sandbox = {
        window: {},
        document: {
            getElementById: id => (id === "molecular-workspace" ? rootNode : id === "tw-sequence" ? node() : id === "tool-workbench" ? {dataset: {}} : null),
            createElement: node,
            dispatchEvent() {},
            addEventListener() {},
        },
        CustomEvent: function (type) {
            this.type = type;
        },
    };

    sandbox.window.window = sandbox.window;
    vm.runInNewContext(fs.readFileSync(path.join(dir, "tool_sequence_window.js"), "utf8"), sandbox);

    const ws = sandbox.window.BiobankMolecularWorkspace;
    const seq = sandbox.window.BiobankToolSequence;

    seq.set("vec", ">x\nAAAA CCCC\nGGGG TTTT", "circular");
    let snap = ws.getSnapshot();

    assert.strictEqual(snap.sequence, "AAAACCCCGGGGTTTT");
    assert.strictEqual(snap.topology, "circular");
    assert(listeners.indexOf("biobank:molecular-workspace-change") !== -1);

    // 1-based inclusive selection; replaceRange takes 0-based slice positions.
    ws.selectSequenceRange(5, 8);
    snap = ws.getSnapshot();
    assert.strictEqual(JSON.stringify(snap.sequenceSelection), JSON.stringify({start: 5, end: 8}));
    assert(ws.createFeatureFromSelection({name: "mid", type: "custom"}));
    ws.selectSequenceRange(13, 16);
    ws.createFeatureFromSelection({name: "tail", type: "primer", strand: "-"});

    // Replace the first four bases: later features move, none is lost, none crosses the edit.
    assert(ws.replaceRange(0, 4, "GAATTCGAATTC"));
    snap = ws.getSnapshot();
    assert.strictEqual(snap.sequence, "GAATTCGAATTC" + "CCCCGGGGTTTT");
    assert.strictEqual(snap.features.length, 2);
    assert.strictEqual(snap.features[0].start, 5 + 8);
    assert.strictEqual(snap.sequenceSelection, null);

    // A feature crossing the edit is dropped.
    ws.replaceRange(14, 18, "");
    assert.strictEqual(ws.getSnapshot().features.length, 1);
}
console.log("sequence window ok");

// ---- RNA / protein calculations ----
const bio = require(path.join(dir, "tool_bio_calc.js"));
const gfp = "MSKGEELFTGVVPILVELDGDVNGHKFSVSGEGEGDATYGKLTLKFICTTGKLPVPWPTLVTTFSYGVQCFSRYPDHMKQHDFFKSAMPEGYVQERTIFFKDDGNYKTRAEVKFEGDTLVNRIELKGIDFKEDGNILGHKLEYNYNSHNVYIMADKQKNGIKVNFKIRHNIEDGSVQLADHYQQNTPIGDGPVLLPDNHYLSTQSALSKDPNEKRDHMVLLEFVTAAGITHGMDELYK";
const pr = bio.proteinReport(gfp, 7.4);

assert.strictEqual(pr.length, 238);
near(pr.mass / 1000, 26.886, 0.01);
near(pr.pI, 5.99, 0.01);
near(pr.charge, -7.1, 0.05);
assert.strictEqual(pr.epsilon280, 22015);
assert.strictEqual(bio.proteinReport("XXXX"), null);
assert.strictEqual(bio.hydropathy("AAAAAAAAAAAA", 5)[0], null);
near(bio.hydropathy("IIIIIIIIIII", 5)[5], 4.5, 1e-9);

const rr = bio.rnaReport("GGGGAAAACCCCTTTT"); // T is read as U

assert.strictEqual(rr.counts.U, 4);
near(rr.gc, 50, 1e-9);
assert.strictEqual(bio.reverseComplement("AUGC", true), "GCAU");
assert.strictEqual(bio.translate("ATGGCTAGCTAA", 0), "MAS*");
assert.strictEqual(bio.translate("AUGGCUAGCUAA", 0), "MAS*");
assert.strictEqual(bio.findOrfs("ATGAAATTTGGGCCCTAA", 3)[0].protein, "MKFGP");
assert.strictEqual(bio.findOrfs("TTAGGGCCCAAATTTCAT", 3)[0].strand, "-");

const hp = bio.foldRna("GGGGAAACCCC");

assert.strictEqual(hp.structure, "((((...))))");
assert(hp.energy < 0);
assert.strictEqual(bio.foldRna("AAAAAAAAAAAA").structure, ".".repeat(12));

const trnaSeq = "GCGGAUUUAGCUCAGUUGGGAGAGCGCCAGACUGAAGAUCUGGAGGUCCUGUGUUCGAUCCACAGAAUUCGCACCA";
const fold = bio.foldRna(trnaSeq);
const parsedFold = bio.parseDotBracket(fold.structure, trnaSeq);

assert(!parsedFold.error);
assert(parsedFold.pairs.length >= 15);
assert(parsedFold.pairs.every(([a, b]) => bio.pairType(trnaSeq[a], trnaSeq[b])), "predicted pairs must be A-U, G-C or G-U");
assert(bio.parseDotBracket("((.", "AAA").error);
assert(bio.parseDotBracket("(.", "AAA").error);
assert(bio.parseDotBracket("x..", "AAA").error);
assert.throws(() => bio.foldRna("A".repeat(bio.MAX_FOLD + 1)));
console.log("bio calc ok");
