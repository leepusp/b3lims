const test = require("node:test");
const assert = require("node:assert/strict");

const {scope} = require(
    "../../static/internal/storage/storage_scene_filter_v8.js"
);

const nodes = [
    {id: "10", parent: null, name: "Freezer Regina"},
    {id: "11", parent: "10", name: "Caixa 1.1"},
    {id: "20", parent: null, name: "Freezer Chuck"},
    {id: "21", parent: "20", name: "Caixa 1.2"}
];

const samples = [
    {id: "46", box: "11", position: "B5"},
    {id: "47", box: "21", position: "B5"}
];

function projection(root, ids) {
    return {
        scene_root_id: root,
        read_only: true,
        nodes: ids.map(id => ({
            id,
            geometry_profile: id === root ? "cabinet" : "grid"
        }))
    };
}

test("selected freezer scopes nodes and Samples", () => {
    const result = scope(
        nodes,
        samples,
        projection(10, [10, 11])
    );

    assert.deepEqual(
        result.nodes.map(item => item.name),
        ["Freezer Regina", "Caixa 1.1"]
    );

    assert.equal(result.samples.length, 1);
    assert.equal(result.samples[0].id, "46");
    assert.equal(result.nodes[0].geometryProfile, "cabinet");
});

test("nested box can be an independent scene root", () => {
    const result = scope(
        nodes,
        samples,
        projection(11, [11])
    );

    assert.equal(result.nodes.length, 1);
    assert.equal(result.nodes[0].parent, null);
    assert.equal(result.samples[0].position, "B5");

    // Original physical parent must remain untouched.
    assert.equal(nodes[1].parent, "10");
});

test("another freezer never enters the selected scene", () => {
    const result = scope(
        nodes,
        samples,
        projection(20, [20, 21])
    );

    assert.deepEqual(
        result.samples.map(item => item.id),
        ["47"]
    );
});

test("incomplete scene data is rejected", () => {
    assert.throws(
        () => scope(
            nodes,
            samples,
            projection(10, [10, 999])
        ),
        /does not match/
    );
});

test("unrelated parent links are rejected", () => {
    assert.throws(
        () => scope(
            nodes,
            samples,
            projection(11, [11, 10])
        ),
        /incomplete hierarchy/
    );
});

test("source data is not mutated", () => {
    const before = JSON.stringify({nodes, samples});

    scope(nodes, samples, projection(10, [10, 11]));

    assert.equal(
        JSON.stringify({nodes, samples}),
        before
    );
});
