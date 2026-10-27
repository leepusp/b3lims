(() => {
  "use strict";

  function initialize() {
    const form = document.getElementById("b3s-location-form");
    const organization = document.getElementById(
      "b3s-c3-organization"
    );
    const dimensions = document.getElementById(
      "b3s-c3-dimensions"
    );
    const rows = document.getElementById("b3s-c3-rows");
    const columns = document.getElementById("b3s-c3-columns");
    const capacity = document.getElementById(
      "b3s-c3-capacity"
    );

    if (
      !form || !organization || !dimensions ||
      !rows || !columns || !capacity
    ) return;

    function refresh() {
      const grid = organization.value === "grid";

      dimensions.hidden = !grid;

      for (const field of [rows, columns]) {
        field.disabled = !grid;
        field.required = grid;
      }

      if (!grid) {
        capacity.textContent =
          "No fixed position capacity. " +
          "This location may contain child locations.";
        return;
      }

      const r = Number(rows.value);
      const c = Number(columns.value);

      if (
        Number.isInteger(r) &&
        Number.isInteger(c) &&
        r >= 1 && r <= 26 &&
        c >= 1 && c <= 24
      ) {
        capacity.textContent =
          `${r} rows × ${c} columns = ${r * c} positions.`;
      } else {
        capacity.textContent =
          "Enter valid dimensions to calculate capacity.";
      }
    }

    organization.addEventListener("change", refresh);
    rows.addEventListener("input", refresh);
    columns.addEventListener("input", refresh);

    refresh();
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded", initialize, {once: true}
    );
  } else {
    initialize();
  }
})();
