"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(
  "core/static/internal/storage/storage_relationship_v89.js",
  "utf8"
);

const startToken = "    const subtreeCounts = new Map();";
// Stop before presentation code; this test evaluates calculations.
const endToken = source.includes(
  'const visualStyle = document.createElement("style");'
)
  ? 'const visualStyle = document.createElement("style");'
  : "    const expanded = new Set();";

const start = source.indexOf(startToken);
const end = source.indexOf(endToken, start);

assert(start >= 0, "Subtree aggregation not found");
assert(end > start, "Aggregation boundary not found");
assert.equal(source.indexOf(startToken, start + 1), -1);

const implementation = source.slice(start, end);

function run(locations, assignments, authorized) {
  const byId = new Map(
    locations.map(item => [item.id, item])
  );

  const counts = new Map();

  for (const id of assignments) {
    counts.set(id, (counts.get(id) || 0) + 1);
  }

  const sandbox = {
    byId,
    counts,
    safeIds: new Set(authorized)
  };

  vm.runInNewContext(
    implementation +
      "\n" +
      "globalThis.result = {" +
      " counts: Object.fromEntries(subtreeCounts)," +
      " path: physicalPath" +
      "};",
    sandbox,
    {timeout: 1000}
  );

  return sandbox.result;
}

const locations = [
  {id: "1", parent: "", name: "Room", workspace: "w1"},
  {id: "2", parent: "1", name: "Freezer", workspace: "w1"},
  {id: "3", parent: "2", name: "Box A", workspace: "w1"},
  {id: "4", parent: "2", name: "Box B", workspace: "w1"},
  {id: "5", parent: "", name: "Other Room", workspace: "w2"},
  {id: "6", parent: "5", name: "Other Box", workspace: "w2"}
];

const result = run(
  locations,
  ["3", "3", "4", "6"],
  locations.map(item => item.id)
);

assert.equal(result.counts["3"], 2);
assert.equal(result.counts["4"], 1);
assert.equal(result.counts["2"], 3);
assert.equal(result.counts["1"], 3);
console.log("SUBTREE_AGGREGATION=PASS");

assert.equal(result.counts["5"], 1);
assert.equal(result.counts["6"], 1);
console.log("WORKSPACE_ISOLATION=PASS");

assert.equal(
  result.path(locations[2]),
  "Room > Freezer > Box A"
);
console.log("PHYSICAL_PATH=PASS");

const restricted = run(
  locations,
  ["3", "6"],
  ["1", "2", "3"]
);

assert.equal(restricted.counts["1"], 1);
assert.equal(restricted.counts["5"], undefined);
console.log("AUTHORIZED_NODES_ONLY=PASS");

const crossWorkspace = [
  {id: "10", parent: "20", name: "Box", workspace: "w1"},
  {id: "20", parent: "", name: "Foreign", workspace: "w2"}
];

const cross = run(
  crossWorkspace,
  ["10"],
  ["10", "20"]
);

assert.equal(cross.counts["10"], 1);
assert.equal(cross.counts["20"], undefined);
assert.equal(cross.path(crossWorkspace[0]), "Box");
console.log("CROSS_WORKSPACE_PARENT=PASS");

const cyclic = [
  {id: "30", parent: "31", name: "A", workspace: "w1"},
  {id: "31", parent: "30", name: "B", workspace: "w1"}
];

const cycle = run(cyclic, ["30"], ["30", "31"]);

assert.equal(cycle.counts["30"], 1);
assert.equal(cycle.counts["31"], 1);
assert.equal(cycle.path(cyclic[0]), "B > A");
console.log("CYCLE_TERMINATION=PASS");

console.log("V810_AGGREGATION_TESTS=PASS");
