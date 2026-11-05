/* Move Selected to Storage: draw the chosen destination so the person sees
   where each selected Sample will sit. Clicking fills the position boxes;
   the server still validates everything on preview. */
(function () {
  "use strict";

  function canonical(anchor, text) {
    const value = String(text || "").trim();
    if (!value) return "";
    if (anchor.organization === "slots") {
      const wanted = value.replace(/\s+/g, " ").toLowerCase();
      return (anchor.slots || []).find(n => n.toLowerCase() === wanted) || "";
    }
    const m = /^([A-Za-z])0*([1-9][0-9]*)$/.exec(value);
    if (!m) return "";
    const r = m[1].toUpperCase().charCodeAt(0) - 65;
    const c = Number(m[2]);
    return r < anchor.rows && c <= anchor.columns
      ? m[1].toUpperCase() + c : "";
  }

  function names(anchor) {
    if (anchor.organization === "slots") return (anchor.slots || []).slice();
    const out = [];
    for (let r = 0; r < anchor.rows; r++) {
      for (let c = 1; c <= anchor.columns; c++) {
        out.push(String.fromCharCode(65 + r) + c);
      }
    }
    return out;
  }

  if (typeof module !== "undefined") module.exports = {canonical, names};
  if (typeof document === "undefined") return;

  document.addEventListener("DOMContentLoaded", function () {
    const dataNode = document.getElementById("b3-bulk-catalog");
    const select = document.getElementById("bulkStorageDestination");
    const panel = document.getElementById("bulkDrawing");
    const canvas = document.getElementById("bulkDrawingCanvas");
    if (!dataNode || !select || !panel || !canvas) return;

    let catalog = [];
    try { catalog = JSON.parse(dataNode.textContent) || []; } catch (e) {}
    const byId = new Map(catalog.map(item => [String(item.id), item]));
    const inputs = Array.from(
      document.querySelectorAll("input[data-bulk-position]")
    );
    const labels = inputs.map(input =>
      input.closest("tr")?.querySelector("strong")?.textContent || ""
    );

    function anchor() {
      const item = byId.get(select.value);
      return item && item.organization !== "free" ? item : null;
    }

    function mineMap(a) {
      const map = new Map();
      inputs.forEach((input, index) => {
        const name = canonical(a, input.value);
        if (name && !map.has(name)) map.set(name, index);
      });
      return map;
    }

    function usedSet(a) {
      const set = new Set();
      for (const text of a.occupied || []) {
        const name = canonical(a, text);
        if (name) set.add(name);
      }
      return set;
    }

    function validate(a) {
      inputs.forEach(input => {
        const bad = a && input.value.trim() && !canonical(a, input.value);
        input.setCustomValidity(
          bad ? "Not a position of this drawing." : ""
        );
        input.classList.toggle("is-invalid", Boolean(bad));
      });
    }

    function draw() {
      const a = anchor();
      canvas.replaceChildren();
      panel.hidden = !a;
      inputs.forEach(input => {
        input.placeholder = a && a.organization === "slots"
          ? (a.slots[0] || "Compartment")
          : "e.g. B5";
      });
      validate(a);
      if (!a) return;

      const used = usedSet(a);
      const mine = mineMap(a);
      const all = names(a);
      let free = 0;

      const state = name =>
        mine.has(name) ? "is-mine" : used.has(name) ? "is-used" : "";

      if (a.organization === "slots") {
        const box = document.createElement("div");
        box.className = "b3-bk-slots " +
          (a.direction === "row" ? "is-row" : "is-stack");
        for (const name of all) {
          const b = document.createElement("button");
          b.type = "button";
          b.className = "b3-bk-slot " + state(name);
          b.dataset.slot = name;
          b.disabled = used.has(name) && !mine.has(name);
          const strong = document.createElement("strong");
          strong.textContent = name;
          const small = document.createElement("small");
          small.textContent = mine.has(name)
            ? labels[mine.get(name)]
            : used.has(name) ? "occupied" : "free";
          b.append(strong, small);
          box.append(b);
          if (!used.has(name) && !mine.has(name)) free++;
        }
        canvas.append(box);
      } else {
        const grid = document.createElement("div");
        grid.className = "b3-bk-grid";
        grid.style.gridTemplateColumns =
          "22px repeat(" + a.columns + ", 34px)";
        grid.append(document.createElement("span"));
        for (let c = 1; c <= a.columns; c++) {
          const axis = document.createElement("span");
          axis.className = "b3-bk-axis";
          axis.textContent = String(c);
          grid.append(axis);
        }
        for (let r = 0; r < a.rows; r++) {
          const axis = document.createElement("span");
          axis.className = "b3-bk-axis";
          axis.textContent = String.fromCharCode(65 + r);
          grid.append(axis);
          for (let c = 1; c <= a.columns; c++) {
            const name = String.fromCharCode(65 + r) + c;
            const b = document.createElement("button");
            b.type = "button";
            b.className = "b3-bk-cell " + state(name);
            b.dataset.slot = name;
            b.disabled = used.has(name) && !mine.has(name);
            b.title = mine.has(name)
              ? name + ": " + labels[mine.get(name)]
              : name + (used.has(name) ? ": occupied" : ": free");
            if (mine.has(name)) b.textContent = String(mine.get(name) + 1);
            grid.append(b);
            if (!used.has(name) && !mine.has(name)) free++;
          }
        }
        canvas.append(grid);
      }

      document.getElementById("bulkDrawingCount").textContent =
        free + " free of " + all.length + " · " + inputs.length +
        " Sample" + (inputs.length === 1 ? "" : "s") + " to place";
    }

    canvas.addEventListener("click", event => {
      const target = event.target.closest("[data-slot]");
      const a = anchor();
      if (!target || !a || target.disabled) return;
      const name = target.dataset.slot;
      const mine = mineMap(a);
      if (mine.has(name)) {
        inputs[mine.get(name)].value = "";
      } else {
        const next = inputs.find(input => !canonical(a, input.value));
        if (!next) return;
        next.value = name;
      }
      draw();
    });

    document.getElementById("bulkAutoFill")?.addEventListener("click", () => {
      const a = anchor();
      if (!a) return;
      const used = usedSet(a);
      const taken = new Set(
        inputs.map(input => canonical(a, input.value)).filter(Boolean)
      );
      const pool = names(a).filter(n => !used.has(n) && !taken.has(n));
      for (const input of inputs) {
        if (canonical(a, input.value)) continue;
        const name = pool.shift();
        if (name) input.value = name;
      }
      draw();
    });

    document.getElementById("bulkClear")?.addEventListener("click", () => {
      inputs.forEach(input => { input.value = ""; });
      draw();
    });

    select.addEventListener("change", draw);
    inputs.forEach(input => input.addEventListener("input", draw));
    draw();
  });
}());
