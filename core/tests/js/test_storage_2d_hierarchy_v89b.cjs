"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const spatial = fs.readFileSync(
  "core/static/internal/storage/storage_spatial_v5.js",
  "utf8"
);

const hierarchy = fs.readFileSync(
  "core/static/internal/storage/storage_2d_hierarchy_v89b.js",
  "utf8"
);

class Element {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.listeners = new Map();
    this.attributes = new Map();
    this.dataset = {};
    this.style = {};
    this.textContent = "";
    this.className = "";
    this.hidden = false;
    this.disabled = false;
    this.parentNode = null;

    this.classList = {
      add: name => {
        this.className += ` ${name}`;
      }
    };
  }

  append(...elements) {
    for (const item of elements) {
      item.parentNode = this;
      this.children.push(item);
    }
  }

  prepend(...elements) {
    for (const item of elements.reverse()) {
      item.parentNode = this;
      this.children.unshift(item);
    }
  }

  insertBefore(item, reference) {
    const index = this.children.indexOf(reference);

    if (index < 0) {
      this.append(item);
      return;
    }

    item.parentNode = this;
    this.children.splice(index, 0, item);
  }

  replaceChildren(...elements) {
    this.children = [];
    this.textContent = "";
    this.append(...elements);
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  addEventListener(name, callback) {
    const callbacks = this.listeners.get(name) || [];
    callbacks.push(callback);
    this.listeners.set(name, callbacks);
  }

  click() {
    if (this.disabled) return;

    for (const callback of this.listeners.get("click") || []) {
      callback({target: this});
    }
  }
}

function createHarness({physical = false} = {}) {
  const events = [];
  const listeners = new Map();

  const host = new Element();
  const aside = new Element();
  const summary = new Element();
  const map = new Element();
  const list = new Element();
  const detail = new Element();

  aside.append(summary, map, list, detail);
  host.querySelector = selector =>
    selector === ".b3-v5-two" ? aside : null;

  const historical = {
    nodes: [
      {
        id: "legacy:chuck",
        parent: null,
        name: "Freezer Chuck",
        kind: "freezer",
        type: "Freezer",
        legacy: true
      },
      {
        id: "legacy:box12",
        parent: "legacy:chuck",
        name: "Caixa 1.2",
        kind: "box",
        type: "Box",
        legacy: true
      },
      {
        id: "legacy:regina",
        parent: null,
        name: "Freezer Regina",
        kind: "freezer",
        type: "Freezer",
        legacy: true
      },
      {
        id: "legacy:box11",
        parent: "legacy:regina",
        name: "Caixa 1.1",
        kind: "box",
        type: "Box",
        legacy: true
      }
    ],
    samples: [
      {
        id: 47,
        box: "legacy:box12",
        code: "BAC-2026-8531_1.2",
        position: "B5",
        status: "active",
        legacy: true
      },
      {
        id: 46,
        box: "legacy:box11",
        code: "BAC-2026-8531_1.1",
        position: "B5",
        status: "active",
        legacy: true
      }
    ]
  };

  const physicalLocations = physical
    ? [
        {
          dataset: {
            locationId: "10",
            parentId: "",
            locationName: "Freezer Test",
            locationKind: "freezer",
            locationType: "Freezer"
          }
        },
        {
          dataset: {
            locationId: "11",
            parentId: "10",
            locationName: "Box Test",
            locationKind: "box",
            locationType: "Box"
          }
        }
      ]
    : [];

  const source = {
    content: {
      querySelectorAll(selector) {
        if (selector === "[data-location-id]") {
          return physicalLocations;
        }
        if (selector === "[data-assignment-location]") {
          return [];
        }
        return [];
      }
    }
  };

  const realButton = new Element("button");
  const demoButton = new Element("button");

  realButton.setAttribute("aria-pressed", "true");
  demoButton.setAttribute("aria-pressed", "false");

  const elements = {
    "b3-v5-views": host,
    "b3-v5-map": map,
    "b3-v5-samples": list,
    "b3-v5-detail": detail,
    "b3-v5-summary": summary,
    "storage-explorer-data": source,
    "storage-legacy-projection": {
      textContent: JSON.stringify(historical)
    },
    "storage-3d-real": realButton,
    "storage-3d-example": demoButton
  };

  const document = {
    getElementById(id) {
      return elements[id] || null;
    },

    createElement(tag) {
      return new Element(tag);
    },

    createTextNode(value) {
      const node = new Element("#text");
      node.textContent = String(value);
      return node;
    },

    querySelectorAll() {
      return [];
    },

    addEventListener(name, callback) {
      const callbacks = listeners.get(name) || [];
      callbacks.push(callback);
      listeners.set(name, callbacks);
    },

    dispatchEvent(event) {
      events.push(event);

      for (const callback of listeners.get(event.type) || []) {
        callback(event);
      }

      return true;
    }
  };

  class CustomEvent {
    constructor(type, options = {}) {
      this.type = type;
      this.detail = options.detail;
    }
  }

  const context = {
    document,
    CustomEvent,
    window: {
      requestAnimationFrame(callback) {
        callback();
      },
      dispatchEvent() {}
    },
    console
  };

  // The 3D controller is deliberately not loaded.
  vm.runInNewContext(spatial, context);
  vm.runInNewContext(hierarchy, context);

  const nav = aside.children.find(
    item => item.id === "b3-v89b-2d-navigation"
  );

  assert.ok(nav, "Independent 2D navigation must exist");

  function clickChoice(label) {
    const choices = nav.children[2];

    const button = choices.children.find(
      item => item.textContent.includes(label)
    );

    assert.ok(button, `Missing 2D choice: ${label}`);
    button.click();
  }

  function overview() {
    const breadcrumbs = nav.children[1];
    const button = breadcrumbs.children.find(
      item => item.textContent === "Overview"
    );

    assert.ok(button);
    button.click();
  }

  return {
    nav,
    map,
    list,
    detail,
    summary,
    events,
    clickChoice,
    overview,
    demoButton,
    realButton,
    document
  };
}

