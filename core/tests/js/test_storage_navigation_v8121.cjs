"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../../..");

const controller = fs.readFileSync(
  path.join(
    root,
    "core/static/internal/storage/storage_navigation_v8121.js"
  ),
  "utf8"
);

const template = fs.readFileSync(
  path.join(
    root,
    "core/interfaces/internal/storage/_viewer_3d.html"
  ),
  "utf8"
);

const index = fs.readFileSync(
  path.join(
    root,
    "core/interfaces/internal/storage/index.html"
  ),
  "utf8"
);

for (const id of [
  "storage-designer-browse",
  "storage-designer-build",
  "storage-designer-browse-panel",
  "storage-designer-build-panel",
  "storage-3d-real",
  "storage-3d-example"
]) {
  assert.ok(template.includes(`id="${id}"`));
  assert.ok(controller.includes(`"${id}"`));
}

assert.equal(
  index.split("storage_navigation_v8121.js").length,
  2
);

assert.ok(
  index.indexOf("storage_workspace_shell_v812.js") <
  index.indexOf("storage_navigation_v8121.js")
);

assert.match(
  controller,
  /inventoryButton\.click\(\)/
);

assert.match(
  controller,
  /workspacesButton\.click\(\)/
);

assert.match(
  controller,
  /webglAvailable\(\)/
);

assert.doesNotMatch(
  controller,
  /fetch\(|XMLHttpRequest|\.submit\(/
);

console.log("V8121_NAVIGATION_CONTRACT=PASS");
