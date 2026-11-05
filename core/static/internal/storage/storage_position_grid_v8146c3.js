(() => {
  "use strict";

  function buildPositionMap(rows, columns, assignments) {
    if (
      !Number.isInteger(rows) ||
      !Number.isInteger(columns) ||
      rows < 1 || rows > 26 ||
      columns < 1 || columns > 24
    ) {
      throw new RangeError("Invalid storage grid dimensions");
    }

    const occupied = new Map();
    const outside = [];

    for (const item of assignments) {
      const raw = String(item.position || "").trim();
      const code = raw.toUpperCase();
      const match = /^([A-Z])0*([1-9][0-9]*)$/.exec(code);

      if (!match) {
        outside.push(item);
        continue;
      }

      const row = match[1].charCodeAt(0) - 65;
      const column = Number(match[2]) - 1;

      if (row >= rows || column >= columns) {
        outside.push(item);
        continue;
      }

      const canonical = match[1] + (column + 1);

      if (!occupied.has(canonical)) {
        occupied.set(canonical, []);
      }

      occupied.get(canonical).push(item);
    }

    const slots = [];

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < columns; c++) {
        const name = String.fromCharCode(65 + r) + (c + 1);

        slots.push({
          name,
          row: r,
          column: c,
          assignments: occupied.get(name) || []
        });
      }
    }

    return {
      rows,
      columns,
      capacity: rows * columns,
      occupiedSlots: occupied.size,
      slots,
      outside
    };
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {buildPositionMap};
  }

  if (typeof document === "undefined") return;

  const EVENT = "b3:storage-v814-contents-rendered";

  function element(tag, text, className) {
    const node = document.createElement(tag);

    if (text !== null && text !== undefined) {
      node.textContent = String(text);
    }

    if (className) node.className = className;

    return node;
  }

  function appendSampleList(host, items) {
    const list = element("ul", null, "b3s-c3-sample-list");

    for (const item of items) {
      const li = document.createElement("li");
      const link = element("a", item.sample);

      link.href = item.url;
      li.append(link);

      if (item.position) {
        li.append(
          element("span", " · " + item.position)
        );
      }

      list.append(li);
    }

    host.append(list);
  }

  function renderGrid(locationId) {
    const host = document.getElementById("b3s-position-map");
    const locationSource = document.getElementById(
      "b3s-location-data"
    );
    const sampleSource = document.getElementById(
      "b3s-sample-data"
    );

    if (
      !host ||
      !locationSource?.content ||
      !sampleSource?.content
    ) return;

    // Preserve the existing Storage renderer.
    host.querySelector("#b3s-c3-visual")?.remove();

    if (!locationId) return;

    const locations = Array.from(
      locationSource.content.querySelectorAll("[data-id]")
    );

    const location = locations.find(
      item => item.dataset.id === String(locationId)
    );

    if (
      !location ||
      location.dataset.c3Organization !== "grid"
    ) return;

    const rows = Number(location.dataset.c3Rows);
    const columns = Number(location.dataset.c3Columns);

    if (
      !Number.isInteger(rows) ||
      !Number.isInteger(columns) ||
      rows < 1 || rows > 26 ||
      columns < 1 || columns > 24
    ) return;

    const assignments = Array.from(
      sampleSource.content.querySelectorAll("[data-id]")
    ).filter(
      item => item.dataset.location === String(locationId)
    ).map(item => ({
      id: item.dataset.id,
      position: item.dataset.position || "",
      sample: item.dataset.sample || "",
      url: item.dataset.url || ""
    }));

    const model = buildPositionMap(
      rows, columns, assignments
    );

    const visual = element(
      "section", null, "b3s-c3-visual"
    );
    visual.id = "b3s-c3-visual";

    const heading = element(
      "h4", "Position map", "b3s-c3-heading"
    );

    const summary = element(
      "p",
      `${rows} × ${columns} · ` +
      `${model.capacity} positions · ` +
      `${model.occupiedSlots} with recorded occupancy`,
      "b3s-c3-summary"
    );

    visual.append(heading, summary);

    if (location.dataset.c3Temperature) {
      visual.append(
        element(
          "p",
          "Temperature: " + location.dataset.c3Temperature,
          "b3s-c3-summary"
        )
      );
    }

    const split = element("div", null, "b3s-c3-split");
    const scroll = element("div", null, "b3s-c3-scroll");
    const grid = element("div", null, "b3s-c3-grid");

    grid.style.gridTemplateColumns =
      `36px repeat(${columns}, 36px)`;

    grid.append(element("span"));

    for (let col = 1; col <= columns; col++) {
      grid.append(
        element("span", col, "b3s-c3-grid-label")
      );
    }

    const detail = element(
      "aside", null, "b3s-c3-detail"
    );

    detail.append(
      element("h5", "Position details"),
      element(
        "p",
        "Select a position to inspect its recorded Sample.",
        "b3s-c3-note"
      )
    );

    function showPosition(slot) {
      detail.replaceChildren();

      detail.append(
        element("h5", "Position " + slot.name)
      );

      if (!slot.assignments.length) {
        detail.append(
          element(
            "p",
            "No active Sample assignment is recorded here. " +
            "Availability must still be validated when saving.",
            "b3s-c3-note"
          )
        );
        return;
      }

      detail.append(
        element(
          "p",
          `${slot.assignments.length} recorded assignment(s).`,
          "b3s-c3-note"
        )
      );

      appendSampleList(detail, slot.assignments);
    }

    for (let row = 0; row < rows; row++) {
      grid.append(
        element(
          "span",
          String.fromCharCode(65 + row),
          "b3s-c3-grid-label"
        )
      );

      for (let col = 0; col < columns; col++) {
        const slot = model.slots[row * columns + col];
        const occupied = slot.assignments.length > 0;

        const button = element(
          "button",
          slot.name,
          "b3s-c3-slot " +
          (occupied ? "b3s-c3-occupied" : "b3s-c3-unrecorded")
        );

        button.type = "button";

        if (slot.assignments.length > 1) {
          button.classList.add("b3s-c3-conflict");
        }

        button.setAttribute(
          "aria-label",
          slot.name + (
            occupied
              ? `: ${slot.assignments.length} recorded Sample(s)`
              : ": no recorded occupancy"
          )
        );

        button.addEventListener(
          "click", () => showPosition(slot)
        );

        grid.append(button);
      }
    }

    scroll.append(grid);
    split.append(scroll, detail);
    visual.append(split);

    const legend = element(
      "p",
      "Blue: recorded occupancy. " +
      "Outlined: no occupancy recorded. " +
      "This view does not reserve or move Samples.",
      "b3s-c3-note"
    );

    visual.append(legend);

    if (model.outside.length) {
      const warning = element(
        "div", null, "b3s-c3-outside"
      );

      warning.append(
        element(
          "h5",
          "Assignments outside the configured grid"
        ),
        element(
          "p",
          "These existing records were preserved. " +
          "They are not automatically moved or renamed.",
          "b3s-c3-note"
        )
      );

      appendSampleList(warning, model.outside);
      visual.append(warning);
    }

    host.append(visual);
  }

  // Register immediately: the original Storage component
  // may initialize during DOMContentLoaded.
  document.addEventListener(EVENT, event => {
    renderGrid(event.detail?.locationId || "");
  });
})();