function allText(node) {
  return [
    node.textContent,
    ...node.children.map(allText)
  ].join(" ");
}

function recordedB5(harness) {
  const button = harness.map.children.find(
    item =>
      item.tagName === "BUTTON" &&
      String(item.title || "").startsWith("B5:")
  );

  assert.ok(button, "Recorded B5 cell not rendered");
  return button;
}

test("2D loads both historical freezers without 3D", () => {
  const h = createHarness();

  const text = allText(h.nav);

  assert.match(text, /Freezer Chuck/);
  assert.match(text, /Freezer Regina/);
  assert.equal(h.nav.hidden, false);
});

test("Chuck -> Caixa 1.2 -> B5 -> Sample", () => {
  const h = createHarness();

  h.clickChoice("Freezer Chuck");
  h.clickChoice("Caixa 1.2");

  assert.match(
    h.summary.textContent,
    /Caixa 1\.2/
  );

  recordedB5(h).click();

  assert.match(
    allText(h.detail),
    /BAC-2026-8531_1\.2/
  );

  assert.ok(
    h.events.some(
      event =>
        event.type === "b3-spatial-v5-pick" &&
        String(event.detail?.key) === "47"
    )
  );
});

test("navigation switches independently to Regina", () => {
  const h = createHarness();

  h.clickChoice("Freezer Chuck");
  h.clickChoice("Caixa 1.2");

  h.overview();

  h.clickChoice("Freezer Regina");
  h.clickChoice("Caixa 1.1");

  recordedB5(h).click();

  assert.match(
    allText(h.detail),
    /BAC-2026-8531_1\.1/
  );

  assert.doesNotMatch(
    allText(h.list),
    /BAC-2026-8531_1\.2/
  );
});

test("historical nodes never request physical selection", () => {
  const h = createHarness();

  h.clickChoice("Freezer Chuck");
  h.clickChoice("Caixa 1.2");

  assert.equal(
    h.events.filter(
      event => event.type === "b3-storage-select-request"
    ).length,
    0
  );

  assert.ok(
    h.events.some(
      event =>
        event.type === "b3-storage-2d-navigate" &&
        event.detail?.id === "legacy:box12"
    )
  );
});

test("registered physical locations retain explorer sync", () => {
  const h = createHarness({physical: true});

  h.clickChoice("Freezer Test");
  h.clickChoice("Box Test");

  const requests = h.events
    .filter(
      event => event.type === "b3-storage-select-request"
    )
    .map(event => event.detail.id);

  assert.equal(JSON.stringify(requests), '["10","11"]');
});

test("demo mode suppresses live navigation", () => {
  const h = createHarness();

  h.demoButton.setAttribute("aria-pressed", "true");
  h.realButton.setAttribute("aria-pressed", "false");
  h.demoButton.click();

  assert.equal(h.nav.hidden, true);

  const before = h.events.length;

  h.clickChoice("Freezer Chuck");

  const newEvents = h.events.slice(before);

  assert.ok(
    !newEvents.some(event =>
      event.type === "b3-storage-2d-navigate" ||
      event.type === "b3-storage-select-request"
    )
  );
});
