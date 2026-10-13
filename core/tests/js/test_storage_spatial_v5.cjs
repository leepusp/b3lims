"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const { test } = require("node:test");

const root = path.resolve(__dirname, "../../static/internal/storage");
const spatialSource = fs.readFileSync(
    path.join(root, "storage_spatial_v5.js"), "utf8"
);
const viewerSource = fs.readFileSync(
    path.join(root, "storage_viewer_3d.js"), "utf8"
);

class Element {
    constructor(tag = "div") {
        this.tagName = tag.toUpperCase();
        this.children = [];
        this.textContent = "";
        this.dataset = {};
        this.style = {};
        this.className = "";
        this.disabled = false;
        this.handlers = new Map();
        this.classes = new Set();
        this.classList = {
            add: value => this.classes.add(value),
            contains: value => this.classes.has(value)
        };
        this.attributes = {};
    }

    replaceChildren(...children) {
        this.children = children;
        this.textContent = "";
    }

    append(...children) {
        this.children.push(...children);
    }

    addEventListener(name, callback) {
        const handlers = this.handlers.get(name) || [];
        handlers.push(callback);
        this.handlers.set(name, handlers);
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    click() {
        for (const callback of this.handlers.get("click") || []) {
            callback();
        }
    }
}

class MockEvent {
    constructor(type, options = {}) {
        this.type = type;
        this.detail = options.detail;
    }
}

function createHarness() {
    const ids = [
        "b3-v5-views",
        "b3-v5-map",
        "b3-v5-samples",
        "b3-v5-detail",
        "b3-v5-summary"
    ];

    const elements = new Map(
        ids.map(id => [id, new Element()])
    );

    const listeners = new Map();
    const emitted = [];

    const controls = ["split", "3d", "2d"].map(view => {
        const element = new Element("button");
        element.dataset.v5View = view;
        return element;
    });

    const document = {
        getElementById: id => elements.get(id) || null,

        createElement: tag => new Element(tag),

        createTextNode: value => ({
            textContent: String(value)
        }),

        querySelectorAll: () => controls,

        addEventListener(type, callback) {
            const handlers = listeners.get(type) || [];
            handlers.push(callback);
            listeners.set(type, handlers);
        },

        dispatchEvent(event) {
            emitted.push(event);

            for (const callback of listeners.get(event.type) || []) {
                callback(event);
            }
        }
    };

    const window = {
        dispatchEvent() {}
    };

    vm.runInNewContext(spatialSource, {
        document,
        window,
        Event: MockEvent,
        CustomEvent: MockEvent
    });

    function publish(samples, mode = "live") {
        document.dispatchEvent(
            new MockEvent("b3-spatial-v5-box", {
                detail: {
                    mode,
                    box: {
                        id: "legacy:box42",
                        name: "Caixa 1.1",
                        path: "Freezer Regina > Caixa 1.1"
                    },
                    samples,
                    picked: null
                }
            })
        );
    }

    return { document, elements, emitted, publish };
}

const sample = {
    id: "42",
    key: "42",
    code: "SAMPLE-42",
    box: "legacy:box42",
    position: "B5",
    status: "active",
    legacy: true,
    url: "/b3lims/samples/42/"
};

test("3D instance index resolves to its corresponding Sample", () => {
    assert.match(
        viewerSource,
        /instanced\.setMatrixAt\(i,\s*dummy\.matrix\)/
    );

    assert.match(
        viewerSource,
        /instanced\.userData\.samples\s*=\s*positions/
    );

    assert.match(
        viewerSource,
        /tube\.object\.userData\.samples\[tube\.instanceId\]/
    );

    assert.match(
        viewerSource,
        /sampleKey\(s\)\s*===\s*pickedSample/
    );
});

test("clicking B5 emits the matching Sample identity", () => {
    const h = createHarness();
    h.publish([sample]);

    const map = h.elements.get("b3-v5-map");

    const b5 = map.children.find(
        element => element.title?.startsWith("B5:")
    );

    assert.ok(b5, "B5 must be displayed");
    assert.equal(b5.disabled, false);

    b5.click();

    const picks = h.emitted.filter(
        event => event.type === "b3-spatial-v5-pick"
    );

    assert.equal(picks.length, 1);
    assert.equal(picks[0].detail.key, "42");
    assert.equal(picks[0].detail.box, "legacy:box42");
    assert.equal(picks[0].detail.mode, "live");

    // draw() replaces the map cells after a selection.
    // Inspect the currently rendered B5 button, not the detached one.
    const currentB5 = h.elements
        .get("b3-v5-map")
        .children.find(
            element => element.title?.startsWith("B5:")
        );

    assert.ok(currentB5, "B5 must remain visible");
    assert.notStrictEqual(currentB5, b5);
    assert.equal(
        currentB5.classList.contains("selected"),
        true
    );

    const detail = h.elements.get("b3-v5-detail");
    const link = detail.children.find(
        element => element.tagName === "A"
    );

    assert.ok(link);
    assert.equal(link.href, sample.url);
});

test("two Samples at one coordinate cannot be selected arbitrarily", () => {
    const h = createHarness();

    h.publish([
        sample,
        {
            ...sample,
            id: "43",
            key: "43",
            code: "SAMPLE-43",
            url: "/b3lims/samples/43/"
        }
    ]);

    const map = h.elements.get("b3-v5-map");
    const b5 = map.children.find(
        element => element.title?.startsWith("B5:")
    );

    assert.ok(b5);
    assert.equal(b5.disabled, true);

    // Both records remain independently accessible through the list.
    const list = h.elements.get("b3-v5-samples");
    assert.equal(list.children.length, 2);
});

test("example mode never exposes a real Sample link", () => {
    const h = createHarness();
    h.publish([sample], "demo");

    const list = h.elements.get("b3-v5-samples");
    list.children[0].click();

    const detail = h.elements.get("b3-v5-detail");

    assert.equal(
        detail.children.some(element => element.tagName === "A"),
        false
    );
});

test("unknown positions never create a fictitious occupied cell", () => {
    const h = createHarness();

    h.publish([{
        ...sample,
        position: "",
        key: "42"
    }]);

    const map = h.elements.get("b3-v5-map");

    assert.equal(
        map.children.some(
            element => element.className === "recorded"
        ),
        false
    );

    const list = h.elements.get("b3-v5-samples");
    assert.equal(list.children.length, 1);
});
