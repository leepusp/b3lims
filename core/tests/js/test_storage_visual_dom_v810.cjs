"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.listeners = {};
    this.value = "";
    this.textContent = "";
    this.className = "";
    this.disabled = false;
    this.title = "";
    this.style = {};

    this.classList = {
      add: name => {
        this.className = [
          ...new Set(
            [...this.className.split(/\s+/), name].filter(Boolean)
          )
        ].join(" ");
      }
    };

    this.content = this;
  }

  append(...nodes) {
    this.children.push(...nodes);
  }

  replaceChildren(...nodes) {
    this.children = [...nodes];
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  addEventListener(name, callback) {
    (this.listeners[name] ||= []).push(callback);
  }

  dispatch(name, detail = {}) {
    for (const callback of this.listeners[name] || []) {
      callback({detail});
    }
  }

  click() {
    this.dispatch("click");
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
    return [];
  }

  querySelector() {
    return null;
  }
}

const elements = new Map();

function register(id, element = new Element()) {
  elements.set(id, element);
  return element;
}

const panel = register("storage-relationship-v89");
const source = register("storage-explorer-data");
const workspaceSource = register(
  "storage-relationship-workspaces-v89"
);
const assignmentSource = register(
  "storage-explorer-assignment-data"
);
const selector = register(
  "storage-relationship-workspace-select-v89"
);
const diagram = register(
  "storage-relationship-diagram-v89"
);
register("storage-relationship-status-v89");
register("storage-explorer-tree");

const workspace = new Element();
workspace.dataset = {
  workspaceId: "1",
  workspaceName: "Laboratory",
  workspaceScope: "group"
};

workspaceSource.workspaces = [workspace];

// The minimal DOM does not implement native <select> behavior.
// Explicitly select the authorized workspace used by this test.
selector.value = "1";

function location(id, parent, name, type) {
  const node = new Element();
  node.dataset = {
    locationId: id,
    parentId: parent,
    workspaceId: "1",
    locationName: name,
    locationType: type,
    locationActive: "1"
  };
  return node;
}

source.locations = [
  location("10", "", "Room", "room"),
  location("11", "10", "Freezer", "freezer"),
  location("12", "11", "Box A", "box")
];

function assignment(id) {
  const node = new Element();
  node.dataset = {
    assignmentLocation: id,
    assignmentStatus: "active"
  };
  return node;
}

assignmentSource.assignments = [
  assignment("12"),
  assignment("12")
];

const listeners = {};

const document = {
  readyState: "complete",

  // No authorized movement preview is present in this fixture.
  querySelectorAll(selector) {
    if (selector === "[data-b3-v89-movement-comparison]") {
      return [];
    }
    return [];
  },

  getElementById(id) {
    return elements.get(id) || null;
  },

  createElement(tag) {
    return new Element(tag);
  },

  createDocumentFragment() {
    return new Element("fragment");
  },

  addEventListener(name, callback) {
    (listeners[name] ||= []).push(callback);
  }
};

const sourceCode = fs.readFileSync(
  "core/static/internal/storage/storage_relationship_v89.js",
  "utf8"
);

vm.runInNewContext(
  sourceCode,
  {document, console, Event: class {}},
  {timeout: 2000}
);

function flatten(node) {
  return [
    node,
    ...node.children.flatMap(flatten)
  ];
}

const initial = flatten(diagram);

const room = initial.find(
  node => node.dataset.locationId === "10"
);

assert(room, "Root location not rendered");
console.log("ROOT_NODE_RENDERED=PASS");

const rootSummary = initial.find(
  node => node.className.includes("b3-v810-summary")
);

assert(rootSummary);
assert(rootSummary.textContent.includes("2 in subtree"));
console.log("SUBTREE_COUNT_RENDERED=PASS");

const rootRow = initial.find(
  node => node.className.includes("b3-v810-node")
);

assert(rootRow, "Visual node class missing");
console.log("VISUAL_NODE_RENDERED=PASS");

const toggle = initial.find(
  node => node.className.includes("b3-v810-toggle")
);

assert(toggle);
assert.equal(toggle.getAttribute("aria-expanded"), "false");

toggle.click();

const expanded = flatten(diagram);

assert(
  expanded.some(node => node.dataset.locationId === "11"),
  "Freezer was not rendered after expansion"
);

console.log("EXPANSION=PASS");

assert(
  panel.children.some(node => node.tagName === "style"),
  "Scoped stylesheet missing"
);

console.log("SCOPED_STYLES=PASS");
console.log("V810_DOM_BEHAVIOR=PASS");
