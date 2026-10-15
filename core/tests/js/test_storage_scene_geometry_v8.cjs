const test = require("node:test");
const assert = require("node:assert/strict");

const {plan, profile} = require(
    "../../static/internal/storage/storage_scene_geometry_v8.js"
);

const nodes = [
    {
        id: "1",
        parent: null,
        name: "Refrigerator A",
        geometryProfile: "cabinet"
    },
    {
        id: "2",
        parent: "1",
        name: "Shelf 2",
        geometryProfile: "shelves"
    },
    {
        id: "3",
        parent: "2",
        name: "Rack 4",
        geometryProfile: "rack"
    },
    {
        id: "4",
        parent: "3",
        name: "Box A",
        geometryProfile: "grid"
    }
];

test("cabinet scene starts at its registered root", () => {
    const result = plan(nodes);

    assert.equal(result.node.id, "1");
    assert.equal(result.profile, "cabinet");
    assert.equal(result.children[0].node.id, "2");
    assert.equal(result.children[0].profile, "shelves");
});

test("shelf is independently navigable", () => {
    const result = plan(nodes, "2");

    assert.equal(result.profile, "shelves");
    assert.equal(result.children[0].profile, "rack");
});

test("rack exposes registered box child", () => {
    const result = plan(nodes, "3");

    assert.equal(result.profile, "rack");
    assert.equal(result.children[0].profile, "grid");
});

test("box can be drawn as an independent scene", () => {
    const result = plan([
        {
            id: "4",
            parent: null,
            name: "Box A",
            geometryProfile: "grid"
        }
    ]);

    assert.equal(result.profile, "grid");
    assert.equal(result.totalChildren, 0);
    assert.equal(result.capacityKnown, false);
});

test("geometry overrides do not change physical type", () => {
    const node = {
        id: "7",
        kind: "rack",
        geometryProfile: "cabinet"
    };

    assert.equal(profile(node), "cabinet");
    assert.equal(node.kind, "rack");
});

test("unknown geometry has a safe fallback", () => {
    assert.equal(
        profile({geometryProfile: "unsupported"}),
        "generic"
    );
});

test("display limit never creates fake children", () => {
    const many = [
        {
            id: "1",
            parent: null,
            name: "Storage",
            geometryProfile: "space"
        },
        ...Array.from({length: 17}, (_, i) => ({
            id: String(i + 2),
            parent: "1",
            name: `Registered ${i + 1}`,
            geometryProfile: "generic"
        }))
    ];

    const result = plan(many, null, 12);

    assert.equal(result.children.length, 12);
    assert.equal(result.totalChildren, 17);
    assert.equal(result.hiddenChildren, 5);
});

test("planning never modifies location records", () => {
    const before = JSON.stringify(nodes);

    plan(nodes, "2");

    assert.equal(JSON.stringify(nodes), before);
});

test("invalid scene hierarchy is rejected", () => {
    assert.throws(
        () => plan([
            {id: "1", parent: null},
            {id: "2", parent: null}
        ]),
        /exactly one root/
    );
});
