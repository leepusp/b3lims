"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function element() {
  const events = {};
  const attributes = {};
  const classes = new Set();

  return {
    hidden: false,
    open: false,
    tagName: "DIV",
    style: { display: "" },
    children: [],
    attributes,
    classList: {
      toggle(name, enabled) {
        if (enabled) classes.add(name);
        else classes.delete(name);
      },
      contains(name) {
        return classes.has(name);
      }
    },
    appendChild(child) {
      this.children.push(child);
    },
    setAttribute(name, value) {
      attributes[name] = value;
    },
    addEventListener(name, callback) {
      (events[name] ||= []).push(callback);
    },
    click() {
      for (const callback of events.click || []) {
        callback();
      }
    }
  };
}

const button = element();
const tree = element();
const viewer = element();
const relationship = element();
relationship.tagName = "DETAILS";

const modes = [element(), element(), element()];
const controls = element();

controls.querySelectorAll = () => modes;

const elements = {
  "b3-v810-hierarchy-button": button,
  "b3-v810-hierarchy-view": tree,
  "b3-v5-views": viewer,
  "storage-relationship-v89": relationship
};

const document = {
  readyState: "complete",
  getElementById(id) {
    return elements[id] || null;
  },
  querySelector(selector) {
    return selector === ".b3-v5-controls"
      ? controls : null;
  }
};

const file = path.resolve(
  __dirname,
  "../../static/internal/storage/storage_hierarchy_mode_v810.js"
);

vm.runInNewContext(
  fs.readFileSync(file, "utf8"),
  { document }
);

assert.equal(tree.children[0], relationship);

button.click();

assert.equal(tree.hidden, false);
assert.equal(viewer.hidden, true);
assert.equal(relationship.open, true);
assert.equal(button.attributes["aria-pressed"], "true");

console.log("HIERARCHY_VIEW=PASS");

modes[2].click();

assert.equal(tree.hidden, true);
assert.equal(viewer.hidden, false);
assert.equal(modes[2].attributes["aria-pressed"], "true");
assert.equal(button.attributes["aria-pressed"], "false");

console.log("RETURN_TO_2D=PASS");
console.log("HIERARCHY_MODE_TESTS=PASS");
