"use strict";

const assert = require("node:assert/strict");

const {
  buildPositionMap
} = require(
  "../../static/internal/storage/storage_position_grid_v8146c3.js"
);

const model = buildPositionMap(3, 4, [
  {
    sample: "SAMPLE-1",
    position: "A1",
    url: "/samples/1/"
  },
  {
    sample: "SAMPLE-2",
    position: "b2",
    url: "/samples/2/"
  },
  {
    sample: "SAMPLE-3",
    position: "posição azul",
    url: "/samples/3/"
  },
  {
    sample: "SAMPLE-4",
    position: "Z99",
    url: "/samples/4/"
  }
]);

assert.equal(model.capacity, 12);
assert.equal(model.slots.length, 12);
assert.equal(model.occupiedSlots, 2);
assert.equal(model.outside.length, 2);

assert.deepEqual(
  model.slots
    .filter(slot => slot.assignments.length)
    .map(slot => slot.name),
  ["A1", "B2"]
);

assert.equal(
  buildPositionMap(9, 9, []).capacity,
  81
);

assert.equal(
  buildPositionMap(8, 12, []).capacity,
  96
);

assert.throws(
  () => buildPositionMap(27, 9, []),
  RangeError
);

assert.throws(
  () => buildPositionMap(9, 25, []),
  RangeError
);

const conflict = buildPositionMap(1, 1, [
  {position: "A1", sample: "ONE"},
  {position: "a1", sample: "TWO"}
]);

assert.equal(conflict.occupiedSlots, 1);
assert.equal(conflict.slots[0].assignments.length, 2);

console.log("C3C_POSITION_GRID_BEHAVIOR=PASS");
console.log("C3C_CAPACITY_9X9=81");
console.log("C3C_UNKNOWN_POSITION_PRESERVATION=PASS");
console.log("C3C_DUPLICATE_OCCUPANCY_VISIBILITY=PASS");
