/* Where this Sample sits: the drawing of its location with its own
   position highlighted. Read-only; moving goes through Storage. */
(function () {
  "use strict";

  function canonical(entry, text) {
    const value = String(text || "").trim();
    if (!value) return "";
    if (entry.organization === "slots") {
      const wanted = value.replace(/\s+/g, " ").toLowerCase();
      return (entry.slots || []).find(n => n.toLowerCase() === wanted) || "";
    }
    const m = /^([A-Za-z])0*([1-9][0-9]*)$/.exec(value);
    if (!m) return "";
    const r = m[1].toUpperCase().charCodeAt(0) - 65;
    const c = Number(m[2]);
    return r < entry.rows && c <= entry.columns
      ? m[1].toUpperCase() + c : "";
  }

  if (typeof module !== "undefined") module.exports = {canonical};
  if (typeof document === "undefined") return;

  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  function draw(entry, storageUrl) {
    const card = el("section", "", "b3-sd-card");
    const head = el("div", "", "b3-sd-head");
    head.append(el("strong", entry.path));
    if (entry.position) head.append(el("small", "Position " + entry.position));
    if (entry.primary) head.append(el("small", "Primary"));
    const legend = el("span", "", "b3-sd-legend");
    legend.setAttribute("aria-hidden", "true");
    legend.append(
      el("i", "", "b3-sd-key"), document.createTextNode(" free"),
      el("i", "", "b3-sd-key is-other"), document.createTextNode(" other Samples"),
      el("i", "", "b3-sd-key is-mine"), document.createTextNode(" this Sample")
    );
    head.append(legend);
    card.append(head);

    const mine = canonical(entry, entry.position);
    const others = new Set(
      (entry.others || []).map(v => canonical(entry, v)).filter(Boolean)
    );
    const canvas = el("div", "", "b3-sd-canvas");

    const state = name => name === mine ? "is-mine" : others.has(name) ? "is-other" : "";

    if (entry.organization === "slots") {
      const box = el("div", "", "b3-sd-slots " + (entry.direction === "row" ? "is-row" : "is-stack"));
      for (const name of entry.slots) {
        const tile = el("div", "", "b3-sd-slot " + state(name));
        tile.append(el("strong", name));
        tile.append(el("small", name === mine ? "this Sample" : others.has(name) ? "occupied" : "free"));
        box.append(tile);
      }
      canvas.append(box);
    } else {
      const size = Math.max(12, Math.min(24, Math.floor(420 / entry.columns)));
      const grid = el("div", "", "b3-sd-grid");
      grid.style.gridTemplateColumns = "16px repeat(" + entry.columns + ", " + size + "px)";
      grid.append(el("span"));
      for (let c = 1; c <= entry.columns; c++) {
        grid.append(el("span", size >= 16 ? String(c) : "", "b3-sd-axis"));
      }
      for (let r = 0; r < entry.rows; r++) {
        grid.append(el("span", String.fromCharCode(65 + r), "b3-sd-axis"));
        for (let c = 1; c <= entry.columns; c++) {
          const name = String.fromCharCode(65 + r) + c;
          const cell = el("i", "", "b3-sd-cell " + state(name));
          cell.style.width = cell.style.height = size + "px";
          cell.title = name + (name === mine ? " (this Sample)" : others.has(name) ? " (occupied)" : " (free)");
          grid.append(cell);
        }
      }
      canvas.append(grid);
    }
    card.append(canvas);

    const actions = el("div", "", "b3-sd-actions");
    const open = el("a", "Open in Storage", "btn btn-sm btn-outline-secondary");
    open.href = storageUrl + "?location=" + encodeURIComponent(entry.location_id);
    actions.append(open);
    if (entry.can_move) {
      const move = el("a", "Move this Sample…", "btn btn-sm btn-outline-primary");
      move.href = storageUrl + "?move_assignment=" + encodeURIComponent(entry.assignment_id);
      actions.append(move);
    }
    card.append(actions);
    return card;
  }

  document.addEventListener("DOMContentLoaded", function () {
    const host = document.getElementById("b3SampleDrawings");
    const data = document.getElementById("b3-sample-drawings");
    if (!host || !data) return;
    let entries = [];
    try { entries = JSON.parse(data.textContent) || []; } catch (e) {}
    const storageUrl = host.dataset.storageUrl || "/storage/";
    for (const entry of entries) {
      if (!["grid", "slots"].includes(entry.organization)) continue;
      host.append(draw(entry, storageUrl));
    }
  });
}());
