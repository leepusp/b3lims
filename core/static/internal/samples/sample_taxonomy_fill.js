(function () {
    "use strict";

    const root = document.getElementById("taxFill");

    if (!root) return;

    const $ = (id) => document.getElementById(id);
    const typeInput = root.dataset.typeInput ? document.getElementById(root.dataset.typeInput) : null;
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
    const sampleType = () => (typeInput ? typeInput.value : root.dataset.type) || "";
    const supported = () => ["Bacterium (Host)", "Phage (Virus)"].includes(sampleType());
    let timer = null;
    let serial = 0;
    let hits = [];

    function setField(name, value) {
        const field = document.querySelector("[name='" + name + "']");

        if (!field || value == null) return;

        field.value = value;
        field.dispatchEvent(new Event("input", {bubbles: true}));
        field.dispatchEvent(new Event("change", {bubbles: true}));
    }

    function epithet(name, genus) {
        return genus ? name.replace(new RegExp("^" + genus.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s+", "i"), "") : name;
    }

    function apply(t) {
        const ranks = t.ranks || {};
        const genus = ranks.genus || t.genus || "";
        const type = sampleType();
        const below = ["strain", "subspecies", "serotype", "serogroup", "biotype", "isolate", "forma specialis", "varietas", "no rank"].includes(t.rank);
        const species = ranks.species || (t.rank === "species" ? t.name : "");

        if (type === "Bacterium (Host)") {
            setField("genus", genus);
            setField("species", epithet(species, genus));

            if (below) setField("strain", epithet(t.name, species || genus));
        } else if (type === "Phage (Virus)") {
            setField("genus", genus);
            setField("taxonomy", ranks.family || ranks.order || ranks.class || "");

            if (below) setField("strain", t.name);
        }

        document.dispatchEvent(new CustomEvent("biobank:set-main-organism", {detail: t}));
    }

    function show(data, query) {
        const box = $("taxFillResults");

        if (!data.available) {
            box.innerHTML = "<div class='list-group-item small text-muted'>The local taxonomy database is not available here. Type the fields by hand.</div>";
        } else if (!data.results.length) {
            box.innerHTML = "<div class='list-group-item small text-muted'>No match for <b>" + esc(query) + "</b> in " + esc(data.scope) + ". Type the fields by hand.</div>";
        } else {
            hits = data.results;
            box.innerHTML = hits.map((t, i) => "<button type='button' class='list-group-item list-group-item-action' data-hit='" + i + "'>"
                + "<span class='fst-italic fw-semibold'>" + esc(t.name) + "</span> <span class='badge text-bg-light border'>" + esc(t.rank) + "</span> <span class='small text-muted'>taxid " + esc(t.taxid) + "</span>"
                + (t.path ? "<div class='small text-muted'>" + esc(t.path) + "</div>" : "") + "</button>").join("");
        }

        box.hidden = false;
    }

    async function search() {
        const query = $("taxFillQuery").value.trim();
        const mine = ++serial;

        if (query.length < 2) {
            $("taxFillResults").hidden = true;

            return;
        }

        try {
            const response = await fetch(root.dataset.searchUrl + "?q=" + encodeURIComponent(query) + "&type=" + encodeURIComponent(sampleType()), {credentials: "same-origin"});
            const data = await response.json();

            if (mine === serial && data.status === "success") show(data, query);
        } catch (e) {
            if (mine === serial) show({available: false, results: [], scope: ""}, query);
        }
    }

    function toggle() { root.hidden = !supported(); }

    $("taxFillQuery").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 250); });
    $("taxFillQuery").addEventListener("keydown", (event) => { if (event.key === "Enter") event.preventDefault(); });
    $("taxFillResults").addEventListener("click", (event) => {
        const hit = event.target.closest("[data-hit]");

        if (!hit) return;

        apply(hits[Number(hit.dataset.hit)]);
        $("taxFillQuery").value = "";
        $("taxFillResults").hidden = true;
    });
    document.addEventListener("click", (event) => { if (!root.contains(event.target)) $("taxFillResults").hidden = true; });

    if (typeInput) typeInput.addEventListener("change", toggle);

    toggle();
})();
