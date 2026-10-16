"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const file = path.resolve(
  __dirname,
  "../../static/internal/storage/storage_graph_v811.js"
);

const context = {window: {}};

vm.runInNewContext(
  fs.readFileSync(file, "utf8"),
  context
);

const {build, position} = context.window.B3GraphV811;

const model = build(
  [
    {id: "1", name: "Freezer Regina", kind: "freezer"},
    {id: "2", parent: "1", name: "Caixa 1.1", kind: "box"}
  ],
  [
    {id: "1", name: "Freezer Chuck", kind: "freezer"},
    {id: "2", parent: "1", name: "Caixa 1.2", kind: "box"}
  ],
  [
    {box: "2", code: "P46", position: "B5", status: "active"}
  ],
  [
    {box: "2", code: "P47", position: "B5", status: "active"}
  ]
);

assert.equal(model.nodes.size, 4);
assert.equal(model.counts.get("p:1"), 1);
assert.equal(model.counts.get("h:1"), 1);

assert.equal(
  model.nodes.get("p:2").parentKey,
  "p:1"
);

assert.equal(
  model.nodes.get("h:2").parentKey,
  "h:1"
);

assert.equal(
  model.nodes.get("h:2").historical,
  true
);

const graph = position(
  model,
  new Set(),
  "h:2"
);

assert.equal(graph.result.length, 5);
assert.equal(graph.edges.length, 3);

assert.equal(
  graph.result.some(
    item => item.sample?.code === "P47"
  ),
  true
);

assert.equal(
  graph.result.some(
    item => item.sample?.code === "P46"
  ),
  false
);

const scoped = {
  nodes: new Map(
    [...model.nodes].filter(
      ([key]) => key.startsWith("p:")
    )
  ),
  samples: model.samples,
  counts: model.counts
};

assert.equal(
  position(scoped).result.length,
  2
);

assert.equal(
  position(model, new Set(), null, "P47")
    .result.some(item => item.key === "h:2"),
  true
);

assert.equal(
  position(model, new Set(), null, "P47")
    .result.some(item => item.key === "p:2"),
  false
);

const cycle = build(
  [
    {id: "a", parent: "b", name: "A"},
    {id: "b", parent: "a", name: "B"}
  ],
  [],
  [],
  []
);

assert.equal(
  position(cycle).result.length,
  2
);

console.log("V811_GRAPH_DATA_LAYOUT=PASS");
