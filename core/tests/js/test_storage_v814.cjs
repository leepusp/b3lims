"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../..");

const js = fs.readFileSync(
  path.join(
    root,
    "core/static/internal/storage/storage_v814.js"
  ),
  "utf8"
);

const html = fs.readFileSync(
  path.join(
    root,
    "core/interfaces/internal/storage/index_v814.html"
  ),
  "utf8"
);

const view = fs.readFileSync(
  path.join(
    root,
    "core/views/internal/storage/views.py"
  ),
  "utf8"
);

const window = {};

vm.runInNewContext(js, {window});

const build = window.B3StorageV814.buildModel;

const rows = [
  {id: "1", parent: "", workspace: "a", name: "Room"},
  {id: "2", parent: "1", workspace: "a", name: "Freezer"},
  {id: "3", parent: "2", workspace: "a", name: "Box"},
  {id: "4", parent: "3", workspace: "b", name: "Invalid"},
  {id: "5", parent: "6", workspace: "a", name: "Cycle A"},
  {id: "6", parent: "5", workspace: "a", name: "Cycle B"}
];

const result = build(rows);

assert.deepEqual(
  Array.from(result, item => item.id),
  ["1", "2", "3"]
);

for (const term of [
  "b3s-location-data",
  "b3s-sample-data",
  "b3s-tree",
  "b3s-path-tree",
  "b3s-movements",
  "create_location",
  "csrf_token"
]) {
  assert.ok(html.includes(term), term);
}

assert.ok(
  view.includes("index_v814.html")
);

assert.ok(
  view.includes(
    "location_id__in=visible_location_ids_v814"
  )
);

assert.doesNotMatch(
  js,
  /localStorage|sessionStorage|WebGLRenderer/
);

// Exactly one authorized, read-only preview request
// is permitted before server-confirmed deletion.
assert.doesNotMatch(
  js,
  /XMLHttpRequest|\.submit\(/
);

const previewFetchCalls = js.match(/\bfetch\s*\(/g) || [];

assert.equal(previewFetchCalls.length, 1);

assert.match(
  js,
  /url\.searchParams\.set\(\s*"b3s_delete_preview"/
);

assert.match(
  js,
  /await fetch\(url\.toString\(\), \{/
);

assert.match(
  js,
  /credentials:\s*"same-origin"/
);


assert.match(
  js,
  /legacyProjection\.nodes/
);

assert.match(
  js,
  /visibleLegacySamples/
);

assert.match(
  js,
  /Historical registration/
);

assert.match(
  view,
  /request\.GET\.get\("legacy"\) == "1"/
);

assert.match(
  view,
  /response\["Location"\] \+= "\?legacy=1"/
);

console.log("V814_HISTORICAL_PROJECTION=PASS");
console.log("V814_PREVIEW_REDIRECT=PASS");


for (const token of [
  "b3s-existing-locations",
  "b3s-manage-selected",
  "b3s-edit-form",
  "b3s-status-form",
  "update_location",
  "Save changes",
  "Create physical location"
]) {
  assert.ok(html.includes(token), token);
}

for (const token of [
  "function renderManage()",
  "function renderTree()",
  "function renderGraph()",
  "function beginEdit(node)",
  "function beginChild(node)",
  "delete_empty_subtree",
  "reactivate_location",
  "b3s-branches",
  "b3s-path-card"
]) {
  assert.ok(js.includes(token), token);
}

assert.ok(
  js.includes("node.historical")
);

assert.ok(
  js.includes("if (!manageable(node)) return")
);

assert.doesNotMatch(
  js,
  /StorageLocation\.objects\.delete|localStorage/
);

console.log("V8142_CONNECTED_NAVIGATION=PASS");
console.log("V8142_CONNECTED_PATH_TREE=PASS");
console.log("V8142_MANAGE_EXISTING=PASS");
console.log("V8142_HISTORICAL_READ_ONLY=PASS");
console.log("V8142_SAFE_STATUS_ACTIONS=PASS");


for (const token of [
  'id="b3s-location-dialog"',
  'id="b3s-position-map"',
  'id="b3s-existing-locations"',
  'id="b3s-edit-form"'
]) {
  assert.ok(html.includes(token), token);
}

assert.ok(
  !html.includes("Create personal workspace")
);

assert.ok(
  !html.includes("<h3>Create physical location</h3>")
  || html.indexOf("<h3>Create physical location</h3>") >
     html.indexOf('id="b3s-location-dialog"')
);

for (const token of [
  "function renderPositionMap()",
  "function openLocationDialog()",
  "function closeLocationDialog()",
  "locationDialog.showModal()",
  "Other positions have not been verified as free"
]) {
  assert.ok(js.includes(token), token);
}

assert.ok(
  !js.includes('"+ Create child"')
);

console.log("V8143_NEW_LOCATION_MODAL=PASS");
console.log("V8143_MANAGE_EXISTING_ONLY=PASS");
console.log("V8143_RECORDED_POSITIONS=PASS");


const defaultTemplate = view.lastIndexOf(
  '"internal/storage/index_v814.html"'
);

const fallbackTemplate = view.lastIndexOf(
  '"internal/storage/index.html"'
);

assert.ok(defaultTemplate > fallbackTemplate);

assert.doesNotMatch(
  view,
  /request\.GET\.get\("v814"\) == "1"/
);

assert.ok(
  view.includes(
    'ctx["storage_v814_assignments"]'
  )
);

assert.ok(!html.includes("?v814=1"));

assert.ok(
  js.includes("b3s-history-record")
);

assert.ok(
  js.includes("const fullPath = position")
);

console.log("V8144_DEFAULT_ROUTING=PASS");
console.log("V8144_LEGACY_FALLBACK=PASS");
console.log("V8144_CLEAN_FORM_ACTIONS=PASS");
console.log("V8144_HISTORICAL_SAMPLE_PATHS=PASS");


for (const token of [
  "collapsedLocations",
  "b3s-tree-toggle",
  "aria-expanded",
  "b3s_delete_preview",
  "delete_empty_subtree",
  "preview.assignment_count"
]) {
  assert.ok(js.includes(token), token);
}

assert.ok(
  html.includes('name="confirm"')
);

console.log("V8145_TREE_COLLAPSE=PASS");
console.log("V8145_DELETE_PREVIEW=PASS");
console.log("V8145_SERVER_CONFIRMATION=PASS");

console.log("V814_HIERARCHY_MODEL=PASS");
console.log("V814_AUTHORIZED_ASSIGNMENTS=PASS");
console.log("V814_NEW_TEMPLATE=PASS");
console.log("V814_NO_BROWSER_PERSISTENCE=PASS");
