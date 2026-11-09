/*
 * Features window: every annotation of the record in one editable table.
 *
 * Edits go through window.BiobankMolecularWorkspace.updateFeature, so the map,
 * the sequence and the inspector follow and each change can be undone.
 */
(function () {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const pane = document.getElementById("mw-features");

    if (!root || !pane) {
        return;
    }

    const api = () => window.BiobankMolecularWorkspace || null;
    const ui = {query: "", sort: "position", open: false};
    let frame = 0;

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    const head = el("div", "mwp-head");
    const title = el("strong", "mwp-title", "Features");
    const filter = el("input", "mwp-filter");
    const sortSelect = el("select", "mwp-select");
    const addButton = el("button", "mwp-btn", "Add from selection");
    const csvButton = el("button", "mwp-btn", "CSV");
    const body = el("div", "mwp-scroll");
    const note = el("p", "mwp-note");

    filter.type = "search";
    filter.placeholder = "Filter by name or type";
    filter.setAttribute("aria-label", "Filter annotations");
    sortSelect.setAttribute("aria-label", "Sort annotations");
    [["position", "By position"], ["name", "By name"], ["size", "By size"], ["type", "By type"]].forEach(([value, label]) => {
        const option = el("option", "", label);

        option.value = value;
        sortSelect.append(option);
    });
    addButton.type = csvButton.type = "button";
    addButton.title = "Make the region selected on the map or in the sequence an annotation";
    csvButton.title = "Download the annotations as a table";
    head.append(title, filter, sortSelect, addButton, csvButton);
    pane.append(head, body, note);

    function size(feature, length) {
        return feature.start <= feature.end ? feature.end - feature.start + 1 : length - feature.start + feature.end + 1;
    }

    function input(type, value, onChange, extra) {
        const node = el("input", "mwp-cell");

        node.type = type;
        node.value = value;
        Object.assign(node, extra || {});
        node.addEventListener("change", () => onChange(node.value));
        node.addEventListener("keydown", event => {
            event.stopPropagation();

            if (event.key === "Enter") node.blur();
        });

        return node;
    }

    function selectCell(options, value, onChange) {
        const node = el("select", "mwp-cell");

        options.forEach(item => {
            const option = el("option", "", item.label);

            option.value = item.value;
            option.selected = item.value === value;
            node.append(option);
        });
        node.addEventListener("change", () => onChange(node.value));

        return node;
    }

    function sorted(features, length) {
        const rows = features.map((feature, index) => ({feature, index}));
        const by = {
            position: (a, b) => a.feature.start - b.feature.start || a.index - b.index,
            name: (a, b) => String(a.feature.name).localeCompare(String(b.feature.name)),
            size: (a, b) => size(b.feature, length) - size(a.feature, length),
            type: (a, b) => String(a.feature.type).localeCompare(String(b.feature.type)) || a.feature.start - b.feature.start,
        };

        return rows.sort(by[ui.sort] || by.position);
    }

    function render() {
        frame = 0;

        const workspace = api();

        if (!workspace || pane.hidden) return;

        const snapshot = workspace.getSnapshot();
        const length = snapshot.sequence.length;
        const query = ui.query.trim().toLowerCase();
        const editable = Boolean(snapshot.canEdit);
        const types = workspace.featureTypes ? workspace.featureTypes() : [];
        const rows = sorted(snapshot.features, length).filter(({feature}) => (
            !query || String(feature.name).toLowerCase().includes(query) || String(feature.type).toLowerCase().includes(query)
        ));
        const table = el("table", "mwp-table");
        const header = el("tr");

        ["", "Name", "Type", "Strand", "Start", "End", "Size", ""].forEach(label => header.append(el("th", "", label)));
        const thead = el("thead");

        thead.append(header);
        table.append(thead);

        const tbody = el("tbody");

        rows.forEach(({feature, index}) => {
            const row = el("tr", snapshot.selectedFeature === index ? "is-selected" : "");
            const patch = field => value => workspace.updateFeature(index, {[field]: value}, {source: "features-window"});
            const color = input("color", /^#[0-9a-f]{6}$/i.test(feature.color) ? feature.color : "#868e96", patch("color"));
            const name = input("text", feature.name, patch("name"));
            const type = selectCell(types.length ? types : [{value: feature.type, label: feature.type}], feature.type, patch("type"));
            const strand = selectCell([{value: "+", label: "+"}, {value: "-", label: "−"}, {value: ".", label: "·"}], feature.strand, patch("strand"));
            const start = input("number", feature.start, patch("start"), {min: 1, max: length});
            const end = input("number", feature.end, patch("end"), {min: 1, max: length});
            const remove = el("button", "mwp-icon", "✕");

            [color, name, type, strand, start, end].forEach(node => {
                node.disabled = !editable;
            });
            color.className = "mwp-color";
            remove.type = "button";
            remove.title = "Delete this annotation";
            remove.disabled = !editable;
            remove.addEventListener("click", event => {
                event.stopPropagation();
                workspace.removeFeature(index, {source: "features-window"});
            });
            row.addEventListener("click", event => {
                if (event.target === row || event.target.tagName === "TD") workspace.selectFeature(index);
            });
            name.addEventListener("focus", () => {
                if (snapshot.selectedFeature !== index) workspace.selectFeature(index);
            });

            [color, name, type, strand, start, end].forEach(node => {
                const cell = el("td");

                cell.append(node);
                row.append(cell);
            });
            row.append(el("td", "mwp-size", size(feature, length).toLocaleString() + " bp"));

            const last = el("td");

            last.append(remove);
            row.append(last);
            tbody.append(row);
        });

        table.append(tbody);

        const active = document.activeElement;
        const keep = active && pane.contains(active) && active.classList.contains("mwp-filter");

        body.replaceChildren(rows.length ? table : el("p", "mwp-empty", query ? "No annotation matches the filter." : "No annotations yet. Select a region on the map or in the sequence and use “Add from selection”."));
        title.textContent = "Features · " + snapshot.features.length;
        addButton.disabled = !editable || !snapshot.sequenceSelection || Number.isInteger(snapshot.sequenceSelection.featureIndex);
        note.textContent = editable
            ? "Edit a cell and press Enter. Every change can be undone from the edit bar. Click a row to select it on the map."
            : "Read only: you can look and select but not edit this record.";

        if (keep) filter.focus();
    }

    function schedule() {
        if (!frame) frame = window.requestAnimationFrame(render);
    }

    filter.addEventListener("input", () => {
        ui.query = filter.value;
        render();
    });
    sortSelect.addEventListener("change", () => {
        ui.sort = sortSelect.value;
        render();
    });
    addButton.addEventListener("click", () => {
        const workspace = api();

        if (workspace) workspace.createFeatureFromSelection({name: "New annotation", type: "custom", focusEditor: false});
    });
    csvButton.addEventListener("click", () => {
        const workspace = api();

        if (!workspace) return;

        const snapshot = workspace.getSnapshot();
        const cell = value => (/[",\n]/.test(String(value)) ? '"' + String(value).replace(/"/g, '""') + '"' : String(value));
        const lines = [["name", "type", "strand", "start", "end", "length_bp", "color", "notes"]].concat(snapshot.features.map(feature => [
            feature.name, feature.type, feature.strand, feature.start, feature.end, size(feature, snapshot.sequence.length), feature.color, feature.notes || "",
        ]));
        const link = document.createElement("a");

        link.href = URL.createObjectURL(new Blob([lines.map(line => line.map(cell).join(",")).join("\n") + "\n"], {type: "text/csv"}));
        link.download = (snapshot.name || "record").replace(/[^A-Za-z0-9._-]+/g, "_") + "_features.csv";
        document.body.append(link);
        link.click();
        link.remove();
    });

    document.addEventListener("biobank:viewer-layout", event => {
        if (event.detail.layout === "features") window.requestAnimationFrame(render);
    });
    root.addEventListener("biobank:molecular-workspace-change", event => {
        const active = document.activeElement;

        // Do not rebuild the table under a cell that is being typed in.
        if (active && pane.contains(active) && active.classList.contains("mwp-cell") && event.detail && event.detail.reason === "selection") return;

        schedule();
    });
}());
