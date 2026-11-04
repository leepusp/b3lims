/* B3 Bench 1.A — Notebook entry composer.
 *
 * Custom fields (eLabFTW metadata.extra_fields), steps, linked entries,
 * custom ID, tags and rating. State comes from the
 * #nb-composer-state JSON script; every change is posted to the
 * composer API and the server's normalized state is rendered back.
 */
(function () {
    "use strict";

    const root = document.getElementById("nb-composer");
    const stateNode = document.getElementById("nb-composer-state");
    if (!root || !stateNode) return;

    let state = JSON.parse(stateNode.textContent || "null");
    if (!state) return;

    const canEdit = root.dataset.canEdit === "true";
    const urls = root.dataset;

    const TYPES = state.fields.types;
    const REFERENCE = new Set(["items", "compounds", "experiments", "users", "uploads"]);

    // --- helpers -----------------------------------------------------------

    function esc(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function csrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        if (match) return decodeURIComponent(match[1]);
        const input = document.querySelector("input[name=csrfmiddlewaretoken]");
        return input ? input.value : (window.csrfToken || "");
    }

    function toast(message, kind) {
        const status = document.getElementById("save-status");
        if (status) {
            status.textContent = message;
            status.classList.toggle("text-danger", kind === "error");
        }
        if (kind === "error") console.warn("[composer]", message);
    }

    function post(url, payload, onError) {
        toast("Saving…");
        return fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {"Content-Type": "application/json", "X-CSRFToken": csrfToken()},
            body: JSON.stringify(payload),
        })
            .then((r) => r.json().catch(() => ({status: "error", message: "HTTP " + r.status})))
            .then((data) => {
                if (data.status !== "success") {
                    toast(data.message || "Not saved", "error");
                    if (onError) onError(data.message || "Not saved");
                    else window.alert(data.message || "Not saved");
                    return null;
                }
                state = data.state;
                toast("Saved");
                renderAll();
                return state;
            });
    }

    function getJson(url) {
        return fetch(url, {credentials: "same-origin"}).then((r) => r.json());
    }

    function debounce(fn, ms) {
        let timer;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
    }

    function metadata() {
        return state.fields.metadata;
    }

    function cloneMetadata() {
        return JSON.parse(JSON.stringify(metadata()));
    }

    function saveMetadata(meta) {
        return post(urls.fieldsUrl, {metadata: meta});
    }

    // --- reference picker (samples, reagents, entries, users, files) --------

    function attachPicker(container, kind, onPick) {
        const input = container.querySelector(".nb-picker-input");
        const results = container.querySelector(".nb-picker-results");

        const search = debounce(function () {
            const q = input.value.trim();
            getJson(urls.lookupUrl + "?kind=" + encodeURIComponent(kind) + "&q=" + encodeURIComponent(q))
                .then((data) => {
                    const items = (data && data.results) || [];
                    results.innerHTML = items.length
                        ? items.map((item) =>
                            `<button type="button" class="list-group-item list-group-item-action py-1 small" data-id="${esc(item.id)}" data-label="${esc(item.label)}">${esc(item.label)}</button>`
                        ).join("")
                        : '<div class="list-group-item py-1 small text-muted">No matches</div>';
                    results.classList.remove("d-none");
                });
        }, 250);

        input.addEventListener("input", search);
        input.addEventListener("focus", search);
        results.addEventListener("click", function (event) {
            const button = event.target.closest("[data-id]");
            if (!button) return;
            results.classList.add("d-none");
            input.value = "";
            onPick(button.dataset.id, button.dataset.label);
        });
        document.addEventListener("click", function (event) {
            if (!container.contains(event.target)) results.classList.add("d-none");
        });
    }

    // --- header: custom ID, tags, rating ------------------------------------

    function renderHeader() {
        const customId = document.getElementById("nb-custom-id");
        if (customId && document.activeElement !== customId) customId.value = state.custom_id || "";

        const list = document.getElementById("nb-tag-list");
        if (list) {
            const favs = (state.favorite_tags || []).map((t) => t.toLowerCase());
            const tagHtml = state.tags.map((tag) => {
                const fav = favs.includes(tag.toLowerCase());
                return `<span class="nb-tag">#${esc(tag)}<button type="button" class="nb-tag-fav${fav ? " on" : ""}" data-tag="${esc(tag)}" data-fav="${fav ? 1 : 0}" title="${fav ? "Remove from favourites" : "Add to favourites"}" aria-label="Toggle favourite ${esc(tag)}"><i class="bi ${fav ? "bi-star-fill" : "bi-star"}"></i></button>${canEdit ? `<button type="button" class="nb-tag-remove" data-tag="${esc(tag)}" aria-label="Remove tag ${esc(tag)}">×</button>` : ""}</span>`;
            }).join("");
            const kwHtml = (state.keywords || []).map((kw) =>
                `<span class="nb-tag nb-keyword" title="Keyword">${esc(kw)}${canEdit ? `<button type="button" class="nb-keyword-remove" data-keyword="${esc(kw)}" aria-label="Remove keyword ${esc(kw)}">×</button>` : ""}</span>`
            ).join("");
            list.innerHTML = tagHtml + kwHtml || (canEdit ? "" : '<span class="text-muted">No tags</span>');
        }

        const quick = document.getElementById("nb-fav-tags");
        if (quick) {
            const free = (state.favorite_tags || []).filter((t) => !state.tags.some((x) => x.toLowerCase() === t.toLowerCase()));
            quick.innerHTML = canEdit && free.length
                ? '<span class="nb-fav-label"><i class="bi bi-star-fill"></i> Favourites</span>' + free.map((t) => `<button type="button" class="nb-fav-chip" data-tag="${esc(t)}">#${esc(t)}</button>`).join("")
                : "";
        }

        const rating = document.getElementById("nb-rating");
        if (rating) {
            rating.innerHTML = [1, 2, 3, 4, 5].map((n) =>
                `<button type="button" class="nb-star${n <= state.rating ? " on" : ""}" data-rating="${n}" ${canEdit ? "" : "disabled"} aria-label="${n} star${n > 1 ? "s" : ""}">★</button>`
            ).join("");
        }
    }

    function bindHeader() {
        if (!canEdit) return;

        const customId = document.getElementById("nb-custom-id");
        if (customId) {
            customId.addEventListener("change", () => post(urls.headerUrl, {custom_id: customId.value}));
        }

        const tagInput = document.getElementById("nb-tag-input");
        if (tagInput) {
            tagInput.addEventListener("keydown", function (event) {
                if (event.key !== "Enter" && event.key !== ",") return;
                event.preventDefault();
                const raw = tagInput.value.trim().replace(/^#/, "");
                if (!raw) { tagInput.value = ""; return; }
                tagInput.value = "";
                // "name: value" is a keyword, anything else is a tag.
                // ("project:x" with no space stays a tag.)
                if (/^[^:=]+(:\s+|\s*=\s*)\S/.test(raw)) {
                    if (!(state.keywords || []).includes(raw)) post(urls.headerUrl, {keywords: (state.keywords || []).concat([raw])});
                    return;
                }
                if (state.tags.some((t) => t.toLowerCase() === raw.toLowerCase())) return;
                post(urls.headerUrl, {tags: state.tags.concat([raw])});
            });
        }

        document.getElementById("nb-tag-list")?.addEventListener("click", function (event) {
            const fav = event.target.closest(".nb-tag-fav");
            if (fav) {
                post(urls.favoriteTagsUrl, {tag: fav.dataset.tag, favorite: fav.dataset.fav !== "1"});
                return;
            }
            const kw = event.target.closest(".nb-keyword-remove");
            if (kw) {
                post(urls.headerUrl, {keywords: (state.keywords || []).filter((k) => k !== kw.dataset.keyword)});
                return;
            }
            const button = event.target.closest(".nb-tag-remove");
            if (!button) return;
            post(urls.headerUrl, {tags: state.tags.filter((t) => t !== button.dataset.tag)});
        });

        document.getElementById("nb-fav-tags")?.addEventListener("click", function (event) {
            const chip = event.target.closest(".nb-fav-chip");
            if (!chip || state.tags.some((t) => t.toLowerCase() === chip.dataset.tag.toLowerCase())) return;
            post(urls.headerUrl, {tags: state.tags.concat([chip.dataset.tag])});
        });

        document.getElementById("nb-rating")?.addEventListener("click", function (event) {
            const star = event.target.closest("[data-rating]");
            if (!star) return;
            const value = Number(star.dataset.rating);
            post(urls.headerUrl, {rating: value === state.rating ? 0 : value});
        });
    }

    // --- custom fields ------------------------------------------------------

    function sortedFields() {
        return Object.entries(metadata().extra_fields || {})
            .sort((a, b) => (a[1].position || 0) - (b[1].position || 0));
    }

    function groups() {
        return (metadata().elabftw && metadata().elabftw.extra_fields_groups) || [];
    }

    function fieldInput(name, field) {
        const id = "nbf-" + btoa(unescape(encodeURIComponent(name))).replace(/[^a-z0-9]/gi, "");
        const disabled = canEdit ? "" : "disabled";
        const value = field.value == null ? "" : field.value;
        const type = field.type;

        if (REFERENCE.has(type)) {
            const label = state.fields.labels[name] || "";
            return `<div class="nb-picker nb-ref" data-kind="${esc(type)}" data-field="${esc(name)}">
                ${value !== "" ? `<div class="nb-ref-value"><i class="bi bi-link-45deg"></i> ${esc(label)}${canEdit ? ` <button type="button" class="btn btn-link btn-sm p-0 nb-ref-clear">clear</button>` : ""}</div>` : ""}
                ${canEdit ? `<input type="search" class="form-control form-control-sm nb-picker-input" placeholder="Search ${esc((TYPES[type] || type).toLowerCase())}…">
                <div class="nb-picker-results list-group d-none"></div>` : (value === "" ? '<span class="text-muted small">—</span>' : "")}
            </div>`;
        }

        if (type === "select") {
            const multi = field.allow_multi_values;
            const selected = multi ? (Array.isArray(value) ? value : []) : [value];
            return `<select id="${id}" class="form-select form-select-sm nb-field-input" data-field="${esc(name)}" ${multi ? `multiple size="${Math.min((field.options || []).length, 4)}"` : ""} ${disabled}>
                ${multi ? "" : '<option value="">—</option>'}
                ${(field.options || []).map((o) => `<option value="${esc(o)}" ${selected.includes(o) ? "selected" : ""}>${esc(o)}</option>`).join("")}
            </select>`;
        }

        if (type === "radio") {
            return `<div class="nb-radio-group">${(field.options || []).map((o, i) =>
                `<label class="form-check form-check-inline small mb-0">
                    <input class="form-check-input nb-field-input" type="radio" name="${id}" value="${esc(o)}" data-field="${esc(name)}" ${value === o ? "checked" : ""} ${disabled}>
                    <span class="form-check-label">${esc(o)}</span></label>`).join("")}</div>`;
        }

        if (type === "checkbox") {
            return `<div class="form-check form-switch mb-0"><input id="${id}" class="form-check-input nb-field-input" type="checkbox" data-field="${esc(name)}" ${value === "on" ? "checked" : ""} ${disabled}></div>`;
        }

        if (type === "number") {
            const units = field.units || [];
            return `<div class="input-group input-group-sm">
                <input id="${id}" type="number" step="any" class="form-control nb-field-input" data-field="${esc(name)}" value="${esc(value)}" ${disabled}>
                ${units.length > 1
                    ? `<select class="form-select nb-unit-input" data-field="${esc(name)}" ${disabled}>${units.map((u) => `<option ${u === field.unit ? "selected" : ""}>${esc(u)}</option>`).join("")}</select>`
                    : (field.unit ? `<span class="input-group-text">${esc(field.unit)}</span>` : "")}
            </div>`;
        }

        const htmlType = {"text": "text", "date": "date", "datetime-local": "datetime-local", "time": "time", "email": "email", "url": "url"}[type] || "text";
        return `<input id="${id}" type="${htmlType}" class="form-control form-control-sm nb-field-input" data-field="${esc(name)}" value="${esc(value)}" ${disabled}>`;
    }

    function fieldRow(name, field) {
        const missing = field.required && (field.value === "" || field.value == null || (Array.isArray(field.value) && !field.value.length));
        return `<div class="nb-field${missing ? " nb-field-missing" : ""}" data-field="${esc(name)}">
            <div class="nb-field-label">
                <span class="fw-semibold">${esc(name)}</span>${field.required ? '<span class="text-danger" title="Required"> *</span>' : ""}
                <span class="nb-field-type">${esc(TYPES[field.type] || field.type)}</span>
                ${field.description ? `<div class="small text-muted">${esc(field.description)}</div>` : ""}
            </div>
            <div class="nb-field-value">${fieldInput(name, field)}</div>
            ${canEdit ? `<div class="nb-field-actions">
                <button type="button" class="btn btn-sm btn-link text-secondary nb-field-up" title="Move up"><i class="bi bi-arrow-up"></i></button>
                <button type="button" class="btn btn-sm btn-link text-secondary nb-field-edit" title="Edit field"><i class="bi bi-pencil"></i></button>
                <button type="button" class="btn btn-sm btn-link text-danger nb-field-delete" title="Delete field"><i class="bi bi-trash"></i></button>
            </div>` : ""}
        </div>`;
    }

    function renderFields() {
        const fields = sortedFields();
        const container = document.getElementById("nb-fields");
        document.getElementById("nb-fields-count").textContent = fields.length;
        document.getElementById("nb-fields-empty").classList.toggle("d-none", fields.length > 0);

        const missingBadge = document.getElementById("nb-fields-missing");
        const missing = state.missing_required || [];
        missingBadge.classList.toggle("d-none", !missing.length);
        missingBadge.textContent = missing.length + " required field" + (missing.length > 1 ? "s" : "") + " empty";

        const sections = [{id: null, name: ""}].concat(groups());
        container.innerHTML = sections.map((group) => {
            const members = fields.filter(([, f]) => (f.group_id == null ? null : f.group_id) === group.id);
            if (group.id === null && !members.length) return "";
            return `<div class="nb-field-group" data-group="${group.id === null ? "" : esc(group.id)}">
                ${group.id === null ? "" : `<div class="nb-field-group-title">${esc(group.name)}
                    ${canEdit ? `<button type="button" class="btn btn-sm btn-link text-danger p-0 ms-2 nb-group-delete" data-group="${esc(group.id)}" title="Delete group (fields are kept)"><i class="bi bi-x-circle"></i></button>` : ""}
                </div>`}
                ${members.map(([n, f]) => fieldRow(n, f)).join("") || '<div class="small text-muted ps-2">No fields in this group.</div>'}
            </div>`;
        }).join("");

        if (canEdit) {
            container.querySelectorAll(".nb-ref").forEach(function (picker) {
                if (!picker.querySelector(".nb-picker-input")) return;
                attachPicker(picker, picker.dataset.kind, function (id) {
                    setFieldValue(picker.dataset.field, String(id));
                });
            });
        }
    }

    function setFieldValue(name, value, unit) {
        const meta = cloneMetadata();
        if (!meta.extra_fields[name]) return;
        meta.extra_fields[name].value = value;
        if (unit !== undefined) meta.extra_fields[name].unit = unit;
        saveMetadata(meta);
    }

    function bindFields() {
        if (!canEdit) return;
        const container = document.getElementById("nb-fields");

        container.addEventListener("change", function (event) {
            const target = event.target;
            const name = target.dataset.field;
            if (!name) return;

            if (target.classList.contains("nb-unit-input")) {
                const meta = cloneMetadata();
                meta.extra_fields[name].unit = target.value;
                saveMetadata(meta);
            } else if (target.type === "checkbox") {
                setFieldValue(name, target.checked ? "on" : "");
            } else if (target.multiple) {
                setFieldValue(name, Array.from(target.selectedOptions).map((o) => o.value));
            } else if (target.classList.contains("nb-field-input")) {
                setFieldValue(name, target.value);
            }
        });

        container.addEventListener("click", function (event) {
            const row = event.target.closest(".nb-field");
            if (event.target.closest(".nb-ref-clear")) {
                setFieldValue(event.target.closest(".nb-ref").dataset.field, "");
            } else if (event.target.closest(".nb-field-delete") && row) {
                if (!window.confirm(`Delete the field "${row.dataset.field}" and its value?`)) return;
                const meta = cloneMetadata();
                delete meta.extra_fields[row.dataset.field];
                saveMetadata(meta);
            } else if (event.target.closest(".nb-field-edit") && row) {
                openFieldEditor(row.dataset.field);
            } else if (event.target.closest(".nb-field-up") && row) {
                moveField(row.dataset.field);
            } else if (event.target.closest(".nb-group-delete")) {
                const groupId = Number(event.target.closest(".nb-group-delete").dataset.group);
                const meta = cloneMetadata();
                meta.elabftw.extra_fields_groups = groups().filter((g) => g.id !== groupId);
                Object.values(meta.extra_fields).forEach((f) => { if (f.group_id === groupId) delete f.group_id; });
                saveMetadata(meta);
            }
        });

        document.getElementById("nb-add-field").addEventListener("click", () => openFieldEditor(null));
        document.getElementById("nb-add-group").addEventListener("click", function () {
            const name = (window.prompt("Group name (e.g. Culture conditions)") || "").trim();
            if (!name) return;
            const meta = cloneMetadata();
            const ids = groups().map((g) => g.id);
            meta.elabftw.extra_fields_groups = groups().concat([{id: ids.length ? Math.max(...ids) + 1 : 1, name}]);
            saveMetadata(meta);
        });
        document.getElementById("nb-load-fields").addEventListener("click", openLoadPanel);
    }

    function orderedMetadata(entries) {
        const meta = cloneMetadata();
        meta.extra_fields = {};
        entries.forEach(([n, f], i) => { f.position = i; meta.extra_fields[n] = f; });
        return meta;
    }

    function moveField(name) {
        const entries = sortedFields().map(([n, f]) => [n, JSON.parse(JSON.stringify(f))]);
        const index = entries.findIndex(([n]) => n === name);
        if (index <= 0) return;
        [entries[index - 1], entries[index]] = [entries[index], entries[index - 1]];
        saveMetadata(orderedMetadata(entries));
    }

    function openFieldEditor(existingName) {
        const editor = document.getElementById("nb-field-editor");
        const field = existingName ? metadata().extra_fields[existingName] : {type: "text", required: false};
        const typeOptions = Object.entries(TYPES).map(([k, label]) =>
            `<option value="${esc(k)}" ${k === field.type ? "selected" : ""}>${esc(label)}</option>`).join("");
        const groupOptions = '<option value="">No group</option>' + groups().map((g) =>
            `<option value="${esc(g.id)}" ${g.id === field.group_id ? "selected" : ""}>${esc(g.name)}</option>`).join("");

        editor.innerHTML = `<div class="row g-2 align-items-end">
            <div class="col-md-4"><label class="form-label small mb-1">Name</label>
                <input type="text" class="form-control form-control-sm" id="nbe-name" maxlength="100" value="${esc(existingName || "")}" placeholder="e.g. Incubation temperature"></div>
            <div class="col-md-3"><label class="form-label small mb-1">Type</label>
                <select class="form-select form-select-sm" id="nbe-type">${typeOptions}</select></div>
            <div class="col-md-3"><label class="form-label small mb-1">Group</label>
                <select class="form-select form-select-sm" id="nbe-group">${groupOptions}</select></div>
            <div class="col-md-2"><div class="form-check mb-1"><input class="form-check-input" type="checkbox" id="nbe-required" ${field.required ? "checked" : ""}>
                <label class="form-check-label small" for="nbe-required">Required</label></div></div>
            <div class="col-md-6 nbe-choices"><label class="form-label small mb-1">Options (one per line)</label>
                <textarea class="form-control form-control-sm" id="nbe-options" rows="3">${esc((field.options || []).join("\n"))}</textarea>
                <div class="form-check nbe-multi"><input class="form-check-input" type="checkbox" id="nbe-multi" ${field.allow_multi_values ? "checked" : ""}>
                <label class="form-check-label small" for="nbe-multi">Allow several values</label></div></div>
            <div class="col-md-6 nbe-units"><label class="form-label small mb-1">Units (comma separated, e.g. °C, K)</label>
                <input type="text" class="form-control form-control-sm" id="nbe-units" value="${esc((field.units || []).join(", "))}"></div>
            <div class="col-12"><label class="form-label small mb-1">Description (optional)</label>
                <input type="text" class="form-control form-control-sm" id="nbe-description" maxlength="500" value="${esc(field.description || "")}"></div>
            <div class="col-12 d-flex gap-2">
                <button type="button" class="btn btn-sm btn-primary" id="nbe-save">${existingName ? "Save field" : "Add field"}</button>
                <button type="button" class="btn btn-sm btn-outline-secondary" id="nbe-cancel">Cancel</button>
            </div></div>`;
        editor.classList.remove("d-none");

        const typeSelect = editor.querySelector("#nbe-type");
        function toggleExtras() {
            const t = typeSelect.value;
            editor.querySelector(".nbe-choices").classList.toggle("d-none", !(t === "select" || t === "radio"));
            editor.querySelector(".nbe-multi").classList.toggle("d-none", t !== "select");
            editor.querySelector(".nbe-units").classList.toggle("d-none", t !== "number");
        }
        typeSelect.addEventListener("change", toggleExtras);
        toggleExtras();
        editor.querySelector("#nbe-name").focus();

        editor.querySelector("#nbe-cancel").addEventListener("click", () => editor.classList.add("d-none"));
        editor.querySelector("#nbe-save").addEventListener("click", function () {
            const name = editor.querySelector("#nbe-name").value.trim();
            if (!name) { window.alert("Give the field a name."); return; }
            if (name !== existingName && metadata().extra_fields[name]) { window.alert("A field with this name already exists."); return; }

            const type = typeSelect.value;
            const updated = {
                type,
                required: editor.querySelector("#nbe-required").checked,
                description: editor.querySelector("#nbe-description").value.trim(),
                value: (existingName && field.type === type) ? field.value : "",
            };
            const groupValue = editor.querySelector("#nbe-group").value;
            if (groupValue !== "") updated.group_id = Number(groupValue);
            if (type === "select" || type === "radio") {
                updated.options = editor.querySelector("#nbe-options").value.split("\n").map((s) => s.trim()).filter(Boolean);
                if (type === "select") updated.allow_multi_values = editor.querySelector("#nbe-multi").checked;
                if (updated.allow_multi_values && !Array.isArray(updated.value)) updated.value = updated.value ? [updated.value] : [];
                if (!updated.allow_multi_values && Array.isArray(updated.value)) updated.value = updated.value[0] || "";
            }
            if (type === "number") {
                updated.units = editor.querySelector("#nbe-units").value.split(",").map((s) => s.trim()).filter(Boolean);
                updated.unit = updated.units.includes(field.unit) ? field.unit : (updated.units[0] || "");
            }

            const entries = sortedFields().map(([n, f]) => [n, JSON.parse(JSON.stringify(f))]);
            const index = entries.findIndex(([n]) => n === existingName);
            if (index >= 0) entries[index] = [name, updated];
            else entries.push([name, updated]);

            saveMetadata(orderedMetadata(entries)).then((ok) => { if (ok) editor.classList.add("d-none"); });
        });
    }

    function openLoadPanel() {
        const panel = document.getElementById("nb-load-panel");
        panel.innerHTML = `<div class="small mb-1">Copy the field structure (not the values) of another entry:</div>
            <div class="nb-picker" data-kind="experiments">
                <input type="search" class="form-control form-control-sm nb-picker-input" placeholder="Search entries with fields to reuse">
                <div class="nb-picker-results list-group d-none"></div>
            </div>
            <button type="button" class="btn btn-sm btn-link px-0" id="nb-load-cancel">Cancel</button>`;
        panel.classList.remove("d-none");
        panel.querySelector("#nb-load-cancel").addEventListener("click", () => panel.classList.add("d-none"));
        attachPicker(panel.querySelector(".nb-picker"), "experiments", function (id, label) {
            getJson(urls.definitionsUrl.replace("/0/", "/" + id + "/")).then(function (data) {
                const source = data && data.metadata;
                const count = source ? Object.keys(source.extra_fields).length : 0;
                if (!count) { window.alert("That entry has no custom fields."); return; }

                const meta = cloneMetadata();
                const groupMap = {};
                let nextGroup = groups().reduce((m, g) => Math.max(m, g.id), 0) + 1;
                (source.elabftw.extra_fields_groups || []).forEach(function (g) {
                    const existing = meta.elabftw.extra_fields_groups.find((x) => x.name === g.name);
                    if (existing) groupMap[g.id] = existing.id;
                    else { groupMap[g.id] = nextGroup; meta.elabftw.extra_fields_groups.push({id: nextGroup++, name: g.name}); }
                });
                let added = 0;
                Object.entries(source.extra_fields).forEach(function ([n, f]) {
                    if (meta.extra_fields[n]) return;
                    if (f.group_id != null) f.group_id = groupMap[f.group_id];
                    f.position = 1000 + added;
                    meta.extra_fields[n] = f;
                    added += 1;
                });
                if (!added) { window.alert("All of those fields already exist here."); return; }
                saveMetadata(meta).then((ok) => { if (ok) panel.classList.add("d-none"); });
            });
        });
        panel.querySelector(".nb-picker-input").focus();
    }

    // --- steps ----------------------------------------------------------------

    function renderSteps() {
        const steps = state.steps;
        const done = steps.filter((s) => s.finished).length;
        document.getElementById("nb-steps-count").textContent = steps.length;
        document.getElementById("nb-steps-summary").textContent = steps.length ? `${done} of ${steps.length} done` : "";
        document.getElementById("nb-steps-bar").style.width = steps.length ? (100 * done / steps.length) + "%" : "0%";

        const now = new Date();
        const groups = Array.from(new Set(steps.map((s) => s.group).filter(Boolean)));
        const list = document.getElementById("nb-group-options");
        if (list) list.innerHTML = groups.map((g) => `<option value="${esc(g)}"></option>`).join("");

        let previous = null;
        document.getElementById("nb-steps").innerHTML = steps.map(function (step, index) {
            const overdue = step.deadline && !step.finished && new Date(step.deadline) < now;
            let heading = "";
            if (step.group !== previous) {
                previous = step.group;
                if (step.group) {
                    const members = steps.filter((s) => s.group === step.group);
                    const ready = members.filter((s) => s.finished).length;
                    heading = `<li class="nb-step-group" data-group="${esc(step.group)}">
                        <i class="bi bi-folder2-open"></i> <strong>${esc(step.group)}</strong>
                        <span class="small text-muted">${ready} of ${members.length} done</span>
                        ${canEdit ? `<span class="ms-auto">
                            <button type="button" class="btn btn-sm btn-link text-secondary nb-group-all" title="${ready === members.length ? "Untick all" : "Tick all"}"><i class="bi bi-check2-all"></i></button>
                            <button type="button" class="btn btn-sm btn-link text-secondary nb-group-rename" title="Rename group"><i class="bi bi-pencil"></i></button>
                        </span>` : ""}
                    </li>`;
                } else if (index > 0) {
                    heading = '<li class="nb-step-group nb-step-group-none"><span class="small text-muted">Other steps</span></li>';
                }
            }
            return heading + `<li class="nb-step${step.group ? " grouped" : ""}${step.finished ? " done" : ""}" data-step="${step.id}">
                <input class="form-check-input nb-step-check" type="checkbox" ${step.finished ? "checked" : ""} ${canEdit ? "" : "disabled"} aria-label="Done">
                <span class="nb-step-n">${index + 1}.</span>
                <span class="nb-step-body">${esc(step.body)}</span>
                ${step.deadline ? `<span class="badge ${overdue ? "text-bg-danger" : "text-bg-light"} nb-step-deadline-badge" title="Deadline"><i class="bi bi-alarm"></i> ${esc(step.deadline.replace("T", " "))}</span>` : ""}
                ${step.finished ? `<span class="small text-muted">✓ ${esc(step.finished_by || "")} · ${esc(step.finished_at || "")}</span>` : ""}
                ${canEdit ? `<span class="nb-step-actions ms-auto">
                    <button type="button" class="btn btn-sm btn-link text-secondary nb-step-up" title="Move up" ${index === 0 ? "disabled" : ""}><i class="bi bi-arrow-up"></i></button>
                    <button type="button" class="btn btn-sm btn-link text-secondary nb-step-edit" title="Edit"><i class="bi bi-pencil"></i></button>
                    <button type="button" class="btn btn-sm btn-link text-danger nb-step-delete" title="Delete"><i class="bi bi-trash"></i></button>
                </span>` : ""}
            </li>`;
        }).join("") || '<li class="text-muted small">No steps yet. Steps are the checklist of the experiment; each one records who finished it and when.</li>';
    }

    function bindSteps() {
        if (!canEdit) return;
        const form = document.getElementById("nb-step-form");
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            const body = document.getElementById("nb-step-body");
            const deadline = document.getElementById("nb-step-deadline");
            const group = document.getElementById("nb-step-group");
            post(urls.stepsUrl, {action: "add", body: body.value, deadline: deadline.value, group: group ? group.value : ""})
                .then((ok) => { if (ok) { body.value = ""; deadline.value = ""; body.focus(); } });
        });

        document.getElementById("nb-steps").addEventListener("click", function (event) {
            const head = event.target.closest(".nb-step-group");
            if (head && head.dataset.group) {
                const name = head.dataset.group;
                if (event.target.closest(".nb-group-rename")) {
                    const next = window.prompt("Group name (leave empty to remove the heading)", name);
                    if (next !== null) post(urls.stepsUrl, {action: "rename_group", group: name, new_name: next.trim()});
                } else if (event.target.closest(".nb-group-all")) {
                    const members = state.steps.filter((s) => s.group === name);
                    post(urls.stepsUrl, {action: "complete_group", group: name, finished: !members.every((s) => s.finished)});
                }
                return;
            }
            const row = event.target.closest(".nb-step");
            if (!row) return;
            const id = Number(row.dataset.step);
            if (event.target.classList.contains("nb-step-check")) {
                post(urls.stepsUrl, {action: "update", step_id: id, finished: event.target.checked});
            } else if (event.target.closest(".nb-step-delete")) {
                if (window.confirm("Delete this step?")) post(urls.stepsUrl, {action: "delete", step_id: id});
            } else if (event.target.closest(".nb-step-edit")) {
                const step = state.steps.find((s) => s.id === id);
                const body = window.prompt("Step", step.body);
                if (body === null || !body.trim()) return;
                const group = window.prompt("Group (leave empty for none)", step.group || "");
                post(urls.stepsUrl, {action: "update", step_id: id, body: body.trim(), group: group === null ? step.group : group.trim()});
            } else if (event.target.closest(".nb-step-up")) {
                const order = state.steps.map((s) => s.id);
                const i = order.indexOf(id);
                if (i > 0) { [order[i - 1], order[i]] = [order[i], order[i - 1]]; post(urls.stepsUrl, {action: "reorder", order}); }
            }
        });
    }

    // --- linked entries ---------------------------------------------------------

    function linkItem(link, removable) {
        const href = urls.entryUrl
            ? urls.entryUrl.replace("/0/", "/" + encodeURIComponent(link.id) + "/")
            : urls.notebookUrl + "?entry_id=" + encodeURIComponent(link.id);
        return `<li class="nb-link" data-target="${esc(link.id)}">
            <i class="bi bi-journal-text text-secondary"></i>
            <a href="${esc(href)}">${esc(link.label)}</a>
            <span class="badge text-bg-light">${esc(link.status)}</span>
            ${removable ? '<button type="button" class="btn btn-sm btn-link text-danger p-0 ms-auto nb-link-remove" title="Remove link"><i class="bi bi-x-lg"></i></button>' : ""}
        </li>`;
    }

    function renderLinks() {
        const out = state.links.outgoing;
        const incoming = state.links.incoming;
        document.getElementById("nb-links-count").textContent = out.length + incoming.length;
        document.getElementById("nb-links-out").innerHTML = out.map((l) => linkItem(l, canEdit)).join("")
            || '<li class="text-muted small">No linked entries. Link the lysate prep, the previous run or the analysis that follows.</li>';
        document.getElementById("nb-links-in").innerHTML = incoming.map((l) => linkItem(l, false)).join("");
        document.getElementById("nb-links-in-title").classList.toggle("d-none", !incoming.length);
    }

    function bindLinks() {
        if (!canEdit) return;
        attachPicker(document.getElementById("nb-link-picker"), "experiments", function (id) {
            post(urls.linksUrl, {action: "add", target_id: Number(id)});
        });
        document.getElementById("nb-links-out").addEventListener("click", function (event) {
            const button = event.target.closest(".nb-link-remove");
            if (!button) return;
            post(urls.linksUrl, {action: "remove", target_id: Number(button.closest(".nb-link").dataset.target)});
        });
    }

    // --- boot -------------------------------------------------------------------

    function renderAll() {
        renderHeader();
        renderFields();
        renderSteps();
        renderLinks();
    }

    renderAll();
    bindHeader();
    bindFields();
    bindSteps();
    bindLinks();
})();
