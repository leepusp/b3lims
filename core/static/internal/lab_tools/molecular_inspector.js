/*
 * Molecular Registry inspector.
 *
 * A read-mostly side panel that follows whatever is selected in the
 * workspace (feature or sequence range), whichever view made the selection.
 * It only listens to `biobank:molecular-workspace-change` and calls the
 * public window.BiobankMolecularWorkspace API, so it works for every type.
 */
(() => {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const host = document.getElementById("mw-inspector");
    const calc = window.BiobankMolecularCalc;

    if (!root || !host || !calc) return;

    const NUCLEOTIDE = ["dna", "rna", "plasmid", "primer", "insert"];
    let context = {};

    try {
        context = JSON.parse(
            document.getElementById("mw-inspector-context").textContent
        ) || {};
    } catch (error) {
        context = {};
    }

    const api = () => window.BiobankMolecularWorkspace;

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function row(label, value, hint) {
        const wrapper = el("div", "mwi-row");

        wrapper.append(el("span", "mwi-label", label));

        const strong = el("strong", "mwi-value", value);

        if (hint) strong.title = hint;
        wrapper.append(strong);

        return wrapper;
    }

    function section(title) {
        const wrapper = el("section", "mwi-section");

        wrapper.append(el("h3", "mwi-title", title));

        return wrapper;
    }

    function copyButton(label, getText) {
        const button = el("button", "btn btn-sm btn-outline-secondary", label);

        button.type = "button";
        button.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(getText());
                button.textContent = "Copied";
            } catch (error) {
                button.textContent = "Copy failed";
            }

            setTimeout(() => { button.textContent = label; }, 1400);
        });

        return button;
    }

    function unitFor(type) {
        return type === "protein" ? "aa" : (type === "rna" ? "nt" : "bp");
    }

    function resolveSelection(snapshot) {
        const features = snapshot.features || [];
        const index = snapshot.selectedFeature;

        if (Number.isInteger(index) && index >= 0 && features[index]) {
            const feature = features[index];

            return {
                kind: "feature",
                name: feature.name,
                featureType: feature.type || feature.feature_type || "",
                strand: feature.strand,
                start: Number(feature.start),
                end: Number(feature.end),
            };
        }

        const range = snapshot.sequenceSelection;

        if (range && range.start && range.end) {
            return {
                kind: "range",
                start: Number(range.start),
                end: Number(range.end),
            };
        }

        return null;
    }

    function recordSection(snapshot) {
        const box = section("Record");

        box.append(row("Name", snapshot.name || "—"));
        box.append(row(
            "Type",
            snapshot.sequenceType +
            (NUCLEOTIDE.includes(snapshot.sequenceType)
                ? " · " + snapshot.topology : "")
        ));

        const info = context || {};

        if (info.sample && info.sample.id) {
            const line = el("div", "mwi-link");

            line.append(el("i", "bi bi-box-seam me-1"));

            if (info.sample.url) {
                const anchor = el("a", "", info.sample.id);

                anchor.href = info.sample.url;
                line.append(anchor);
            } else {
                line.append(document.createTextNode(info.sample.id));
            }

            box.append(line);
        }

        if (info.place) {
            const line = el("div", "mwi-link text-muted");

            line.append(el("i", "bi bi-geo-alt me-1"));

            if (info.place_url) {
                const anchor = el("a", "", info.place);

                anchor.href = info.place_url;
                line.append(anchor);
            } else {
                line.append(document.createTextNode(info.place));
            }

            if (info.place_position) {
                line.append(document.createTextNode(" · " + info.place_position));
            }

            box.append(line);
        }

        if (info.entries) {
            box.append(row("ELN entries", String(info.entries)));
        }

        if (info.duplicates && info.duplicates.length) {
            const warn = el("div", "mwi-warning");

            warn.append(el("i", "bi bi-copy me-1"));
            warn.append(document.createTextNode(
                "Same sequence as: "
            ));

            info.duplicates.forEach((item, position) => {
                const anchor = el("a", "", item.name);

                anchor.href = item.url;
                warn.append(anchor);

                if (position < info.duplicates.length - 1) {
                    warn.append(document.createTextNode(", "));
                }
            });

            box.append(warn);
        }

        return box;
    }

    function nucleotideFacts(box, seq, type, whole) {
        const gc = calc.gcPercent(seq);

        if (gc !== null) box.append(row("GC", gc + "%"));

        const tm = calc.meltingTemperature(seq);

        if (tm !== null && (type === "primer" || !whole)) {
            box.append(row(
                "Tm",
                tm + " °C",
                "Nearest-neighbour (SantaLucia 1998), 50 mM Na⁺, 250 nM strand"
            ));
        }

        if (type === "primer") {
            const checks = calc.primerChecks(seq);

            box.append(row(
                "3′ clamp",
                checks.clampGc + " G/C in last 5",
                "Two or three G/C in the last five bases is usually good"
            ));
            box.append(row("Longest run", checks.longestRun + " nt"));
        }
    }

    function selectionSection(snapshot, selection) {
        const type = snapshot.sequenceType;
        const unit = unitFor(type);
        const whole = !selection;
        const box = section(whole ? "Whole molecule" : (
            selection.kind === "feature"
                ? "Selected feature" : "Selected region"
        ));
        const seq = whole
            ? snapshot.sequence
            : calc.slice(snapshot.sequence, selection.start, selection.end);

        if (!seq) {
            box.append(el("p", "mwi-empty", "No sequence to analyse."));
            return box;
        }

        if (!whole) {
            if (selection.kind === "feature") {
                box.append(row("Name", selection.name || "—"));

                if (selection.featureType) {
                    box.append(row("Kind", selection.featureType));
                }
            }

            box.append(row("Range", selection.start + "–" + selection.end));
        } else {
            box.append(el(
                "p",
                "mwi-hint",
                "Click a feature or drag a region in any view to inspect it here."
            ));
        }

        box.append(row("Length", seq.length + " " + unit));

        if (type === "protein") {
            const props = calc.proteinProperties(seq);

            if (props) {
                box.append(row("Mass", (props.massDa / 1000).toFixed(2) + " kDa"));
                box.append(row("pI", String(props.isoelectricPoint)));
                box.append(row("Charge pH 7.4", String(props.chargeAt74)));
                box.append(row("ε280", props.extinction280 + " M⁻¹cm⁻¹",
                    "Pace method, reduced cysteines excluded unless paired"));
            }
        } else {
            nucleotideFacts(box, seq, type, whole);
        }

        const actions = el("div", "mwi-actions");

        actions.append(copyButton("Copy sequence", () => seq));

        if (type !== "protein") {
            actions.append(copyButton(
                "Copy reverse complement",
                () => calc.reverseComplement(seq, type === "rna")
            ));

            if (!whole && seq.length >= 6 && type !== "primer") {
                actions.append(copyButton(
                    "Copy translation",
                    () => calc.translate(seq, 0)
                ));
            }
        }

        const workspace = api();

        if (
            !whole && selection.kind === "range" &&
            snapshot.canEdit && workspace &&
            typeof workspace.createFeatureFromSelection === "function"
        ) {
            const create = el("button", "btn btn-sm btn-primary", "Make it a feature");

            create.type = "button";
            create.addEventListener("click", () => {
                workspace.createFeatureFromSelection();
            });
            actions.append(create);
        }

        box.append(actions);

        if (!whole && type !== "protein" && seq.length >= 9) {
            const peptide = calc.translate(seq, 0);
            const preview = peptide.length > 48
                ? peptide.slice(0, 48) + "…" : peptide;

            box.append(row("Frame 1", preview));
        }

        return box;
    }

    function orfSection(snapshot) {
        const type = snapshot.sequenceType;

        if (
            type === "protein" || type === "primer" ||
            !snapshot.sequence || snapshot.sequence.length < 100
        ) return null;

        const orf = calc.longestOrf(snapshot.sequence, 30);

        if (!orf) return null;

        const box = section("Longest forward ORF");

        box.append(row("Range", orf.start + "–" + orf.end));
        box.append(row("Protein", orf.aminoAcids + " aa · frame " + orf.frame));

        const workspace = api();

        if (workspace && typeof workspace.selectSequenceRange === "function") {
            const go = el("button", "btn btn-sm btn-outline-primary", "Select ORF");

            go.type = "button";
            go.addEventListener("click", () => {
                workspace.selectSequenceRange(orf.start, orf.end, {source: "inspector"});
            });
            box.append(go);
        }

        return box;
    }

    let queued = false;

    /*
     * The annotation editor used to float over the page. It is created
     * lazily by the workspace, so dock it under the inspector the first
     * time it exists; the editor and the inspector then read as one panel.
     */
    function dockEditor() {
        const dock = document.getElementById("mw-inspector-editor");
        const drawer = document.getElementById("mw-annotation-drawer");

        if (dock && drawer && drawer.parentElement !== dock) {
            dock.appendChild(drawer);
        }
    }

    function render() {
        queued = false;
        dockEditor();

        const workspace = api();

        if (!workspace) return;

        const snapshot = workspace.getSnapshot();
        const selection = resolveSelection(snapshot);

        host.replaceChildren(
            recordSection(snapshot),
            selectionSection(snapshot, selection)
        );

        const orf = selection ? null : orfSection(snapshot);

        if (orf) host.append(orf);
    }

    function schedule() {
        if (queued) return;

        queued = true;
        window.requestAnimationFrame(render);
    }

    root.addEventListener("biobank:molecular-workspace-change", schedule);

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", schedule);
    } else {
        schedule();
    }

    window.addEventListener("load", schedule);
})();
