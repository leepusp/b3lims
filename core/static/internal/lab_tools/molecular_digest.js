/*
 * Molecular digest panel.
 *
 * Pick enzymes (search by name or site, type IIS included), see the cuts on
 * the map and in the sequence, the fragments, and an interactive gel whose
 * bands select the matching region. Cuts are shared with the map and the
 * sequence editor through window.BiobankDigest and the
 * "biobank:digest-change" event.
 */
(function () {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const panel = document.getElementById("mw-digest");
    const calc = window.BiobankDigestCalc;

    if (!root || !panel || !calc) {
        return;
    }

    const NS = "http://www.w3.org/2000/svg";
    const COLORS = ["#1D4ED8", "#D9480F", "#2B8A3E", "#9C36B5", "#C2255C", "#0B7285", "#E67700", "#495057"];
    const LADDERS = {
        "1 kb": calc.LADDER,
        "100 bp": [1500, 1200, 1000, 900, 800, 700, 600, 500, 400, 300, 200, 100],
        "λ HindIII": [23130, 9416, 6557, 4361, 2322, 2027, 564],
    };
    const GELS = {
        "0.7%": [400, 15000],
        "1%": [250, 10000],
        "1.5%": [150, 6000],
        "2%": [80, 3500],
    };
    const FILTERS = [
        ["unique", "Cut once"],
        ["few", "Cut 1–3 times"],
        ["iis", "Type IIS"],
        ["blunt", "Blunt ends"],
        ["all", "All enzymes"],
    ];
    const LIMIT = 80;

    const picked = [];
    const THEMES = {
        dark: {label: "Classic dark", bg: "#12202E", band: "#EAF2FA", ladder: "#C8D6E5", text: "#9FB3C8", well: "#0A141E", glow: "#9CC3F0"},
        uv: {label: "Ethidium (UV orange)", bg: "#1B0F08", band: "#FFA24A", ladder: "#FFC98F", text: "#D9A877", well: "#0D0704", glow: "#FF7A18"},
        sybr: {label: "SYBR green", bg: "#06140C", band: "#86FFA3", ladder: "#BDFFD0", text: "#8FCBA2", well: "#030B06", glow: "#2EE06A"},
        blue: {label: "Blue light", bg: "#0A1626", band: "#7CCBFF", ladder: "#B5E1FF", text: "#86A9C8", well: "#050C16", glow: "#2E9BFF"},
        light: {label: "Light (for printing)", bg: "#F6F8FB", band: "#1B2733", ladder: "#5C6B7C", text: "#2B3A4A", well: "#C5CED8", glow: "#1B2733"},
    };
    const SIZES = [["fill", "Fill the window"], ["compact", "Compact"], ["tall", "Tall"]];
    const ui = {query: "", filter: "unique", ladder: "1 kb", gel: "1%", all: false, look: "dark", size: "fill", bright: 100, thick: 100, labels: false};
    let mode = "map";

    try {
        Object.assign(ui, JSON.parse(window.localStorage.getItem("biobank.digest.gellook") || "{}"));
    } catch (error) {
        // Storage can be blocked or hold something unreadable; defaults apply.
    }

    if (!THEMES[ui.look]) ui.look = "dark";
    let cache = {key: "", counts: [], sites: [], fragments: [], snapshot: null};
    let frame = 0;

    const api = () => window.BiobankMolecularWorkspace || null;

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function svg(tag, attributes, text) {
        const node = document.createElementNS(NS, tag);

        Object.entries(attributes || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));

        if (text !== undefined) node.textContent = text;

        return node;
    }

    const colorOf = name => COLORS[Math.max(0, picked.indexOf(name)) % COLORS.length];

    /* ---------- computation ---------- */

    function compute() {
        const workspace = api();
        const snapshot = workspace ? workspace.getSnapshot() : null;

        if (!snapshot) return cache;

        const circular = snapshot.topology === "circular";
        const key = [circular, picked.join(","), snapshot.sequence.length, snapshot.sequence.slice(0, 64), snapshot.sequence.slice(-64)].join("|");
        const sequence = snapshot.sequence;

        if (cache.sequence !== sequence || cache.circular !== circular) {
            cache = {key: "", sequence, circular, counts: calc.catalogCounts(sequence, circular), sites: [], fragments: [], snapshot};
        }

        if (cache.key !== key) {
            cache.key = key;
            cache.sites = picked.flatMap(name => calc.cutSites(sequence, name, circular))
                .map(site => ({...site, color: colorOf(site.enzyme)}))
                .sort((a, b) => a.position - b.position);
            cache.fragments = picked.length ? calc.digest(sequence, picked, circular) : [];
        }

        cache.snapshot = snapshot;

        return cache;
    }

    function publish() {
        document.dispatchEvent(new CustomEvent("biobank:digest-change", {detail: {sites: cache.sites.length}}));
    }

    window.BiobankDigest = {
        sites() {
            return picked.length ? compute().sites : [];
        },
        enzymes: () => picked.slice(),
        fragments: () => (picked.length ? compute().fragments : []),
        pick(name) {
            if (calc.byName(name) && !picked.includes(name)) {
                picked.push(name);
                changed();
            }
        },
        clear() {
            picked.length = 0;
            changed();
        },
    };

    /* ---------- skeleton ---------- */

    const enzymeCard = el("section", "mwd-card mwd-enzymes");
    const search = el("input", "mwd-search");
    const filterSelect = el("select", "mwd-select");
    const enzymeList = el("div", "mwd-list");
    const enzymeNote = el("p", "mwd-note");
    const fragmentCard = el("section", "mwd-card mwd-fragments");
    const fragmentTitle = el("span", "mwd-label");
    const fragmentList = el("div", "mwd-fraglist");
    const exportRow = el("div", "mwd-exports");
    const gelCard = el("section", "mwd-card mwd-gelcard");
    const gelHost = el("div", "mwd-gelhost");
    const gelTip = el("div", "mwd-geltip");
    const ladderSelect = el("select", "mwd-select");
    const percentSelect = el("select", "mwd-select");

    search.type = "search";
    search.placeholder = "Search an enzyme or a site (e.g. BsaI, GAATTC)";
    search.setAttribute("aria-label", "Search enzymes");
    filterSelect.setAttribute("aria-label", "Which enzymes to list");
    ladderSelect.setAttribute("aria-label", "Ladder");
    percentSelect.setAttribute("aria-label", "Agarose percentage");
    gelTip.hidden = true;

    FILTERS.forEach(([value, label]) => {
        const option = el("option", "", label);

        option.value = value;
        filterSelect.append(option);
    });
    Object.keys(LADDERS).forEach(name => {
        const option = el("option", "", name + " ladder");

        option.value = name;
        ladderSelect.append(option);
    });
    Object.keys(GELS).forEach(name => {
        const option = el("option", "", name + " agarose");

        option.value = name;
        percentSelect.append(option);
    });
    percentSelect.value = ui.gel;

    const enzymeHead = el("div", "mwd-head");
    const clearButton = el("button", "mwd-link", "Clear");

    clearButton.type = "button";
    enzymeHead.append(el("span", "mwd-label", "Enzymes"), clearButton);
    enzymeCard.append(enzymeHead, search, filterSelect, enzymeList, enzymeNote);

    const gelHead = el("div", "mwd-head");

    const looks = el("div", "mwd-looks");
    const themeSelect = el("select", "mwd-select");
    const sizeSelect = el("select", "mwd-select");
    const brightInput = el("input", "mwd-range");
    const thickInput = el("input", "mwd-range");
    const labelsBox = el("input");
    const gelPng = el("button", "mwd-link", "PNG");

    Object.entries(THEMES).forEach(([value, theme]) => {
        const option = el("option", "", theme.label);

        option.value = value;
        themeSelect.append(option);
    });
    SIZES.forEach(([value, label]) => {
        const option = el("option", "", label);

        option.value = value;
        sizeSelect.append(option);
    });
    [[brightInput, 40, 200], [thickInput, 50, 200]].forEach(([input, min, max]) => {
        input.type = "range";
        input.min = String(min);
        input.max = String(max);
    });
    labelsBox.type = "checkbox";
    gelPng.type = "button";
    gelPng.title = "Download the gel as an image";
    themeSelect.setAttribute("aria-label", "Gel colours");
    sizeSelect.setAttribute("aria-label", "Gel size");
    brightInput.setAttribute("aria-label", "Band brightness");
    thickInput.setAttribute("aria-label", "Band thickness");
    themeSelect.value = ui.look;
    sizeSelect.value = ui.size;
    brightInput.value = String(ui.bright);
    thickInput.value = String(ui.thick);
    labelsBox.checked = ui.labels;

    const labelled = (text, node) => {
        const wrap = el("label", "mwd-lookitem");

        wrap.append(el("span", "", text), node);

        return wrap;
    };

    looks.append(labelled("Colours", themeSelect), labelled("Size", sizeSelect), labelled("Brightness", brightInput), labelled("Thickness", thickInput), labelled("Band sizes", labelsBox), gelPng);
    gelHead.append(el("span", "mwd-label", "Gel"), ladderSelect, percentSelect);
    gelCard.append(gelHead, looks, gelHost, el("p", "mwd-note", "Hover a band to see it, click it to select that fragment on the map and in the sequence."));
    fragmentCard.append(fragmentList, exportRow);
    const grid = el("div", "mwd-grid");

    function foldable(card, key, heading) {
        const header = heading || card.querySelector(".mwd-head");
        const button = el("button", "mwd-fold", "▾");
        let open = true;

        try {
            open = window.localStorage.getItem("biobank.digest.fold." + key) !== "closed";
        } catch (error) {
            // Storage can be blocked; the card then starts open.
        }

        function apply() {
            card.classList.toggle("is-collapsed", !open);
            button.textContent = open ? "▾" : "▸";
            button.setAttribute("aria-expanded", String(open));
            button.title = open ? "Fold this section" : "Unfold this section";
        }

        button.type = "button";
        button.addEventListener("click", () => {
            open = !open;
            apply();

            try {
                window.localStorage.setItem("biobank.digest.fold." + key, open ? "open" : "closed");
            } catch (error) {
                // Not persisted; fine.
            }
        });
        header.append(button);
        apply();
    }

    const fragmentHead = el("div", "mwd-head");

    fragmentHead.append(fragmentTitle);
    fragmentCard.prepend(fragmentHead);
    foldable(enzymeCard, "enzymes");
    foldable(fragmentCard, "fragments");
    foldable(gelCard, "gel");
    grid.append(gelCard, enzymeCard, fragmentCard);
    panel.replaceChildren(grid);

    /* ---------- enzymes ---------- */

    function siteLabel(item) {
        const width = item.site.length;

        return item.typeIIS
            ? item.site + "(" + (item.cut - width) + "/" + (item.bottom - width) + ")"
            : item.site.slice(0, item.cut) + "^" + item.site.slice(item.cut);
    }

    function matches(item, query) {
        return !query || item.name.toLowerCase().includes(query) || item.site.toLowerCase().includes(query);
    }

    function passes(item) {
        switch (ui.filter) {
            case "unique": return item.cuts.length === 1;
            case "few": return item.cuts.length >= 1 && item.cuts.length <= 3;
            case "iis": return item.typeIIS;
            case "blunt": return item.ends === "blunt";
            default: return true;
        }
    }

    function enzymeRow(item) {
        const on = picked.includes(item.name);
        const row = el("button", "mwd-enzyme" + (on ? " is-on" : ""));
        const check = el("span", "mwd-check", on ? "✓" : "");

        row.type = "button";
        row.setAttribute("aria-pressed", String(on));
        row.title = item.ends + (item.typeIIS ? " · type IIS, cuts outside its site" : "");

        if (on) check.style.cssText = "background:" + colorOf(item.name) + ";border-color:" + colorOf(item.name) + ";color:#fff";

        const name = el("b", "", item.name);

        row.append(check, name);

        if (item.typeIIS) row.append(el("span", "mwd-badge", "IIS"));

        row.append(
            el("span", "mwd-site", siteLabel(item)),
            el("span", "mwd-count", item.cuts.length === 0 ? "no cut" : item.cuts.length === 1 ? "1 cut · " + (item.cuts[0] || "origin") : item.cuts.length + " cuts")
        );
        row.addEventListener("click", () => {
            const index = picked.indexOf(item.name);

            if (index >= 0) picked.splice(index, 1);
            else picked.push(item.name);

            changed();
        });

        return row;
    }

    function renderEnzymes(state) {
        const query = ui.query.trim().toLowerCase();
        const chosen = state.counts.filter(item => picked.includes(item.name));
        const rest = state.counts.filter(item => !picked.includes(item.name) && matches(item, query) && (query || passes(item)));
        const shown = ui.all ? rest : rest.slice(0, LIMIT);

        enzymeList.replaceChildren(...chosen.map(enzymeRow), ...shown.map(enzymeRow));

        if (!chosen.length && !shown.length) {
            enzymeList.append(el("p", "mwd-empty", query ? "No enzyme matches “" + ui.query + "”." : "No enzyme matches this filter."));
        }

        if (rest.length > shown.length) {
            const more = el("button", "mwd-link", "Show all " + rest.length + " matches");

            more.type = "button";
            more.addEventListener("click", () => {
                ui.all = true;
                renderEnzymes(compute());
            });
            enzymeList.append(more);
        }

        clearButton.hidden = !picked.length;
        enzymeNote.textContent = "Sites are searched on both strands. Cut counts are for the " + (state.circular ? "circular" : "linear") + " molecule. IIS enzymes cut outside their site: (n/m) is the distance of the two cuts from the site.";
    }

    /* ---------- fragments ---------- */

    function selectRange(fragment) {
        const workspace = api();

        if (workspace) workspace.selectSequenceRange(fragment.start, fragment.end, {source: "digest"});
    }

    function isSelected(fragment, snapshot) {
        const sel = snapshot && snapshot.sequenceSelection;

        return Boolean(sel && sel.start === fragment.start && sel.end === fragment.end);
    }

    function renderFragments(state) {
        const total = state.sequence ? state.sequence.length : 0;
        const fragments = picked.length ? state.fragments : [];

        fragmentTitle.textContent = picked.length ? "Fragments · " + fragments.length : "Fragments";
        fragmentList.replaceChildren();

        if (!picked.length) {
            fragmentList.append(el("p", "mwd-empty", "Pick one or more enzymes. The cuts appear on the map and in the sequence, and the fragments and the gel update at once."));
        }

        fragments.slice().sort((a, b) => b.length - a.length).forEach((fragment, index) => {
            const row = el("button", "mwd-fragment" + (isSelected(fragment, state.snapshot) ? " is-selected" : ""));
            const bar = el("span", "mwd-bar");
            const fill = el("span", "mwd-fill");

            row.type = "button";
            row.dataset.size = fragment.length;
            row.dataset.start = fragment.start;
            row.title = "Select this fragment";
            fill.style.width = Math.max(2, Math.round(fragment.length / total * 100)) + "%";
            fill.style.background = COLORS[index % COLORS.length];
            bar.append(fill);
            row.append(
                el("span", "mwd-range", fragment.start.toLocaleString() + "–" + fragment.end.toLocaleString()),
                bar,
                el("b", "mwd-size", fragment.length.toLocaleString("en-US") + " bp")
            );
            row.addEventListener("click", () => selectRange(fragment));
            row.addEventListener("pointerenter", () => highlightBands(fragment.start, true));
            row.addEventListener("pointerleave", () => highlightBands(fragment.start, false));
            fragmentList.append(row);
        });

        exportRow.hidden = !picked.length;
    }

    function download(name, type, content) {
        const blob = content instanceof Blob ? content : new Blob([content], {type});
        const link = document.createElement("a");

        link.href = URL.createObjectURL(blob);
        link.download = name;
        document.body.append(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(link.href), 2000);
    }

    function fileBase() {
        const snapshot = cache.snapshot;
        const name = snapshot && snapshot.name ? snapshot.name : "record";

        return name.replace(/[^A-Za-z0-9._-]+/g, "_") + "_" + picked.join("-");
    }

    function csvCell(value) {
        return /[",\n]/.test(String(value)) ? '"' + String(value).replace(/"/g, '""') + '"' : String(value);
    }

    function addExport(label, title, handler) {
        const button = el("button", "mwd-action", label);

        button.type = "button";
        button.title = title;
        button.addEventListener("click", handler);
        exportRow.append(button);

        return button;
    }

    addExport("Copy fragments", "Copy start, end and size of every fragment", event => {
        const text = compute().fragments.map(item => item.start + "\t" + item.end + "\t" + item.length).join("\n");

        if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});

        event.currentTarget.textContent = "Copied";
        window.setTimeout(() => {
            event.target.textContent = "Copy fragments";
        }, 1500);
    });
    addExport("Fragments CSV", "Download the fragment table", () => {
        const rows = [["start", "end", "length_bp"]].concat(compute().fragments.map(item => [item.start, item.end, item.length]));

        download(fileBase() + "_fragments.csv", "text/csv", rows.map(row => row.map(csvCell).join(",")).join("\n") + "\n");
    });
    addExport("Cut sites CSV", "Download every cut with its position and ends", () => {
        const rows = [["enzyme", "site", "strand", "cut_after_base_top", "cut_after_base_bottom", "ends"]].concat(compute().sites.map(site => [
            site.enzyme, calc.byName(site.enzyme).site, site.strand, site.position, site.bottom,
            site.overhang === 0 ? "blunt" : (site.overhang > 0 ? "5' overhang " + site.overhang : "3' overhang " + -site.overhang),
        ]));

        download(fileBase() + "_cuts.csv", "text/csv", rows.map(row => row.map(csvCell).join(",")).join("\n") + "\n");
    });
    addExport("Map SVG", "Download the restriction map as an SVG image", () => {
        if (window.BiobankMapCanvas && window.BiobankMapCanvas.downloadImage) window.BiobankMapCanvas.downloadImage("svg", fileBase() + "_map");
    });
    addExport("Map PNG", "Download the restriction map as a PNG image", () => {
        if (window.BiobankMapCanvas && window.BiobankMapCanvas.downloadImage) window.BiobankMapCanvas.downloadImage("png", fileBase() + "_map");
    });

    /* ---------- gel ---------- */

    function lanesFor(state) {
        const sequence = state.sequence || "";
        const lanes = [
            {label: "Ladder", ladder: true, bands: LADDERS[ui.ladder].map(size => ({size, count: 1}))},
            {label: "Uncut", bands: [{size: sequence.length, count: 1}]},
        ];

        function group(fragments) {
            const bySize = new Map();

            fragments.forEach(fragment => {
                const entry = bySize.get(fragment.length) || {size: fragment.length, count: 0, fragment};

                entry.count += 1;
                bySize.set(fragment.length, entry);
            });

            return Array.from(bySize.values());
        }

        if (picked.length > 1 && picked.length <= 4) {
            picked.forEach(name => lanes.push({label: name, bands: group(calc.digest(sequence, [name], state.circular)), single: name}));
        }

        if (picked.length) lanes.push({label: picked.length === 1 ? picked[0] : "All", bands: group(state.fragments), main: true});

        return lanes;
    }

    function highlightBands(start, on) {
        gelHost.querySelectorAll('[data-start="' + start + '"]').forEach(node => node.classList.toggle("is-hover", on));
    }

    function gelHeight() {
        if (ui.size === "compact") return 300;
        if (ui.size === "tall") return 720;

        const used = gelHost.getBoundingClientRect().top - panel.getBoundingClientRect().top + panel.scrollTop;

        return Math.max(300, Math.min(760, (panel.clientHeight || 560) - used - 56));
    }

    let lastGel = null;

    function renderGel(state) {
        lastGel = state;

        const theme = THEMES[ui.look];
        const lanes = lanesFor(state);
        const width = Math.max(260, Math.round(gelHost.clientWidth || 360));
        const height = gelHeight();
        const left = 44;
        const top = 38;
        const laneW = Math.max(40, Math.min(120, (width - left - 10) / lanes.length));
        const offset = left + Math.max(0, (width - left - 10 - laneW * lanes.length) / 2);
        const usable = height - top - 14;
        const [min, max] = GELS[ui.gel];
        const y = size => top + calc.gelPosition(size, min, max) * usable;
        const node = svg("svg", {viewBox: "0 0 " + width + " " + height, width, height, class: "mwd-gel", role: "img", "aria-label": "Simulated agarose gel", "font-family": "sans-serif"});
        const total = state.sequence ? state.sequence.length : 1;
        const defs = svg("defs");
        const blur = svg("filter", {id: "mwdGlow", x: "-30%", y: "-300%", width: "160%", height: "700%"});
        const fontSize = Math.max(9, Math.min(13, laneW / 6));

        blur.append(svg("feGaussianBlur", {stdDeviation: 2.2}));
        defs.append(blur);
        node.append(defs, svg("rect", {x: 0, y: 0, width, height, rx: 8, fill: theme.bg}));

        lanes.forEach((lane, index) => {
            const x = offset + index * laneW;
            const bandW = laneW - Math.max(10, laneW * 0.22);
            const bandX = x + (laneW - bandW) / 2;

            node.append(svg("rect", {x: bandX, y: top - 9, width: bandW, height: 5, rx: 2, fill: theme.well}));
            node.append(svg("text", {x: x + laneW / 2, y: 20, "text-anchor": "middle", "font-size": fontSize + 1, fill: theme.text}, lane.label.length > 9 ? lane.label.slice(0, 8) + "…" : lane.label));

            lane.bands.forEach(band => {
                const by = y(band.size);
                const group = svg("g", {class: "mwd-band" + (lane.ladder ? " is-ladder" : "")});
                const mass = Math.min(1, band.size * band.count / total * 1.4);
                const base = lane.ladder ? 3 : Math.max(3, Math.min(8, 2 + band.size / total * 6 * band.count));
                const weight = Math.max(1.5, base * (ui.thick / 100) * Math.sqrt(height / 300));
                const strength = Math.min(1, (lane.ladder ? 0.8 : 0.4 + 0.6 * mass) * ui.bright / 100);
                const color = lane.ladder ? theme.ladder : theme.band;
                const glow = svg("rect", {x: bandX, y: (by - weight / 2).toFixed(1), width: bandW, height: weight, rx: 2, fill: theme.glow, opacity: (strength * 0.55).toFixed(2), filter: "url(#mwdGlow)"});
                const rect = svg("rect", {x: bandX, y: (by - weight / 2).toFixed(1), width: bandW, height: weight, rx: 1.5, fill: color, opacity: strength.toFixed(2)});
                const hit = svg("rect", {x: x + 2, y: (by - 7).toFixed(1), width: laneW - 4, height: 14, fill: "transparent", style: "cursor:" + (lane.ladder ? "default" : "pointer")});

                group.append(glow, rect, hit);

                if (band.fragment) group.dataset.start = band.fragment.start;

                const label = band.size.toLocaleString("en-US") + " bp" + (band.count > 1 ? " ×" + band.count : "");

                hit.addEventListener("pointerenter", event => {
                    const box = gelHost.getBoundingClientRect();

                    gelTip.textContent = (lane.ladder ? "Ladder " : lane.label + " · ") + label;
                    gelTip.style.left = Math.min(event.clientX - box.left + 12, box.width - 130) + "px";
                    gelTip.style.top = event.clientY - box.top + 12 + "px";
                    gelTip.hidden = false;
                    group.classList.add("is-hover");

                    if (lane.main && band.fragment) {
                        fragmentList.querySelectorAll('.mwd-fragment[data-start="' + band.fragment.start + '"]').forEach(row => row.classList.add("is-hover"));
                    }
                });
                hit.addEventListener("pointerleave", () => {
                    gelTip.hidden = true;
                    group.classList.remove("is-hover");
                    fragmentList.querySelectorAll(".mwd-fragment.is-hover").forEach(row => row.classList.remove("is-hover"));
                });

                if (!lane.ladder && band.fragment) {
                    hit.addEventListener("click", () => selectRange(band.fragment));
                }

                node.append(group);

                if (ui.labels && !lane.ladder && laneW >= 56) {
                    node.append(svg("text", {x: x + laneW / 2, y: (by - weight / 2 - 3).toFixed(1), "text-anchor": "middle", "font-size": Math.max(8, fontSize - 2), fill: theme.text}, band.size.toLocaleString("en-US")));
                }

                if (lane.ladder && index === 0) {
                    node.append(svg("text", {x: x - 3, y: by + 3, "text-anchor": "end", "font-size": Math.max(8, fontSize - 1), fill: theme.text}, band.size >= 1000 ? (band.size / 1000).toFixed(band.size % 1000 ? 1 : 0) + "k" : String(band.size)));
                }
            });
        });

        gelHost.replaceChildren(node, gelTip);
    }

    function saveLook() {
        try {
            window.localStorage.setItem("biobank.digest.gellook", JSON.stringify({look: ui.look, size: ui.size, bright: ui.bright, thick: ui.thick, labels: ui.labels}));
        } catch (error) {
            // Not persisted; fine.
        }
    }

    function downloadGel() {
        const source = gelHost.querySelector("svg");

        if (!source) return;

        const text = new XMLSerializer().serializeToString(source);
        const image = new Image();
        const url = URL.createObjectURL(new Blob([text], {type: "image/svg+xml"}));

        image.onload = () => {
            const canvas = document.createElement("canvas");
            const scale = 2;

            canvas.width = source.viewBox.baseVal.width * scale;
            canvas.height = source.viewBox.baseVal.height * scale;
            canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
            URL.revokeObjectURL(url);
            canvas.toBlob(blob => {
                const link = document.createElement("a");

                link.href = URL.createObjectURL(blob);
                link.download = fileBase() + "_gel.png";
                document.body.append(link);
                link.click();
                link.remove();
            }, "image/png");
        };
        image.src = url;
    }

    /* ---------- orchestration ---------- */

    function renderAll() {
        frame = 0;

        const state = compute();

        if (mode !== "digest") return;

        renderEnzymes(state);
        renderFragments(state);
        renderGel(state);
    }

    function schedule() {
        if (!frame) frame = window.requestAnimationFrame(renderAll);
    }

    let lastCut = "";

    function changed() {
        ui.all = false;
        compute();
        lastCut = cache.key;
        publish();
        schedule();
    }

    search.addEventListener("input", () => {
        ui.query = search.value;
        ui.all = false;
        renderEnzymes(compute());
    });
    filterSelect.addEventListener("change", () => {
        ui.filter = filterSelect.value;
        ui.all = false;
        renderEnzymes(compute());
    });
    ladderSelect.addEventListener("change", () => {
        ui.ladder = ladderSelect.value;
        renderGel(compute());
    });
    percentSelect.addEventListener("change", () => {
        ui.gel = percentSelect.value;
        renderGel(compute());
    });
    themeSelect.addEventListener("change", () => {
        ui.look = themeSelect.value;
        saveLook();
        renderGel(compute());
    });
    sizeSelect.addEventListener("change", () => {
        ui.size = sizeSelect.value;
        saveLook();
        renderGel(compute());
    });
    brightInput.addEventListener("input", () => {
        ui.bright = Number(brightInput.value);
        saveLook();
        renderGel(compute());
    });
    thickInput.addEventListener("input", () => {
        ui.thick = Number(thickInput.value);
        saveLook();
        renderGel(compute());
    });
    labelsBox.addEventListener("change", () => {
        ui.labels = labelsBox.checked;
        saveLook();
        renderGel(compute());
    });
    gelPng.addEventListener("click", downloadGel);
    clearButton.addEventListener("click", () => window.BiobankDigest.clear());

    if (window.ResizeObserver) {
        let lastWidth = 0;

        new ResizeObserver(() => {
            const width = Math.round(gelHost.clientWidth);

            if (mode === "digest" && width && Math.abs(width - lastWidth) > 3) {
                lastWidth = width;
                renderGel(compute());
            }
        }).observe(gelHost);
    }

    document.addEventListener("biobank:viewer-layout", event => {
        mode = event.detail.layout === "digest" ? "digest" : "map";

        if (mode === "digest") {
            renderAll();
        }

        publish();
    });
    root.addEventListener("biobank:molecular-workspace-change", () => {
        compute();

        if (picked.length && cache.key !== lastCut) {
            lastCut = cache.key;
            publish();
        }

        if (mode === "digest") schedule();
    });
}());
