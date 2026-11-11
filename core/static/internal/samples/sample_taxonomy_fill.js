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

    function setIfEmpty(name, value) {
        const field = document.querySelector("[name='" + name + "']");

        if (field && value && !field.value) setField(name, value);
    }

    function ictvGenomeType(text) {
        const first = String(text || "").split(",")[0].trim();

        return /RT/.test(first) ? "" : (["dsDNA", "ssDNA", "dsRNA", "ssRNA"].find((g) => first.startsWith(g)) || "");
    }

    function apply(t) {
        const ranks = t.ranks || {};
        const genus = ranks.genus || t.genus || "";
        const type = sampleType();
        const below = ["strain", "subspecies", "serotype", "serogroup", "biotype", "isolate", "forma specialis", "varietas", "no rank"].includes(t.rank);
        const unspecified = /\bsp\./.test(t.name);
        const species = unspecified ? "" : (ranks.species || (t.rank === "species" ? t.name : ""));

        if (type === "Bacterium (Host)") {
            setField("genus", genus);
            setField("species", epithet(species, genus));

            if (below && !unspecified) setField("strain", epithet(t.name, species || genus));
        } else if (type === "Phage (Virus)") {
            setField("genus", genus);
            setField("taxonomy", ranks.family || ranks.order || ranks.class || "");

            if (t.source === "ictv") setIfEmpty("genome_type", ictvGenomeType(t.genome));

            if (below) setField("strain", t.name);
        }

        document.dispatchEvent(new CustomEvent("biobank:set-main-organism", {detail: t}));
        details(t);
    }

    const num = (v) => (v == null ? "-" : Number(v).toLocaleString());
    const SOURCES = {ncbi: "NCBI Taxonomy", gtdb: "GTDB", ictv: "ICTV", inferred: "Inferred from the lineage"};
    let chosen = new Set();

    function writeSelection() {
        $("referenceJson").value = JSON.stringify(Array.from(chosen).map((k) => {
            const [source, key] = k.split("|");

            return {source, key};
        }));
        const count = chosen.size;

        $("taxFillCount").textContent = count ? count + " item(s) will be attached to the sample" : "Nothing selected: only the fields above are filled";
    }

    function card(d) {
        let html = "<div class='border rounded bg-light p-2 small'>";

        (d.warnings || []).forEach((w) => { html += "<div class='text-warning-emphasis mb-1'><i class='bi bi-exclamation-triangle me-1'></i>" + esc(w) + "</div>"; });

        const items = d.catalog || [];

        if (!items.length) return html + "<div class='text-muted'>No reference data is available for this taxon.</div></div>";

        html += "<div class='fw-semibold mb-1'>Reference data for <i>" + esc(d.name) + "</i> - tick what to keep with this sample</div>";

        ["ncbi", "gtdb", "ictv", "inferred"].forEach((source) => {
            const mine = items.filter((i) => i.source === source);

            if (!mine.length) return;

            html += "<div class='mt-2 pt-2 border-top'><div class='d-flex justify-content-between align-items-center'>"
                + "<div class='fw-semibold'>" + esc(SOURCES[source]) + " <span class='text-muted fw-normal'>" + esc(mine[0].version) + "</span>"
                + (source === d.source || source === "inferred" || source === "ncbi" ? "" : " <span class='badge text-bg-light border'>matched through the NCBI species</span>") + "</div>"
                + "<span><button type='button' class='btn btn-link btn-sm p-0 me-2' data-all='" + source + "'>select all</button>"
                + "<button type='button' class='btn btn-link btn-sm p-0' data-none='" + source + "'>none</button></span></div>";

            let group = "";

            mine.forEach((i) => {
                if (i.group !== group) {
                    group = i.group;
                    html += "<div class='text-muted mt-1'>" + esc(group) + "</div>";
                }

                const id = i.source + "|" + i.key;

                html += "<label class='d-flex gap-2 align-items-start ms-2'><input type='checkbox' class='form-check-input mt-1' data-ref='" + esc(id) + "'" + (chosen.has(id) ? " checked" : "") + ">"
                    + "<span><span class='text-muted'>" + esc(i.label) + ":</span> " + esc(i.value) + "</span></label>";
            });

            html += "</div>";
        });

        return html + "</div>";
    }

    $("taxFillCard").addEventListener("change", (event) => {
        const box = event.target.closest("[data-ref]");

        if (!box) return;

        box.checked ? chosen.add(box.dataset.ref) : chosen.delete(box.dataset.ref);
        writeSelection();
    });
    $("taxFillCard").addEventListener("click", (event) => {
        const all = event.target.closest("[data-all]");
        const none = event.target.closest("[data-none]");
        const source = (all || none || {dataset: {}}).dataset.all || (all || none || {dataset: {}}).dataset.none;

        if (!source) return;

        $("taxFillCard").querySelectorAll("[data-ref^='" + source + "|']").forEach((box) => {
            box.checked = !!all;
            all ? chosen.add(box.dataset.ref) : chosen.delete(box.dataset.ref);
        });
        writeSelection();
    });

    async function details(t) {
        const box = $("taxFillCard");

        box.hidden = true;
        chosen = new Set();
        writeSelection();

        try {
            const query = t.source === "gtdb" ? "?source=gtdb&name=" + encodeURIComponent(t.gtdb) : t.source === "ictv" ? "?source=ictv&name=" + encodeURIComponent(t.ictv) : "?taxid=" + encodeURIComponent(t.taxid) + "&type=" + encodeURIComponent(sampleType());
            const response = await fetch(root.dataset.detailsUrl + query, {credentials: "same-origin"});
            const d = await response.json();

            if (d.status !== "success") return;

            const inferred = d.inferred || {};

            setIfEmpty("genome_type", d.genome_type || (inferred.genome_type && inferred.genome_type.value));
            setIfEmpty("ncbi_accession", d.ncbi_accession);
            setIfEmpty("morphotype", inferred.morphotype && inferred.morphotype.value);
            box.innerHTML = card(d);
            box.hidden = false;
        } catch (e) {
            box.hidden = true;
        }
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
                + "<span class='fst-italic fw-semibold'>" + esc(t.name) + "</span> <span class='badge " + ({gtdb: "text-bg-success", ictv: "text-bg-warning"}[t.source] || "text-bg-primary") + "'>" + (t.source || "ncbi").toUpperCase() + "</span> <span class='badge text-bg-light border'>" + esc(t.rank) + "</span> <span class='small text-muted'>" + (t.source === "gtdb" ? num(t.genomes) + " genomes" : t.source === "ictv" ? esc(t.genome) + (t.hosts ? " · host: " + esc(t.hosts) : "") : "taxid " + esc(t.taxid)) + "</span>"
                + (t.matched ? " <span class='small text-muted'>(" + esc(t.matched) + ")</span>" : "")
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
            const response = await fetch(root.dataset.searchUrl + "?q=" + encodeURIComponent(query) + "&type=" + encodeURIComponent(sampleType()) + "&source=" + $("taxFillSource").value, {credentials: "same-origin"});
            const data = await response.json();

            if (mine === serial && data.status === "success") show(data, query);
        } catch (e) {
            if (mine === serial) show({available: false, results: [], scope: ""}, query);
        }
    }

    function toggle() {
        root.hidden = !supported();

        const type = sampleType();
        const own = {"Bacterium (Host)": "gtdb", "Phage (Virus)": "ictv"}[type];

        $("taxFillSource").querySelectorAll("option").forEach((o) => { o.hidden = o.value !== "all" && o.value !== "ncbi" && o.value !== own; });
        $("taxFillSource").closest(".d-flex").hidden = !own;
        $("taxFillSource").value = own ? "all" : "ncbi";

        $("taxFillQuery").placeholder = {
            "Bacterium (Host)": "Scientific or common name, for example Escherichia coli or E. coli",
            "Phage (Virus)": "Scientific name of the virus, genus or family, for example Tequatrovirus",
        }[sampleType()] || "Scientific or common name";
    }

    $("taxFillSource").addEventListener("change", search);
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
