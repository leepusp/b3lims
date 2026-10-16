"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../..");

const file = path.join(
  root,
  "core/static/internal/storage/storage_isometric_v813.js"
);

const window = {};

vm.runInNewContext(
  fs.readFileSync(file, "utf8"),
  {window}
);

const {build, layout} = window.B3StorageSVGV813;

const data = build(
  [
    {id: "1", name: "Physical freezer", kind: "freezer"},
    {id: "2", parent: "1", name: "Physical box", kind: "box"}
  ],
  [
    {id: "1", name: "Historical freezer", kind: "freezer"},
    {id: "2", parent: "1", name: "Historical box", kind: "box"}
  ],
  [
    {box: "2", code: "PHYS", position: "A1", status: "active"}
  ],
  [
    {box: "2", code: "HIST", position: "B5"}
  ]
);

assert.equal(data.nodes.size, 4);

assert.equal(
  data.nodes.get("p:2").parentKey,
  "p:1"
);

assert.equal(
  data.nodes.get("h:2").parentKey,
  "h:1"
);

assert.equal(data.counts.get("p:1"), 1);
assert.equal(data.counts.get("h:1"), 1);

assert.equal(
  data.samples.get("h:2")[0].legacy,
  true
);

const overview = layout(data);
assert.equal(overview.items.length, 4);
assert.equal(overview.edges.length, 2);

const focused = layout(data, "h:1");
assert.equal(focused.items.length, 2);

const cycle = build(
  [
    {id: "a", parent: "b", name: "A"},
    {id: "b", parent: "a", name: "B"}
  ],
  [], [], []
);

assert.equal(layout(cycle).items.length, 2);

const index = fs.readFileSync(
  path.join(root, "core/interfaces/internal/storage/index.html"),
  "utf8"
);

const template = fs.readFileSync(
  path.join(
    root,
    "core/interfaces/internal/storage/_viewer_3d.html"
  ),
  "utf8"
);

assert.match(index, /storage_isometric_v813\.js/);

assert.doesNotMatch(
  index,
  /src="[^"]*storage_viewer_3d\.js/
);

assert.match(
  template,
  /id="storage-isometric-v813"/
);

assert.doesNotMatch(
  template,
  /id="storage-3d-canvas"/
);

assert.doesNotMatch(
  fs.readFileSync(file, "utf8"),
  /WebGLRenderer|getContext\(["']webgl/
);

console.log("V813_SVG_DATA_MODEL=PASS");
console.log("V813_SVG_HIERARCHY=PASS");
console.log("V813_NO_WEBGL_RUNTIME=PASS");
