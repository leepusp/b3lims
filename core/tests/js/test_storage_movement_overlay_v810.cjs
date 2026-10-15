"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const controller = fs.readFileSync(
  "core/static/internal/storage/storage_relationship_v89.js",
  "utf8"
);

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
    this.content = this;
    this.classList = {
      add: name => {
        this.className = [...new Set([
          ...this.className.split(/\s+/).filter(Boolean),
          name
        ])].join(" ");
      }
    };
  }

  append(...items) {
    this.children.push(...items);
  }

  replaceChildren(...items) {
    this.children = [...items];
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  addEventListener(name, handler) {
    (this.listeners[name] ||= []).push(handler);
  }

  click() {
    for (const fn of this.listeners.click || []) {
      fn({});
    }
  }

  focus() {}

  querySelectorAll(selector) {
    if (selector === "[data-workspace-id]") {
      return this.workspaces || [];
    }
    if (selector === "[data-location-id]") {
      return this.locations || [];
    }
    if (selector === "[data-assignment-location]") {
      return this.assignments || [];
    }
    if (selector === "[data-b3-v89-movement-row]") {
      return this.rows || [];
    }
    return [];
  }

  querySelector(selector) {
    return this.lookup?.[selector] || null;
  }
}

function node(dataset = {}, textContent = "") {
  const result = new Element();
  result.dataset = dataset;
  result.textContent = textContent;
  return result;
}

const locations = [
  ["10", "", "1", "Room"],
  ["11", "10", "1", "Freezer"],
  ["12", "11", "1", "Box A"],
  ["13", "12", "1", "Position A1"],
  ["14", "11", "1", "Box B"],
  ["20", "", "2", "Other Room"],
  ["21", "20", "2", "Other Box"],
  ["30", "", "1", "Duplicate"],
  ["31", "30", "1", "Box"],
  ["40", "", "1", "Duplicate"],
  ["41", "40", "1", "Box"]
];

function comparison(kind, origin, destination, rows = []) {
  const item = node({
    b3V89MovementComparison: kind,
    b3V810ContainerId: origin,
    b3V810DestinationId: destination
  });
  item.rows = rows.map(([before, after]) => {
    const row = node();
    row.lookup = {
      "[data-b3-v89-path-before]": node({}, before),
      "[data-b3-v89-path-after]": node({}, after)
    };
    return row;
  });
  return item;
}

function run(comparisons, selectedIds) {
  const elements = new Map();
  const events = {};
  const register = id => {
    const item = new Element();
    elements.set(id, item);
    return item;
  };

  register("storage-relationship-v89");
  const source = register("storage-explorer-data");
  const workspaces = register(
    "storage-relationship-workspaces-v89"
  );
  register("storage-explorer-assignment-data");
  const selector = register(
    "storage-relationship-workspace-select-v89"
  );
  const diagram = register(
    "storage-relationship-diagram-v89"
  );
  register("storage-relationship-status-v89");
  register("storage-explorer-tree");

  selector.value = "1";
  workspaces.workspaces = [
    node({
      workspaceId: "1",
      workspaceName: "Lab 1",
      workspaceScope: "group"
    }),
    node({
      workspaceId: "2",
      workspaceName: "Lab 2",
      workspaceScope: "group"
    })
  ];

  source.locations = locations.map(
    ([id, parent, workspace, name]) => node({
      locationId: id,
      parentId: parent,
      workspaceId: workspace,
      locationName: name,
      locationType: "box",
      locationActive: "1"
    })
  );

  const document = {
    readyState: "complete",
    getElementById(id) {
      return elements.get(id) || null;
    },
    querySelectorAll(selectorText) {
      if (selectorText ===
          "[data-b3-v89-movement-comparison]") {
        return comparisons;
      }
      return [];
    },
    createElement(tag) {
      return new Element(tag);
    },
    createDocumentFragment() {
      return new Element("fragment");
    },
    addEventListener(name, callback) {
      (events[name] ||= []).push(callback);
    }
  };

  vm.runInNewContext(
    controller,
    {document, console, Event: class {}},
    {timeout: 2000}
  );

  for (const id of selectedIds) {
    for (const handler of
         events["b3-storage-location-selected"] || []) {
      handler({detail: {id}});
    }
  }

  function walk(element) {
    return [
      element,
      ...element.children.flatMap(walk)
    ];
  }

  function classes(id) {
    const match = walk(diagram).find(item =>
      item.className.includes("b3-v810-node") &&
      item.children.some(child =>
        child.dataset.locationId === id
      )
    );
    return match?.className || "";
  }

  return {classes, diagram};
}

function has(result, id, name) {
  return result.classes(id).split(/\s+/).includes(name);
}

const origin = "b3-v810-preview-origin";
const destination = "b3-v810-preview-destination";
const affected = "b3-v810-preview-affected";

{
  const result = run(
    [comparison("container", "12", "14")],
    ["13", "14"]
  );

  assert(has(result, "12", origin));
  assert(has(result, "14", destination));
  assert(has(result, "13", affected));
  assert(!has(result, "11", affected));
  console.log("CONTAINER_MOVEMENT=PASS");
}

{
  const result = run(
    [comparison("sample", "", "", [
      ["Room > Freezer > Box A",
       "Room > Freezer > Box B"]
    ])],
    ["12", "14"]
  );

  assert(has(result, "12", origin));
  assert(has(result, "14", destination));
  assert(!has(result, "13", affected));
  console.log("SAMPLE_MOVEMENT=PASS");
}

{
  const result = run(
    [comparison("bulk", "", "", [
      ["Room > Freezer > Box A",
       "Room > Freezer > Box B"],
      ["Room > Freezer > Box B",
       "Room > Freezer > Box A"]
    ])],
    ["12", "14"]
  );

  for (const id of ["12", "14"]) {
    assert(has(result, id, origin));
    assert(has(result, id, destination));
  }
  console.log("BULK_MOVEMENT=PASS");
}

{
  const result = run(
    [comparison("container", "12", "21")],
    ["12", "21"]
  );

  assert(!has(result, "12", origin));
  assert(!has(result, "21", destination));
  assert(!has(result, "13", affected));
  console.log("CROSS_WORKSPACE_REJECTED=PASS");
}

{
  const result = run(
    [comparison("sample", "", "", [
      ["Duplicate > Box",
       "Room > Freezer > Box A"]
    ])],
    ["31", "41", "12"]
  );

  assert(!has(result, "31", origin));
  assert(!has(result, "41", origin));
  assert(!has(result, "12", destination));
  console.log("AMBIGUOUS_PATH_REJECTED=PASS");
}

{
  const result = run([], ["12", "14"]);
  assert(!has(result, "12", origin));
  assert(!has(result, "14", destination));
  console.log("NO_PREVIEW=PASS");
}

assert(!controller.includes("requestSubmit("));
assert(!controller.includes(".submit("));
assert(!controller.includes("fetch("));
console.log("READ_ONLY_CONTROLLER=PASS");

console.log("V810_MOVEMENT_OVERLAY_TESTS=PASS");
