/* Data submission package editor. */
(function () {
    "use strict";

    const root = document.getElementById("submission-editor");

    if (!root) return;

    const $ = (id) => document.getElementById(id);
    const apiUrl = root.dataset.apiUrl;
    const lookupUrl = root.dataset.lookupUrl;
    const csrf = () => (root.querySelector("input[name=csrfmiddlewaretoken]") || {}).value || "";
    const BADGE = {draft: "secondary", proposed: "warning", approved: "primary", published: "success", rejected: "danger"};
    const KIND_NAMES = {sequence: "a sequence record", structure: "a 3D structure", sample: "a sample", entry: "an ELN entry", notebook: "a Jupyter notebook", taxon: "a taxon"};

    let pkg = JSON.parse($("sp-data").textContent);
    let manifest = JSON.parse($("sp-manifest-data").textContent);
    let pickerKind = null;
    let pickerCallback = null;
    let pickerTimer = null;

    function esc(text) {
        const el = document.createElement("div");

        el.textContent = text == null ? "" : String(text);

        return el.innerHTML;
    }

    function showError(message) {
        $("sp-error").textContent = message || "";
        $("sp-error").hidden = !message;
    }

    async function act(payload) {
        showError("");

        const response = await fetch(apiUrl, {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({status: "error", message: "Unexpected response."}));

        if (data.status !== "success") {
            showError(data.message || "Could not save.");

            return null;
        }
        if (data.deleted) {
            window.location.href = root.dataset.listUrl;

            return data;
        }

        pkg = data.package;
        manifest = data.manifest || "";
        render();

        return data;
    }

    function button(label, cls, handler) {
        const el = document.createElement("button");

        el.type = "button";
        el.className = "btn btn-sm " + cls;
        el.textContent = label;
        el.addEventListener("click", handler);

        return el;
    }

    function render() {
        $("sp-title-text").textContent = pkg.title;
        $("sp-status").className = "badge text-bg-" + (BADGE[pkg.status] || "secondary");
        $("sp-status").textContent = pkg.status.charAt(0).toUpperCase() + pkg.status.slice(1);

        const note = $("sp-note");
        const notes = [];

        if (pkg.status === "rejected" && pkg.review_note) notes.push("Rejected: " + pkg.review_note);
        if (pkg.approved_by && ["approved", "published"].includes(pkg.status)) notes.push("Approved by " + pkg.approved_by + " on " + pkg.approved_at.replace("T", " ") + (pkg.review_note ? ". Note: " + pkg.review_note : ""));
        if (pkg.status === "proposed") notes.push("Waiting for review by someone allowed to approve submissions.");

        note.textContent = notes.join(" ");
        note.hidden = !notes.length;

        const form = $("sp-form");

        if (document.activeElement.closest && !document.activeElement.closest("#sp-form")) {
            $("sp-title").value = pkg.title;
            $("sp-description").value = pkg.description;
            $("sp-destination").value = pkg.destination;
            $("sp-workflow").value = pkg.workflow || "";
            ["license", "authors", "keywords", "funding"].forEach((k) => { $("sp-" + k).value = (pkg.metadata || {})[k] || ""; });
        }

        form.querySelectorAll("input,select,textarea,button").forEach((el) => { el.disabled = !pkg.can_edit; });
        $("sp-add-group").hidden = !pkg.can_edit;
        $("sp-taxon-set").hidden = !pkg.can_edit;
        $("sp-taxon-clear").hidden = !pkg.can_edit || !pkg.taxon_id;

        $("sp-taxon").innerHTML = pkg.taxon_id ? "<strong>" + esc(pkg.taxon_name) + "</strong> · NCBI taxid " + esc(pkg.taxon_id) + (pkg.taxonomy_version ? " · taxonomy " + esc(pkg.taxonomy_version) : "") : "<span class='text-muted'>No taxon chosen.</span>";
        $("sp-lineage").textContent = pkg.lineage.map((x) => x.name).join(" › ");

        const list = $("sp-items");

        list.innerHTML = pkg.items.length ? "" : "<li class='list-group-item small text-muted'>No records yet. Use the buttons above to add some.</li>";
        pkg.items.forEach((item) => {
            const li = document.createElement("li");

            li.className = "list-group-item d-flex justify-content-between align-items-center small";
            li.innerHTML = "<span><span class='badge text-bg-light border me-2'>" + esc(item.kind_label) + "</span>" + (item.url ? "<a href='" + esc(item.url) + "'>" + esc(item.label || "(removed)") + "</a>" : esc(item.label || "(removed)")) + "</span>";

            if (pkg.can_edit) li.appendChild(button("Remove", "btn-link text-danger p-0", () => act({action: "remove_item", item_id: item.id})));

            list.appendChild(li);
        });

        const actions = $("sp-actions");

        actions.innerHTML = "";

        if (pkg.can_edit) actions.appendChild(button(pkg.status === "rejected" ? "Propose again" : "Propose for review", "btn-primary", () => act({action: "propose"})));
        if (pkg.can_review) actions.appendChild(button("Review…", "btn-warning", () => bootstrap.Modal.getOrCreateInstance($("sp-review")).show()));
        if (pkg.can_publish) actions.appendChild(button(pkg.destination === "internal" ? "Publish to repository" : "Prepare files for upload", "btn-success", () => act({action: "publish"})));
        if (pkg.can_upload_zenodo) actions.appendChild(button("Create Zenodo draft", "btn-outline-success", () => { if (window.confirm("Create a draft on Zenodo with these files? It is not published until you publish it there.")) act({action: "upload_zenodo"}); }));
        if (pkg.can_delete) actions.appendChild(button("Delete", "btn-outline-danger", () => { if (window.confirm("Delete this package?")) act({action: "delete"}); }));

        const checks = $("sp-check-list");
        const problems = pkg.validation.errors.map((m) => ["text-danger", m]).concat(pkg.validation.warnings.map((m) => ["text-warning-emphasis", m]));

        checks.innerHTML = "";
        problems.forEach(([cls, msg]) => { const li = document.createElement("li"); li.className = cls; li.textContent = msg; checks.appendChild(li); });
        $("sp-checks").hidden = !problems.length || pkg.status === "published";

        $("sp-reference").hidden = !pkg.can_set_reference;

        if (document.activeElement !== $("sp-ref-input")) $("sp-ref-input").value = pkg.external_reference || "";

        $("sp-published-title").textContent = pkg.destination === "internal" ? "In the repository" : "Ready to upload (kept in the repository)";
        $("sp-published").hidden = !pkg.repository_path;
        $("sp-path").textContent = pkg.repository_path;
        $("sp-sha").textContent = pkg.manifest_sha256;
        $("sp-manifest").textContent = manifest || "";
    }

    $("sp-form").addEventListener("submit", (event) => {
        event.preventDefault();
        act({
            action: "update", title: $("sp-title").value, description: $("sp-description").value, destination: $("sp-destination").value,
            workflow: $("sp-workflow").value || null,
            metadata: {license: $("sp-license").value, authors: $("sp-authors").value, keywords: $("sp-keywords").value, funding: $("sp-funding").value},
        });
    });

    $("sp-approve").addEventListener("click", async () => {
        if (await act({action: "approve", note: $("sp-review-note").value})) bootstrap.Modal.getOrCreateInstance($("sp-review")).hide();
    });
    $("sp-reject").addEventListener("click", async () => {
        if (await act({action: "reject", note: $("sp-review-note").value})) bootstrap.Modal.getOrCreateInstance($("sp-review")).hide();
    });
    $("sp-ref-save").addEventListener("click", () => act({action: "set_reference", value: $("sp-ref-input").value}));
    $("sp-taxon-clear").addEventListener("click", () => act({action: "update", taxon_id: ""}));

    function openPicker(kind, callback) {
        pickerKind = kind;
        pickerCallback = callback;
        $("sp-picker-title").textContent = "Choose " + KIND_NAMES[kind];
        $("sp-picker-q").value = "";
        bootstrap.Modal.getOrCreateInstance($("sp-picker")).show();
        search();
    }

    async function search() {
        const response = await fetch(lookupUrl + "?" + new URLSearchParams({kind: pickerKind, q: $("sp-picker-q").value}));
        const data = response.ok ? await response.json() : {results: []};
        const list = $("sp-picker-results");

        list.innerHTML = data.results.length ? "" : "<div class='small text-muted p-2'>Nothing found.</div>";
        data.results.forEach((item) => {
            const b = document.createElement("button");

            b.type = "button";
            b.className = "list-group-item list-group-item-action small";
            b.textContent = item.label;
            b.addEventListener("click", () => {
                bootstrap.Modal.getOrCreateInstance($("sp-picker")).hide();
                pickerCallback(item.id);
            });
            list.appendChild(b);
        });
    }

    $("sp-picker-q").addEventListener("input", () => { clearTimeout(pickerTimer); pickerTimer = setTimeout(search, 250); });
    $("sp-add-group").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
        const kind = b.dataset.kind;

        openPicker(kind, (id) => act({action: "add_item", kind, ref: id}));
    }));
    $("sp-taxon-set").addEventListener("click", () => openPicker("taxon", (id) => act({action: "update", taxon_id: String(id)})));

    render();
})();
