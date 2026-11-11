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

            if (below) setField("strain", t.name);
        }

        document.dispatchEvent(new CustomEvent("biobank:set-main-organism", {detail: t}));
        details(t);
    }

    const list = (items, limit) => (items || []).slice(0, limit || 6).map(esc).join("; ");
    const pairs = (items) => (items || []).map((p) => esc(p[0]) + " (" + p[1] + ")").join("; ");
    const num = (v, d) => (v == null ? "-" : Number(v).toLocaleString(undefined, {maximumFractionDigits: d == null ? 0 : d}));

    function card(d) {
        const rows = [];
        const add = (label, value) => { if (value) rows.push("<div><span class='text-muted'>" + label + ":</span> " + value + "</div>"); };
        const g = d.gtdb;

        add("NCBI", "taxid " + esc(d.taxid) + " · " + esc(d.rank) + (d.division ? " · " + esc(d.division) : "") + (d.genetic_code ? " · genetic code: " + esc(d.genetic_code) : ""));
        add("Lineage", (d.lineage || []).filter((c) => c.rank !== "no rank" && c.rank !== "clade").map((c) => esc(c.name)).join(" > "));
        add("Also known as", list(d.synonyms));
        add("Common names", list(d.common_names, 4));
        add("Authority", list(d.authority, 3));

        let html = "<div class='border rounded bg-light p-2 small'>" + rows.join("");

        (d.warnings || []).forEach((w) => { html += "<div class='text-warning-emphasis mt-1'><i class='bi bi-exclamation-triangle me-1'></i>" + esc(w) + "</div>"; });

        const inferred = d.inferred || {};
        const inf = Object.keys(inferred).map((k) => esc(k.replace("_", " ")) + " = <b>" + esc(inferred[k].value) + "</b> (from " + esc(inferred[k].basis) + ")");

        if (inf.length) html += "<div class='mt-1'><span class='badge text-bg-info me-1'>inferred</span>" + inf.join("; ") + ". Filled only when the field was empty.</div>";

        if (g) {
            html += "<div class='mt-2 pt-2 border-top'><div class='fw-semibold'>GTDB " + esc(g.release) + " reference for " + esc(g.name) + "</div>"
                + "<div>" + num(g.genomes) + " genomes · size " + num(g.genome_size_median) + " bp (" + num(g.genome_size_min) + " – " + num(g.genome_size_max) + ") · GC " + num(g.gc_mean, 1) + "%</div>"
                + "<div>CheckM2 completeness " + num(g.completeness_mean, 1) + "% · contamination " + num(g.contamination_mean, 1) + "% · type-material genomes " + num(g.type_material_genomes) + "</div>"
                + (g.isolation_sources && g.isolation_sources.length ? "<div><span class='text-muted'>Common isolation sources:</span> " + pairs(g.isolation_sources) + "</div>" : "")
                + (g.countries && g.countries.length ? "<div><span class='text-muted'>Countries:</span> " + pairs(g.countries) + "</div>" : "")
                + "<div class='text-muted'>" + esc((g.lineage || "").replace(/[a-z]__/g, "").split(";").join(" > ")) + "</div></div>";
        }

        return html + "</div>";
    }

    async function details(t) {
        const box = $("taxFillCard");

        box.hidden = true;

        try {
            const response = await fetch(root.dataset.detailsUrl + "?taxid=" + encodeURIComponent(t.taxid) + "&type=" + encodeURIComponent(sampleType()), {credentials: "same-origin"});
            const d = await response.json();

            if (d.status !== "success") return;

            const inferred = d.inferred || {};

            setIfEmpty("genome_type", inferred.genome_type && inferred.genome_type.value);
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
