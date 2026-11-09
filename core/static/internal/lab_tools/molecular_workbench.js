/*
 * Molecular Registry workbench layer.
 *
 * - Focus mode: hides the app menu and top bar so the work area uses the
 *   whole window.
 * - Rails: the tracks and inspector columns can be hidden.
 * - Modes: Map (the existing viewer) and Digest (enzymes, fragments, gel).
 *
 * Everything shares the workspace selection: clicking a fragment selects its
 * range through BiobankMolecularWorkspace, so the map, sequence, tracks and
 * inspector follow.
 */
(() => {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const body = root && root.querySelector(".mw-body");
    const main = root && root.querySelector(".mw-main");
    const panel = document.getElementById("mw-digest");
    const calc = window.BiobankDigestCalc;

    if (!root || !body || !main) return;

    const STORAGE_KEY = "biobank.molecular-workbench.v1";
    const NS = "http://www.w3.org/2000/svg";
    const COLORS = ["#1D4ED8", "#E8A100", "#2E9E6B", "#B58AE8", "#E5645A", "#0E7490"];
    const prefs = {focus: false, tracks: true, inspector: true};
    const chosen = new Set();
    let mode = "map";
    let filter = "unique";
    let queued = false;

    function load() {
        try {
            Object.assign(prefs, JSON.parse(
                window.localStorage.getItem(STORAGE_KEY) || "{}"
            ));
        } catch (error) {
            // Preferences are a convenience; the page works without them.
        }
    }

    function save() {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
        } catch (error) {
            // Storage can be blocked; ignore.
        }
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function svg(tag, attributes) {
        const node = document.createElementNS(NS, tag);

        Object.entries(attributes || {}).forEach(([key, value]) => {
            node.setAttribute(key, String(value));
        });

        return node;
    }

    const api = () => window.BiobankMolecularWorkspace;

    function applyLayout() {
        document.body.classList.toggle("mw-focus", prefs.focus);
        body.classList.toggle("is-tracks-hidden", !prefs.tracks);
        body.classList.toggle("is-inspector-hidden", !prefs.inspector);
        main.classList.toggle("is-digest", mode === "digest");
        root.classList.toggle("is-digest", mode === "digest");
        root.classList.toggle("is-metadata-hidden", mode !== "features");

        root.querySelectorAll("[data-mwb-focus]").forEach(button => {
            button.classList.toggle("is-active", prefs.focus);
            button.setAttribute("aria-pressed", String(prefs.focus));
        });
        root.querySelectorAll("[data-mwb-rail]").forEach(button => {
            const on = prefs[button.dataset.mwbRail];

            button.classList.toggle("is-active", Boolean(on));
            button.setAttribute("aria-pressed", String(Boolean(on)));
        });
        root.querySelectorAll("[data-mwb-mode]").forEach(button => {
            const on = button.dataset.mwbMode === mode;

            button.classList.toggle("is-active", on);
            button.setAttribute("aria-pressed", String(on));
        });

        if (panel) panel.hidden = mode !== "digest";
    }

    // The old "Viewer / Feature table / Sequence data" switcher stays in the
    // page (other scripts listen to it) but is hidden; these modes drive it.
    const LEGACY_VIEW = {
        map: "seqviz",
        structure: "secondary-structure",
        features: "construction",
        data: "sequence",
    };

    function setMode(next) {
        mode = next;

        if (LEGACY_VIEW[next]) {
            const legacy = root.querySelector(
                '[data-mw-view="' + LEGACY_VIEW[next] + '"]'
            );

            if (legacy) legacy.click();
        }

        applyLayout();

        if (mode === "digest") renderDigest();
    }

    function enzymeRow(item, circular) {
        const count = item.cuts.length;
        const row = el(
            "button",
            "mwd-enzyme" + (chosen.has(item.name) ? " is-on" : "")
        );

        row.type = "button";
        row.setAttribute("aria-pressed", String(chosen.has(item.name)));
        row.append(
            el("span", "mwd-check", chosen.has(item.name) ? "✓" : ""),
            el("b", "", item.name),
            el("span", "mwd-site", item.site),
            el("span", "mwd-count", count === 0 ? "no cut" : (
                count === 1 ? "1 cut · " + (item.cuts[0] || (circular ? 0 : 0))
                    : count + " cuts"
            ))
        );
        row.addEventListener("click", () => {
            if (chosen.has(item.name)) chosen.delete(item.name);
            else chosen.add(item.name);

            renderDigest();
        });

        return row;
    }

    function fragmentRow(fragment, index, total, unit) {
        const row = el("button", "mwd-fragment");

        row.type = "button";
        row.title = "Select this fragment";

        const bar = el("span", "mwd-bar");
        const fill = el("span", "mwd-fill");

        fill.style.width = Math.max(2, Math.round(fragment.length / total * 100)) + "%";
        fill.style.background = COLORS[index % COLORS.length];
        bar.append(fill);

        row.append(
            el("span", "mwd-range", fragment.start + "–" + fragment.end),
            bar,
            el("b", "mwd-size", fragment.length.toLocaleString("en-US") + " " + unit)
        );
        row.addEventListener("click", () => {
            const workspace = api();

            if (workspace) {
                workspace.selectSequenceRange(
                    fragment.start, fragment.end, {source: "digest"}
                );
            }
        });

        return row;
    }

    function gel(fragments, total) {
        const width = 270;
        const height = 310;
        const top = 34;
        const usable = height - top - 14;
        const svgNode = svg("svg", {
            viewBox: "0 0 " + width + " " + height,
            class: "mwd-gel",
            role: "img",
            "aria-label": "Simulated agarose gel",
        });
        const y = size => top + calc.gelPosition(size, 300, 12000) * usable;

        svgNode.append(svg("rect", {
            x: 0, y: 0, width, height, rx: 8, fill: "#12202E",
        }));

        [["Ladder", 48], ["Uncut", 134], ["Digest", 220]].forEach(([label, x]) => {
            const text = svg("text", {
                x, y: 20, "text-anchor": "middle", "font-size": 11,
                fill: "#9FB3C8", "font-family": "IBM Plex Sans, sans-serif",
            });

            text.textContent = label;
            svgNode.append(text);
        });

        calc.LADDER.forEach(size => {
            svgNode.append(svg("rect", {
                x: 22, y: y(size).toFixed(1), width: 52, height: 3, rx: 1.5,
                fill: "#C8D6E5", opacity: 0.85,
            }));

            const text = svg("text", {
                x: 80, y: (y(size) + 4).toFixed(1), "font-size": 9,
                fill: "#9FB3C8", "font-family": "IBM Plex Mono, monospace",
            });

            text.textContent = size >= 1000 ? (size / 1000) + "k" : String(size);
            svgNode.append(text);
        });

        svgNode.append(svg("rect", {
            x: 108, y: y(total).toFixed(1), width: 52, height: 4, rx: 1.5,
            fill: "#EAF2FA", opacity: 0.9,
        }));

        fragments.forEach(fragment => {
            svgNode.append(svg("rect", {
                x: 194, y: y(fragment.length).toFixed(1), width: 52,
                height: fragment.length > 1000 ? 4 : 3, rx: 1.5,
                fill: "#EAF2FA", opacity: 0.95,
            }));
        });

        return svgNode;
    }

    function renderDigest() {
        queued = false;

        if (!panel || mode !== "digest" || !calc) return;

        const workspace = api();

        if (!workspace) return;

        const snapshot = workspace.getSnapshot();
        const sequence = snapshot.sequence || "";
        const circular = snapshot.topology === "circular";
        const counts = calc.catalogCounts(sequence, circular);
        const picked = Array.from(chosen).filter(name => calc.byName(name));
        const fragments = picked.length
            ? calc.digest(sequence, picked, circular)
            : [];
        const unit = "bp";
        const listed = counts.filter(item => (
            chosen.has(item.name) ||
            filter === "all" ||
            (filter === "unique" && item.cuts.length === 1) ||
            (filter === "few" && item.cuts.length >= 1 && item.cuts.length <= 3)
        ));

        const left = el("section", "mwd-card");
        const head = el("div", "mwd-head");
        const select = el("select", "mwd-select");

        head.append(el("span", "mwd-label", "Enzymes"));

        [["unique", "Cut once"], ["few", "Cut 1–3 times"], ["all", "All"]].forEach(
            ([value, label]) => {
                const option = el("option", "", label);

                option.value = value;
                option.selected = filter === value;
                select.append(option);
            }
        );
        select.setAttribute("aria-label", "Which enzymes to list");
        select.addEventListener("change", () => {
            filter = select.value;
            renderDigest();
        });
        head.append(select);
        left.append(head);

        const list = el("div", "mwd-list");

        if (!listed.length) {
            list.append(el("p", "mwd-empty", "No enzyme matches this filter."));
        }

        listed.forEach(item => list.append(enzymeRow(item, circular)));
        left.append(list, el(
            "p", "mwd-note",
            "Palindromic sites only. Cut counts are for the " +
            (circular ? "circular" : "linear") + " molecule."
        ));

        const middle = el("section", "mwd-card");
        const title = el("div", "mwd-head");

        title.append(el(
            "span", "mwd-label",
            picked.length
                ? "Fragments · " + fragments.length
                : "Fragments"
        ));
        middle.append(title);

        if (!picked.length) {
            middle.append(el(
                "p", "mwd-empty",
                "Pick one or more enzymes on the left. Fragments and the gel update at once."
            ));
        } else {
            fragments.forEach((fragment, index) => {
                middle.append(fragmentRow(
                    fragment, index, sequence.length, unit
                ));
            });

            const copy = el("button", "mwd-action", "Copy fragment list");

            copy.type = "button";
            copy.addEventListener("click", () => {
                const text = fragments.map(item => (
                    item.start + "\t" + item.end + "\t" + item.length
                )).join("\n");

                if (navigator.clipboard) navigator.clipboard.writeText(text);
                copy.textContent = "Copied";
            });
            middle.append(copy);
        }

        const right = el("section", "mwd-card mwd-gelcard");

        right.append(
            el("span", "mwd-label", "Simulated gel"),
            gel(fragments, sequence.length),
            el("p", "mwd-note", "Band positions are computed from the fragment sizes (log scale).")
        );

        panel.replaceChildren(left, middle, right);
    }

    function schedule() {
        if (queued || mode !== "digest") return;

        queued = true;
        window.requestAnimationFrame(renderDigest);
    }

    function bind() {
        root.querySelectorAll("[data-mwb-mode]").forEach(button => {
            button.addEventListener("click", () => setMode(button.dataset.mwbMode));
        });
        root.querySelectorAll("[data-mwb-focus]").forEach(button => {
            button.addEventListener("click", () => {
                prefs.focus = !prefs.focus;
                save();
                applyLayout();
            });
        });
        root.querySelectorAll("[data-mwb-rail]").forEach(button => {
            button.addEventListener("click", () => {
                const key = button.dataset.mwbRail;

                prefs[key] = !prefs[key];
                save();
                applyLayout();
            });
        });

        root.addEventListener("biobank:molecular-workspace-change", schedule);
    }

    /*
     * Viewer bar. The page still contains three renderers (SeqViz, the
     * detailed map, the linear browser) with a toolbar each. Here they are
     * presented as one viewer: a layout switch picks the renderer, zoom works
     * on whichever is active, and the active renderer's own controls live in
     * "View options" instead of stacking above the map.
     */
    function bindViewerBar() {
        const zoomRange = document.getElementById("mw-seqviz-zoom");
        const modeSelect = document.getElementById("mw-seqviz-mode");
        const label = document.getElementById("mwv-zoom-label");
        const layoutButtons = root.querySelectorAll("[data-mwv-layout]");
        const zoomButtons = root.querySelectorAll("[data-mwv-zoom]");
        const zoomGroup = root.querySelector(".mwv-zoom");
        const menus = root.querySelectorAll(".mwv-more");
        const panelBody = root.querySelector(".mwv-view .mwv-more-panel");
        const isRna = root.dataset.sequenceType === "rna";
        const sections = {};
        const adopted = {detailed: false, linear: false};

        function section(name, title) {
            const box = el("div", "mwv-opts");

            box.dataset.mwvOpts = name;
            box.append(el("div", "mwv-opts-title", title));
            panelBody.append(box);
            sections[name] = box;

            return box;
        }

        if (panelBody) {
            const own = panelBody.querySelector(".mw-seqviz-controls");

            if (own) {
                const box = el("div", "mwv-opts");

                box.dataset.mwvOpts = "seqviz";
                panelBody.insertBefore(box, own);
                box.append(own);
                sections.seqviz = box;
            }

            section("detailed", "Map options");
            section("linear", "Sequence options");
        }

        const engineOf = () => {
            const active = root.querySelector(".mpm-view-button.is-active");

            return active ? active.dataset.mpmView : "seqviz";
        };

        function layoutOf(engine) {
            if (engine === "detailed") return "map";
            if (engine === "linear") return "seq";
            return isRna ? "seq" : "both";
        }

        function mapSvg() {
            return document.querySelector("#mw-detailed-plasmid-map svg");
        }

        function zoomText(engine) {
            if (engine === "seqviz" && zoomRange) return zoomRange.value + "%";

            const svgNode = mapSvg();
            const box = svgNode && svgNode.getAttribute("viewBox");

            if (engine === "detailed" && box) {
                const width = Number(box.split(/\s+/)[2]);

                if (width > 0) return Math.round(1000 / width * 100) + "%";
            }

            return "";
        }

        function sync() {
            const engine = engineOf();
            const layout = layoutOf(engine);

            layoutButtons.forEach(button => {
                const on = button.dataset.mwvLayout === layout;

                button.classList.toggle("is-active", on);
                button.setAttribute("aria-pressed", String(on));
            });

            Object.entries(sections).forEach(([name, box]) => {
                box.hidden = name !== engine;
            });

            if (zoomGroup) zoomGroup.hidden = engine === "linear";
            if (label) label.textContent = zoomText(engine) || "100%";
        }

        function chooseEngine(name) {
            const button = root.querySelector('[data-mpm-view="' + name + '"]');

            if (button) button.click();
            window.setTimeout(sync, 60);
        }

        layoutButtons.forEach(button => {
            button.addEventListener("click", () => {
                const layout = button.dataset.mwvLayout;

                if (layout === "map") {
                    chooseEngine("detailed");
                } else if (layout === "seq" && !isRna) {
                    chooseEngine("linear");
                } else {
                    chooseEngine("seqviz");

                    if (modeSelect) {
                        modeSelect.value = layout === "seq" ? "linear" : "both";
                        modeSelect.dispatchEvent(new Event("change", {bubbles: true}));
                    }
                }
            });
        });

        zoomButtons.forEach(button => {
            button.addEventListener("click", () => {
                const engine = engineOf();
                const step = button.dataset.mwvZoom;

                if (engine === "seqviz" && zoomRange) {
                    const next = step === "fit"
                        ? 50
                        : Math.max(0, Math.min(100, Number(zoomRange.value) + Number(step)));

                    zoomRange.value = String(next);
                    zoomRange.dispatchEvent(new Event("input", {bubbles: true}));
                } else if (engine === "detailed") {
                    if (step === "fit") {
                        const reset = document.getElementById("mpm-reset-view");

                        if (reset) reset.click();
                    } else if (mapSvg()) {
                        const rect = mapSvg().getBoundingClientRect();

                        mapSvg().dispatchEvent(new WheelEvent("wheel", {
                            deltaY: Number(step) > 0 ? -100 : 100,
                            clientX: rect.left + rect.width / 2,
                            clientY: rect.top + rect.height / 2,
                            bubbles: true,
                            cancelable: true,
                        }));
                    }
                }

                window.setTimeout(sync, 80);
            });
        });

        // Bring the other renderers' toolbars into View options once they exist.
        function adopt() {
            const shell = document.getElementById("mw-detailed-plasmid-map");

            if (shell && !adopted.detailed && shell.querySelector(".mpm-toolbar")) {
                [".mpm-toolbar", "#mpm-selected-enzymes-wrap", ".mpm-secondary-row"]
                    .forEach(selector => {
                        const node = shell.querySelector(selector);

                        if (node && sections.detailed) sections.detailed.append(node);
                    });
                adopted.detailed = true;
            }

            const linear = document.querySelector(".mlb-toolbar");

            if (linear && !adopted.linear && sections.linear) {
                sections.linear.append(linear);
                adopted.linear = true;
            }

            return adopted.detailed && adopted.linear;
        }

        let tries = 0;
        const timer = window.setInterval(() => {
            tries += 1;

            if (adopt() || tries > 60) window.clearInterval(timer);

            sync();
        }, 200);

        const switcher = root.querySelector(".mpm-view-switcher");

        if (switcher) {
            new MutationObserver(sync).observe(switcher, {
                subtree: true, attributes: true, attributeFilter: ["class"],
            });
        }

        [zoomRange, modeSelect].forEach(control => {
            if (control) {
                control.addEventListener("input", sync);
                control.addEventListener("change", sync);
            }
        });

        const reset = document.getElementById("mw-seqviz-reset");

        if (reset) reset.addEventListener("click", () => window.setTimeout(sync, 0));

        // One popover open at a time; closes on outside click or Escape.
        menus.forEach(menu => {
            menu.addEventListener("toggle", () => {
                if (menu.open) menus.forEach(other => {
                    if (other !== menu) other.open = false;
                });
            });
        });
        document.addEventListener("click", event => {
            menus.forEach(menu => {
                if (menu.open && !menu.contains(event.target)) menu.open = false;
            });
        });
        document.addEventListener("keydown", event => {
            if (event.key === "Escape") menus.forEach(menu => {
                menu.open = false;
            });
        });

        // Edit & export: the old "Sequence data" and annotation views stay
        // available, reached from here instead of from extra tabs.
        const press = id => {
            const node = document.getElementById(id);

            if (node) node.click();
        };
        const ACTIONS = {
            "edit-sequence": () => setMode("data"),
            "edit-annotations": () => setMode("features"),
            import: () => {
                setMode("data");
                window.setTimeout(() => press("mw-import-fasta"), 120);
            },
            copy: () => press("mw-copy"),
            fasta: () => press("mw-export-fasta"),
            genbank: () => press("mw-export-genbank"),
        };

        root.querySelectorAll("[data-mwv-act]").forEach(item => {
            item.addEventListener("click", () => {
                const run = ACTIONS[item.dataset.mwvAct];

                menus.forEach(menu => {
                    menu.open = false;
                });

                if (run) run();
            });
        });

        sync();
    }

    load();
    bind();
    bindViewerBar();
    applyLayout();
})();
