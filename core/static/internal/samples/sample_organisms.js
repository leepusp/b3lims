(function () {
    "use strict";

    const root = document.getElementById("organismsSection");

    if (!root) return;

    const $ = (id) => document.getElementById(id);
    const ROLES = [["primary", "Main organism"], ["member", "Member"], ["host", "Host"], ["associated", "Associated"]];
    const typeInput = root.dataset.typeInput ? document.getElementById(root.dataset.typeInput) : null;
    let rows = [];
    let timer = null;
    let serial = 0;
    let available = true;

    try {
        rows = JSON.parse($("organisms-initial").textContent || "[]");

        if (typeof rows === "string") rows = JSON.parse(rows || "[]");
    } catch (e) { rows = []; }

    if (!Array.isArray(rows)) rows = [];

    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
    const sampleType = () => (typeInput ? typeInput.value : root.dataset.type) || "";

    function sync() {
        $("organismsJson").value = JSON.stringify(rows.map((r) => ({
            role: r.role, name: r.name, strain: r.strain || "", taxid: r.taxid || "", notes: r.notes || "",
        })));
    }

    function badge(r) {
        return r.taxid
            ? "<span class='badge text-bg-light border'>" + esc((r.source || "ncbi").toUpperCase()) + " · taxid " + esc(r.taxid) + (r.rank ? " · " + esc(r.rank) : "") + "</span>"
            : "<span class='badge text-bg-warning' title='Not linked to a taxonomy database'>typed by hand</span>";
    }

    function render() {
        $("orgRows").innerHTML = rows.map((r, i) => {
            const roles = ROLES.map(([v, l]) => "<option value='" + v + "'" + (r.role === v ? " selected" : "") + ">" + l + "</option>").join("");
            const name = r.taxid
                ? "<div class='fw-semibold fst-italic'>" + esc(r.name) + "</div>" + (r.path ? "<div class='small text-muted'>" + esc(r.path) + "</div>" : "")
                : "<input class='form-control form-control-sm' data-org='name' data-i='" + i + "' maxlength='255' value='" + esc(r.name) + "' placeholder='Organism name'>";

            return "<div class='d-flex flex-wrap gap-2 align-items-start border rounded p-2 mb-2 bg-light' data-row='" + i + "'>"
                + "<div style='width:11rem'><select class='form-select form-select-sm' data-org='role' data-i='" + i + "'>" + roles + "</select></div>"
                + "<div class='flex-grow-1' style='min-width:14rem'>" + name + "<div class='mt-1'>" + badge(r) + "</div></div>"
                + "<div style='width:10rem'><input class='form-control form-control-sm' data-org='strain' data-i='" + i + "' maxlength='100' value='" + esc(r.strain) + "' placeholder='Strain'></div>"
                + "<button type='button' class='btn btn-sm btn-outline-danger' data-remove='" + i + "' title='Remove'><i class='bi bi-x-lg'></i></button></div>";
        }).join("");
        $("orgNote").textContent = rows.some((r) => !r.taxid) ? "Rows typed by hand are not linked to a taxonomy database; you can replace them by a search later." : "";
        sync();
    }

    function fill(name, value) {
        const field = document.querySelector("[name='" + name + "']");

        if (field && value && !field.value) {
            field.value = value;
            field.dispatchEvent(new Event("input", {bubbles: true}));
        }
    }

    // The type's own genus, species and strain fields follow the main organism when they are empty.
    function followMain() {
        const main = rows[0];

        if (!main) return;

        const type = sampleType();

        if (type === "Bacterium (Host)") {
            fill("genus", main.genus);
            fill("species", main.rank === "species" || main.rank === "subspecies" ? main.name.replace(new RegExp("^" + (main.genus || "") + "\\s+", "i"), "") : "");
            fill("strain", main.strain);
        } else if (type === "Phage (Virus)") {
            fill("genus", main.genus);
            fill("strain", main.strain);
        }
    }

    function add(row) {
        rows.push(Object.assign({role: rows.length ? "member" : "primary", strain: "", notes: ""}, row));
        render();
        followMain();
    }

    function results(data, query) {
        const box = $("orgResults");
        const hand = "<button type='button' class='list-group-item list-group-item-action small' data-hand='" + esc(query) + "'><i class='bi bi-pencil me-1'></i>Add <b>" + esc(query) + "</b> by hand</button>";

        if (!data.available) {
            box.innerHTML = "<div class='list-group-item small text-muted'>The local taxonomy database is not available here. Add the name by hand.</div>" + hand;
        } else if (!data.results.length) {
            box.innerHTML = "<div class='list-group-item small text-muted'>No match in " + esc(data.scope) + ".</div>" + hand;
        } else {
            box.innerHTML = data.results.map((t, i) => "<button type='button' class='list-group-item list-group-item-action' data-hit='" + i + "'>"
                + "<span class='fst-italic fw-semibold'>" + esc(t.name) + "</span> <span class='badge text-bg-light border'>" + esc(t.rank) + "</span> <span class='small text-muted'>taxid " + esc(t.taxid) + "</span>"
                + (t.path ? "<div class='small text-muted'>" + esc(t.path) + "</div>" : "") + "</button>").join("") + hand;
        }

        box.hidden = false;
        box._hits = data.results || [];
    }

    async function search() {
        const query = $("orgQuery").value.trim();
        const mine = ++serial;

        if (query.length < 2) {
            $("orgResults").hidden = true;

            return;
        }

        try {
            const response = await fetch(root.dataset.searchUrl + "?q=" + encodeURIComponent(query) + "&type=" + encodeURIComponent(sampleType()), {credentials: "same-origin"});
            const data = await response.json();

            if (mine === serial && data.status === "success") {
                available = data.available;
                results(data, query);
            }
        } catch (e) {
            if (mine === serial) results({available: false, results: [], scope: ""}, query);
        }
    }

    function scope() {
        const labels = {"Bacterium (Host)": "Bacteria and Archaea", "Phage (Virus)": "Viruses"};

        $("orgScope").textContent = "Searching: " + (labels[sampleType()] || "any organism");
    }

    $("orgQuery").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 250); });
    $("orgQuery").addEventListener("keydown", (event) => { if (event.key === "Enter") event.preventDefault(); });
    $("orgResults").addEventListener("click", (event) => {
        const hit = event.target.closest("[data-hit]");
        const hand = event.target.closest("[data-hand]");

        if (hit) {
            const t = $("orgResults")._hits[Number(hit.dataset.hit)];

            add({name: t.name, taxid: String(t.taxid), rank: t.rank, source: "ncbi", path: t.path, genus: t.genus});
        } else if (hand) {
            add({name: hand.dataset.hand, taxid: "", rank: ""});
        } else {
            return;
        }

        $("orgQuery").value = "";
        $("orgResults").hidden = true;
    });
    document.addEventListener("click", (event) => { if (!root.contains(event.target)) $("orgResults").hidden = true; });
    $("orgManual").addEventListener("click", () => add({name: "", taxid: ""}));
    $("orgRows").addEventListener("input", (event) => {
        const el = event.target.closest("[data-org]");

        if (!el) return;

        const row = rows[Number(el.dataset.i)];

        row[el.dataset.org] = el.value;
        sync();

        if (el.dataset.org === "strain") followMain();
    });
    $("orgRows").addEventListener("change", (event) => {
        const el = event.target.closest("[data-org='role']");

        if (!el) return;

        const i = Number(el.dataset.i);

        rows[i].role = el.value;

        if (el.value === "primary") {
            rows.forEach((r, j) => { if (j !== i && r.role === "primary") r.role = "member"; });
            rows.unshift(rows.splice(i, 1)[0]);
        }

        render();
        followMain();
    });
    $("orgRows").addEventListener("click", (event) => {
        const remove = event.target.closest("[data-remove]");

        if (!remove) return;

        rows.splice(Number(remove.dataset.remove), 1);

        if (rows.length && !rows.some((r) => r.role === "primary")) rows[0].role = "primary";

        render();
    });

    // The "fill from taxonomy" box above the type's fields sets the main organism too.
    document.addEventListener("biobank:set-main-organism", (event) => {
        const t = event.detail;
        const row = {role: "primary", strain: "", notes: "", name: t.name, taxid: String(t.taxid), rank: t.rank, source: "ncbi", path: t.path, genus: t.genus};
        const at = rows.findIndex((r) => r.role === "primary");

        if (at >= 0) {
            row.strain = rows[at].strain || "";
            rows[at] = row;
        } else {
            rows.unshift(row);
        }

        // keep a single entry for the same taxon
        rows = rows.filter((r, i) => i === (at >= 0 ? at : 0) || !(r.taxid && r.taxid === row.taxid && r.strain === row.strain));
        render();
    });

    if (typeInput) typeInput.addEventListener("change", scope);

    scope();
    render();
})();
