(() => {
  "use strict";

  const MAX_SLOTS = 40;

  // Default compartment names: "Door 1", "Door 2", ...
  function slotNames(word, count) {
    const label = String(word || "").trim() || "Slot";
    const total = Math.max(0, Math.min(MAX_SLOTS, Number(count) || 0));
    const names = [];

    for (let i = 1; i <= total; i++) names.push(label + " " + i);

    return names;
  }

  // Keep what the person already renamed when the count changes.
  function resizeNames(current, word, count) {
    const defaults = slotNames(word, count);

    return defaults.map((name, i) =>
      i < current.length && current[i] ? current[i] : name
    );
  }

  // Rename only the names that are still the automatic ones.
  function rewordNames(current, oldWord, newWord) {
    const before = slotNames(oldWord, current.length);
    const after = slotNames(newWord, current.length);

    return current.map((name, i) =>
      name === before[i] ? after[i] : name
    );
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {slotNames, resizeNames, rewordNames};
  }

  if (typeof document === "undefined") return;

  function el(tag, className, text) {
    const node = document.createElement(tag);

    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;

    return node;
  }

  function initialize() {
    const form = document.getElementById("b3s-location-form");
    const organization = document.getElementById("b3s-c3-organization");
    const dimensions = document.getElementById("b3s-c3-dimensions");
    const rows = document.getElementById("b3s-c3-rows");
    const columns = document.getElementById("b3s-c3-columns");
    const capacity = document.getElementById("b3s-c3-capacity");
    const slotsBox = document.getElementById("b3s-c3-slots");
    const slotWord = document.getElementById("b3s-c3-slot-word");
    const slotCount = document.getElementById("b3s-c3-slot-count");
    const slotDirection = document.getElementById(
      "b3s-c3-slot-direction"
    );
    const slotNamesHost = document.getElementById("b3s-c3-slot-names");
    const preview = document.getElementById("b3s-c3-preview");

    if (
      !form || !organization || !dimensions || !rows || !columns ||
      !capacity || !slotsBox || !slotWord || !slotCount ||
      !slotDirection || !slotNamesHost || !preview
    ) return;

    let names = slotNames(slotWord.value, slotCount.value);
    let lastWord = slotWord.value;

    function drawGrid(r, c) {
      preview.replaceChildren();

      if (!(r >= 1 && r <= 26 && c >= 1 && c <= 24)) return;

      const box = el("div", "b3s-c3-pv-box");
      const grid = el("div", "b3s-c3-pv-grid");
      const size = Math.max(10, Math.min(26, Math.floor(300 / c)));

      grid.style.gridTemplateColumns =
        `18px repeat(${c}, ${size}px)`;
      grid.append(el("span"));

      for (let col = 1; col <= c; col++) {
        grid.append(el("span", "b3s-c3-pv-axis", size >= 14 ? col : ""));
      }

      for (let row = 0; row < r; row++) {
        grid.append(
          el("span", "b3s-c3-pv-axis", String.fromCharCode(65 + row))
        );

        for (let col = 0; col < c; col++) {
          const cell = el("span", "b3s-c3-pv-cell");

          cell.style.width = cell.style.height = size + "px";
          cell.title = String.fromCharCode(65 + row) + (col + 1);
          grid.append(cell);
        }
      }

      box.append(grid);
      preview.append(box);
    }

    function drawSlots() {
      preview.replaceChildren();
      slotNamesHost.replaceChildren();

      const stacked = slotDirection.value !== "row";
      const cabinet = el(
        "div",
        "b3s-c3-pv-cabinet " + (stacked ? "is-stack" : "is-row")
      );

      names.forEach((name, index) => {
        const tile = el("label", "b3s-c3-pv-slot");
        const input = document.createElement("input");

        input.type = "text";
        input.name = "slot_label";
        input.value = name;
        input.maxLength = 40;
        input.required = true;
        input.setAttribute("aria-label", "Compartment " + (index + 1));
        input.addEventListener("input", () => {
          names[index] = input.value;
          summarise();
        });

        tile.append(input);
        cabinet.append(tile);
      });

      preview.append(cabinet);
    }

    function summarise() {
      const mode = organization.value;

      if (mode === "grid") {
        const r = Number(rows.value);
        const c = Number(columns.value);

        capacity.textContent =
          Number.isInteger(r) && Number.isInteger(c) &&
          r >= 1 && r <= 26 && c >= 1 && c <= 24
            ? `${r} rows × ${c} columns = ${r * c} positions ` +
              `(A1 to ${String.fromCharCode(64 + r)}${c}).`
            : "Enter valid dimensions to calculate capacity.";
        return;
      }

      if (mode === "slots") {
        const filled = names.map(n => n.trim().toLowerCase());
        const repeated = filled.length !== new Set(filled).size;

        capacity.textContent = repeated
          ? "Two compartments have the same name."
          : `${names.length} compartment(s): ` +
            "each one can hold what you register there.";
        return;
      }

      capacity.textContent =
        "A single place. It can still contain other locations.";
    }

    function refresh() {
      const mode = organization.value;
      const grid = mode === "grid";
      const slots = mode === "slots";

      dimensions.hidden = !grid;
      slotsBox.hidden = !slots;

      for (const field of [rows, columns]) {
        field.disabled = !grid;
        field.required = grid;
      }

      slotDirection.disabled = !slots;

      if (grid) {
        drawGrid(Number(rows.value), Number(columns.value));
      } else if (slots) {
        drawSlots();
      } else {
        preview.replaceChildren();
      }

      summarise();
    }

    organization.addEventListener("change", refresh);
    rows.addEventListener("input", refresh);
    columns.addEventListener("input", refresh);
    slotDirection.addEventListener("change", refresh);

    slotCount.addEventListener("input", () => {
      const count = Number(slotCount.value);

      if (!Number.isInteger(count) || count < 1 || count > MAX_SLOTS) {
        return;
      }

      names = resizeNames(names, slotWord.value, count);
      refresh();
    });

    slotWord.addEventListener("input", () => {
      names = rewordNames(names, lastWord, slotWord.value);
      lastWord = slotWord.value;
      refresh();
    });

    refresh();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, {once: true});
  } else {
    initialize();
  }
})();
