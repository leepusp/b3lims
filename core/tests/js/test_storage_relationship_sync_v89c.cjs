"use strict";

const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");

const source = fs.readFileSync(
  "core/static/internal/storage/storage_relationship_v89.js",
  "utf8"
);

const startMarker =
  "    // Keep the hierarchy map synchronized";

const endMarker = "\n    render();\n  }\n";

const start = source.indexOf(startMarker);
const end = source.indexOf(endMarker, start);

assert(start >= 0, "Synchronization listener not found");
assert(end > start, "Listener boundary not found");

const handler = source.slice(start, end);

function scenario(locations, authorized, eventId) {
  const callbacks = new Map();
  const selector = {value: ""};
  const expanded = new Set();
  const byId = new Map(locations.map(x => [x.id, x]));
  const safeIds = new Set(authorized);
  const allowed = new Set(["w1", "w2"]);
  let renders = 0;

  const sandbox = {
    document: {
      addEventListener(name, callback) {
        callbacks.set(name, callback);
      }
    },
    byId,
    safeIds,
    allowed,
    selector,
    expanded,
    render() {
      renders++;
    }
  };

  vm.runInNewContext(
    'let selectedId = "";\n' +
    handler +
    '\nglobalThis.readSelection = () => selectedId;',
    sandbox,
    {timeout: 1000}
  );

  const listener = callbacks.get(
    "b3-storage-location-selected"
  );

  assert.equal(typeof listener, "function");

  listener({detail: {id: eventId}});

  return {
    selected: sandbox.readSelection(),
    workspace: selector.value,
    expanded: [...expanded],
    renders
  };
}

const locations = [
  {id: "1", parent: "", workspace: "w1"},
  {id: "2", parent: "1", workspace: "w1"},
  {id: "3", parent: "2", workspace: "w1"},
  {id: "4", parent: "", workspace: "w2"},
  {id: "5", parent: "4", workspace: "w2"}
];

const authorized = locations.map(x => x.id);

const deep = scenario(locations, authorized, "3");
assert.equal(deep.selected, "3");
assert.equal(deep.workspace, "w1");
assert.deepEqual(deep.expanded.sort(), ["1", "2"]);
assert.equal(deep.renders, 1);
console.log("DEEP_SELECTION=PASS");

const second = scenario(locations, authorized, "5");
assert.equal(second.selected, "5");
assert.equal(second.workspace, "w2");
assert.deepEqual(second.expanded, ["4"]);
console.log("WORKSPACE_SELECTION=PASS");

const blocked = scenario(
  locations,
  ["1", "2", "3"],
  "5"
);
assert.equal(blocked.selected, "");
assert.equal(blocked.renders, 0);
console.log("UNAUTHORIZED_SELECTION=PASS");

const cyclic = scenario([
  {id: "7", parent: "8", workspace: "w1"},
  {id: "8", parent: "7", workspace: "w1"}
], ["7", "8"], "7");

assert.equal(cyclic.selected, "7");
assert.equal(cyclic.renders, 1);
assert.deepEqual(cyclic.expanded, ["8"]);
console.log("CYCLE_PROTECTION=PASS");

console.log("TREE_SYNC_LISTENER_TESTS=PASS");
