/*
 * Molecular Registry workbench layer.
 *
 * - Focus mode: hides the app menu and top bar so the work area uses the
 *   whole window.
 * - Rails: the tracks and inspector columns can be hidden.
 * - Modes: Map (the viewer, whose layouts include Digest: molecular_digest.js).
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

    if (!root || !body || !main) return;

    const STORAGE_KEY = "biobank.molecular-workbench.v1";
    const prefs = {focus: false, tracks: true, inspector: true};
    let mode = "map";

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
        const card = root.querySelector(".mw-seqviz-card");
        const canvasApi = () => window.BiobankMapCanvas || null;
        const canvasHost = document.getElementById("mmc");
        const seqHost = document.getElementById("msc");
        const split = document.getElementById("mw-split");
        const seqApi = () => window.BiobankSeqCanvas || null;
        let currentLayout = isRna ? "seq" : "both";

        function canvasOn() {
            return Boolean(canvasHost && canvasApi() && canvasApi().active());
        }

        function seqOn() {
            return Boolean(seqHost && seqApi() && seqApi().active());
        }

        function anyCanvas() {
            return canvasOn() || seqOn();
        }

        // What sits left of a window (Digest, Features, ORFs): the map, the sequence, or nothing.
        const store = {
            get(key, fallback) {
                try {
                    return window.localStorage.getItem("biobank.viewer." + key) || fallback;
                } catch (error) {
                    return fallback;
                }
            },
            set(key, value) {
                try {
                    window.localStorage.setItem("biobank.viewer." + key, String(value));
                } catch (error) {
                    // Not persisted; fine.
                }
            },
        };
        let paneLeft = ["map", "seq", "none"].includes(store.get("left", "map")) ? store.get("left", "map") : "map";
        let leftPct = Math.max(20, Math.min(65, Number(store.get("leftpct", "42")) || 42));
        const divider = el("div", "mw-divider");
        const grip = el("div", "mw-grip");
        const dividerButtons = {};

        divider.hidden = true;
        divider.setAttribute("role", "separator");
        divider.setAttribute("aria-orientation", "vertical");
        grip.title = "Drag to resize, double-click to reset";
        divider.append(grip);
        [["map", "Map", "Show the map next to this window"], ["seq", "Sequence", "Show the sequence next to this window"], ["none", "Hide", "Give the whole width to this window"]].forEach(([key, label, title]) => {
            const button = el("button", "mw-divbtn", label);

            button.type = "button";
            button.title = title;
            button.addEventListener("click", () => {
                paneLeft = key;
                store.set("left", key);
                applyCanvases();
            });
            dividerButtons[key] = button;
            divider.append(button);
        });

        if (split && seqHost) seqHost.after(divider);

        grip.addEventListener("pointerdown", event => {
            const box = split.getBoundingClientRect();

            grip.setPointerCapture(event.pointerId);
            split.classList.add("is-resizing");

            const move = moveEvent => {
                leftPct = Math.max(20, Math.min(65, (moveEvent.clientX - box.left) / box.width * 100));
                split.style.setProperty("--mw-left", leftPct.toFixed(1) + "%");
            };
            const stop = () => {
                grip.removeEventListener("pointermove", move);
                grip.removeEventListener("pointerup", stop);
                grip.removeEventListener("pointercancel", stop);
                split.classList.remove("is-resizing");
                store.set("leftpct", leftPct.toFixed(1));
            };

            grip.addEventListener("pointermove", move);
            grip.addEventListener("pointerup", stop);
            grip.addEventListener("pointercancel", stop);
        });
        grip.addEventListener("dblclick", () => {
            leftPct = 42;
            split.style.setProperty("--mw-left", "42%");
            store.set("leftpct", "42");
        });

        // The layout decides which interactive canvases are shown.
        function applyCanvases() {
            const usable = Boolean(canvasHost && seqHost && canvasApi() && seqApi());
            const PANES = {digest: "mw-digest", features: "mw-features", orfs: "mw-orfs"};
            const inPane = usable && currentLayout in PANES;
            const mapWanted = usable && (currentLayout === "map" || currentLayout === "both" || (inPane && paneLeft === "map"));
            const seqWanted = usable && (currentLayout === "seq" || currentLayout === "both" || (inPane && paneLeft === "seq"));

            if (card) card.classList.toggle("is-canvas", mapWanted || seqWanted || inPane);
            if (split) {
                split.classList.toggle("is-both", mapWanted && seqWanted);
                split.classList.toggle("is-pane", inPane);
                split.classList.toggle("is-leftless", inPane && paneLeft === "none");
                split.style.setProperty("--mw-left", leftPct.toFixed(1) + "%");
            }

            divider.hidden = !(usable && (inPane || (mapWanted && seqWanted)));
            divider.classList.toggle("is-simple", !inPane);
            Object.entries(dividerButtons).forEach(([key, button]) => {
                button.hidden = !inPane;
                button.classList.toggle("is-active", key === paneLeft);
                button.setAttribute("aria-pressed", String(key === paneLeft));
            });

            if (canvasApi()) canvasApi().setActive(mapWanted);
            if (seqApi()) seqApi().setActive(seqWanted);

            Object.entries(PANES).forEach(([layout, id]) => {
                const pane = document.getElementById(id);

                if (pane) pane.hidden = !(usable && currentLayout === layout);
            });

            document.dispatchEvent(new CustomEvent("biobank:viewer-layout", {detail: {layout: currentLayout}}));
        }

        const setCanvas = () => applyCanvases();

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
            const layout = canvasHost && seqHost ? currentLayout : layoutOf(engine);

            layoutButtons.forEach(button => {
                const on = button.dataset.mwvLayout === layout;

                button.classList.toggle("is-active", on);
                button.setAttribute("aria-pressed", String(on));
            });

            Object.entries(sections).forEach(([name, box]) => {
                box.hidden = anyCanvas() || name !== engine;
            });

            if (zoomGroup) zoomGroup.hidden = engine === "linear" && !anyCanvas();
            if (label) {
                label.textContent = seqOn()
                    ? seqApi().zoomPercent() + "%"
                    : canvasOn()
                        ? canvasApi().zoomPercent() + "%"
                        : (zoomText(engine) || "100%");
            }
        }

        function chooseEngine(name) {
            const button = root.querySelector('[data-mpm-view="' + name + '"]');

            if (button) button.click();
            window.setTimeout(sync, 60);
        }

        layoutButtons.forEach(button => {
            button.addEventListener("click", () => {
                const layout = button.dataset.mwvLayout;

                currentLayout = layout;
                applyCanvases();

                // Nucleotide records have no other renderer to switch to.
                if (canvasHost && seqHost) {
                    sync();

                    return;
                }

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

                if (anyCanvas()) {
                    const target = seqOn() ? seqApi() : canvasApi();

                    if (step === "fit") target.fit();
                    else if (Number(step) > 0) target.zoomIn();
                    else target.zoomOut();
                } else if (engine === "seqviz" && zoomRange) {
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

        if (canvasHost) canvasHost.addEventListener("mmc:zoom", sync);
        if (seqHost) seqHost.addEventListener("msc:zoom", sync);

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
        // The map image is drawn from the record, whichever layout is showing.
        const imageExport = kind => {
            const maps = canvasApi();
            const snapshot = api() ? api().getSnapshot() : null;
            const base = snapshot && snapshot.name ? snapshot.name : "map";

            if (maps && maps.downloadImage) maps.downloadImage(kind, base + "_map");
        };
        const ACTIONS = {
            "edit-sequence": () => setMode("data"),
            "edit-annotations": () => setMode("features"),
            import: () => {
                if (canvasHost && seqHost) {
                    press("mw-import-fasta");

                    return;
                }

                setMode("data");
                window.setTimeout(() => press("mw-import-fasta"), 120);
            },
            copy: () => press("mw-copy"),
            fasta: () => press("mw-export-fasta"),
            genbank: () => press("mw-export-genbank"),
            "image-svg": () => imageExport("svg"),
            "image-png": () => imageExport("png"),
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

        applyCanvases();
        sync();
    }

    load();
    bind();
    bindViewerBar();
    applyLayout();
})();
