/* B3 ELN entry page (releases 2.0 and 2.1).
 *
 * Document-centred editor after Benchling and eLabFTW: entry navigator,
 * open-entry tabs, TinyMCE 6 with a Biobank menu, Jspreadsheet tables with
 * formulas, Relevant items and Files. Custom fields, steps, entry links,
 * tags, custom ID and rating are handled by notebook_composer_v1.js.
 * 2.1 adds exclusive edit, revisions with compare/restore, comments and
 * file versions.
 */
(function () {
    "use strict";

    const stateNode = document.getElementById("bx-state");
    if (!stateNode) return;
    const state = JSON.parse(stateNode.textContent);
    const canEdit = state.can_edit;
    const urls = state.urls;
    const entryId = state.entry.id;
    const shell = document.getElementById("bx-shell");
    const saveStatus = document.getElementById("save-status");
    let lockToken = "";
    let editorRef = null;

    // ---------------------------------------------------------------- helpers

    function esc(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function csrf() {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : (window.csrfToken || "");
    }

    function status(text, isError) {
        if (!saveStatus) return;
        saveStatus.textContent = text;
        saveStatus.classList.toggle("text-danger", !!isError);
    }

    function postJson(url, payload) {
        return fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: Object.assign({"Content-Type": "application/json", "X-CSRFToken": csrf()}, lockToken ? {"X-Lock-Token": lockToken} : {}),
            body: JSON.stringify(payload),
        }).then((r) => r.json().catch(() => ({status: "error", message: "HTTP " + r.status})));
    }

    function getJson(url) {
        return fetch(url, {credentials: "same-origin"}).then((r) => r.json());
    }

    function debounce(fn, ms) {
        let timer;
        const wrapped = function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), ms);
        };
        wrapped.flush = function (...args) { clearTimeout(timer); fn.apply(this, args); };
        return wrapped;
    }

    const store = {
        get(key, fallback) {
            try { const v = window.localStorage.getItem("b3eln." + key); return v === null ? fallback : JSON.parse(v); }
            catch (e) { return fallback; }
        },
        set(key, value) {
            try { window.localStorage.setItem("b3eln." + key, JSON.stringify(value)); } catch (e) { /* storage unavailable */ }
        },
    };

    function entryUrl(id) {
        return urls.entry.replace("/0/", "/" + id + "/");
    }

    // ---------------------------------------------------------------- entry update

    let pending = 0;
    function updateEntry(fields) {
        if (!canEdit) return Promise.resolve(null);
        pending += 1;
        status("Saving…");
        return postJson(urls.update, fields).then(function (data) {
            pending -= 1;
            if (data.status === "locked") { lockLost({holder: data.holder}, true); status("Not saved: edited elsewhere", true); return null; }
            if (data.status !== "success") { status(data.message || "Not saved", true); return null; }
            status("Saved " + data.updated_at.slice(11));
            const updated = document.getElementById("bx-updated");
            if (updated) updated.textContent = data.updated_at;
            return data;
        }).catch(function () { pending -= 1; status("Offline — not saved", true); });
    }

    window.addEventListener("beforeunload", function (event) {
        if (pending > 0) { event.preventDefault(); event.returnValue = ""; }
    });

    // ---------------------------------------------------------------- navigator & tabs

    function initNavigator() {
        const filter = document.getElementById("bx-nav-filter");
        const chips = Array.from(document.querySelectorAll("#bx-nav-types .bx-chip"));
        const items = Array.from(document.querySelectorAll("#bx-nav-list .bx-nav-item"));
        let type = "";

        function apply() {
            const q = (filter.value || "").trim().toLowerCase();
            items.forEach(function (item) {
                const show = (!type || item.dataset.type === type) && (!q || item.dataset.search.includes(q));
                item.classList.toggle("d-none", !show);
            });
        }
        filter.addEventListener("input", apply);
        chips.forEach(function (chip) {
            chip.addEventListener("click", function () {
                chips.forEach((c) => c.classList.toggle("on", c === chip));
                type = chip.dataset.type;
                apply();
            });
        });

        const active = document.querySelector("#bx-nav-list .bx-nav-item.active");
        if (active) active.scrollIntoView({block: "nearest"});

        if (store.get("navHidden", false)) shell.classList.add("nav-hidden");
        document.getElementById("bx-nav-collapse").addEventListener("click", function () {
            shell.classList.add("nav-hidden"); store.set("navHidden", true);
        });
        document.getElementById("bx-nav-open").addEventListener("click", function () {
            shell.classList.remove("nav-hidden"); store.set("navHidden", false);
        });

        if (store.get("infoHidden", false)) shell.classList.add("info-hidden");
        document.getElementById("bx-info-toggle").addEventListener("click", function () {
            shell.classList.toggle("info-hidden");
            store.set("infoHidden", shell.classList.contains("info-hidden"));
        });
    }

    function initTabs() {
        const list = document.getElementById("bx-tabs-list");
        let tabs = store.get("openTabs", []).filter((t) => t && t.id);
        const current = {id: entryId, title: state.entry.title, custom_id: state.entry.custom_id};
        const index = tabs.findIndex((t) => t.id === entryId);
        if (index >= 0) tabs[index] = current; else tabs.unshift(current);
        tabs = tabs.slice(0, 8);
        store.set("openTabs", tabs);

        function render() {
            list.innerHTML = tabs.map(function (t) {
                return `<a class="bx-tab${t.id === entryId ? " active" : ""}" href="${esc(entryUrl(t.id))}" title="${esc(t.title)}">
                    <i class="bi bi-file-earmark-text"></i><span>${esc(t.title)}</span>
                    <button type="button" class="bx-tab-close" data-close="${esc(t.id)}" aria-label="Close tab">×</button></a>`;
            }).join("");
        }
        render();

        list.addEventListener("click", function (event) {
            const close = event.target.closest("[data-close]");
            if (!close) return;
            event.preventDefault();
            const id = Number(close.dataset.close);
            const position = tabs.findIndex((t) => t.id === id);
            tabs = tabs.filter((t) => t.id !== id);
            store.set("openTabs", tabs);
            if (id === entryId) {
                const next = tabs[Math.min(position, tabs.length - 1)];
                window.location.href = next ? entryUrl(next.id) : urls.dashboard;
            } else {
                render();
            }
        });

        window.bxRenameTab = function (title) {
            const t = tabs.find((x) => x.id === entryId);
            if (t) { t.title = title; store.set("openTabs", tabs); render(); }
            const navName = document.querySelector("#bx-nav-list .bx-nav-item.active .bx-nav-name");
            if (navName) navName.textContent = title;
        };
    }

    // ---------------------------------------------------------------- section panes

    function initSections() {
        const buttons = Array.from(document.querySelectorAll(".bx-section"));
        const panes = Array.from(document.querySelectorAll(".bx-pane"));
        function show(name) {
            buttons.forEach((b) => b.classList.toggle("on", b.dataset.pane === name));
            panes.forEach((p) => p.classList.toggle("on", p.dataset.pane === name));
            store.set("pane", name);
            if (name === "notes") sheets.forEach((s) => s.refresh && s.refresh());
        }
        buttons.forEach((b) => b.addEventListener("click", () => show(b.dataset.pane)));
        let requested = null;
        try { requested = new URLSearchParams(window.location.search).get("tab"); } catch (e) { /* ignore */ }
        const remembered = requested || store.get("pane", "notes");
        if (buttons.some((b) => b.dataset.pane === remembered)) show(remembered);

        // Mirror the composer counters into the section bar.
        const mirrors = [
            ["nb-fields-count", "bx-count-fields"],
            ["nb-steps-count", "bx-count-steps"],
        ];
        function sync() {
            mirrors.forEach(function ([from, to]) {
                const source = document.getElementById(from);
                const target = document.getElementById(to);
                if (source && target) target.textContent = source.textContent && source.textContent !== "0" ? source.textContent : "";
            });
            const done = document.getElementById("nb-steps-summary");
            const bar = document.getElementById("nb-steps-bar");
            const infoBar = document.getElementById("bx-info-steps-bar");
            const infoText = document.getElementById("bx-info-steps");
            if (bar && infoBar) infoBar.style.width = bar.style.width;
            if (done && infoText) infoText.textContent = done.textContent || "No steps";
            const missing = document.getElementById("nb-fields-missing");
            const infoMissing = document.getElementById("bx-info-missing");
            if (missing && infoMissing) {
                infoMissing.textContent = missing.classList.contains("d-none") ? "" : "⚠ " + missing.textContent;
            }
        }
        const observer = new MutationObserver(sync);
        ["nb-fields-count", "nb-steps-count", "nb-steps-summary", "nb-fields-missing"].forEach(function (id) {
            const el = document.getElementById(id);
            if (el) observer.observe(el, {childList: true, characterData: true, subtree: true, attributes: true});
        });
        sync();
    }

    // ---------------------------------------------------------------- header fields

    function initHeader() {
        const title = document.getElementById("bx-title");
        const saveTitle = debounce(function () {
            const value = title.value.trim() || "Untitled entry";
            updateEntry({title: value}).then(() => window.bxRenameTab && window.bxRenameTab(value));
        }, 700);
        title.addEventListener("input", saveTitle);
        title.addEventListener("keydown", function (event) {
            if (event.key === "Enter") { event.preventDefault(); saveTitle.flush(); if (window.tinymce && tinymce.activeEditor) tinymce.activeEditor.focus(); }
        });

        const statusSelect = document.getElementById("bx-status");
        const statusPill = document.getElementById("bx-status-pill");
        statusSelect.addEventListener("change", function () {
            statusPill.className = "bx-pill bx-status bx-status-" + statusSelect.value;
            updateEntry({status: statusSelect.value});
        });
        document.getElementById("bx-type").addEventListener("change", (e) => updateEntry({entry_type: e.target.value}));
        document.getElementById("bx-visibility").addEventListener("change", (e) => updateEntry({visibility: e.target.value}));
        document.getElementById("bx-date").addEventListener("change", (e) => updateEntry({experiment_date: e.target.value || null}));
        const project = document.getElementById("bx-project");
        if (project) project.addEventListener("change", () => updateEntry({project: project.value}));

        const pin = document.getElementById("bx-pin");
        let pinned = state.pinned;
        function renderPin() {
            pin.classList.toggle("on", pinned);
            pin.innerHTML = `<i class="bi bi-pin-angle${pinned ? "-fill" : ""}"></i>`;
            pin.title = pinned ? "Unpin from your dashboard" : "Pin to your dashboard";
        }
        renderPin();
        pin.addEventListener("click", function () {
            postJson(urls.batch, {action: pinned ? "unpin" : "pin", ids: [entryId]}).then(function (data) {
                if (data.status === "success") { pinned = !pinned; renderPin(); }
            });
        });

        document.getElementById("bx-duplicate").addEventListener("click", function () {
            if (!window.confirm("Create a copy of this entry (text, fields, steps, tags and spreadsheets)?")) return;
            postJson(urls.duplicate, {}).then(function (data) {
                if (data.status === "success") window.location.href = data.url;
                else window.alert(data.message || "Could not duplicate");
            });
        });

        document.getElementById("bx-print").addEventListener("click", () => window.print());
    }

    // ---------------------------------------------------------------- table of contents

    function renderToc(root) {
        const toc = document.getElementById("bx-toc");
        if (!toc || !root) return;
        const headings = Array.from(root.querySelectorAll("h1, h2, h3"));
        toc.innerHTML = headings.length
            ? headings.map((h, i) => `<li><a href="#" data-h="${i}" class="${h.tagName === "H3" ? "h3" : ""}">${esc(h.textContent.trim() || "—")}</a></li>`).join("")
            : '<li class="bx-hint">Headings in the notes appear here.</li>';
        toc.onclick = function (event) {
            const link = event.target.closest("[data-h]");
            if (!link) return;
            event.preventDefault();
            const target = headings[Number(link.dataset.h)];
            if (target) target.scrollIntoView({behavior: "smooth", block: "start"});
        };
    }

    // ---------------------------------------------------------------- reference modal

    const REF_KINDS = {
        samples: {title: "Insert a sample", search: (q) => urls.relevant + "?kind=samples&q=" + encodeURIComponent(q), chip: "items", link: "samples"},
        chemicals: {title: "Insert a reagent / compound", search: (q) => urls.relevant + "?kind=chemicals&q=" + encodeURIComponent(q), chip: "compounds", link: "chemicals"},
        molecules: {title: "Insert a molecular record", search: (q) => urls.relevant + "?kind=molecules&q=" + encodeURIComponent(q), chip: "molecules", link: "molecules"},
        entries: {title: "Insert a link to another entry", search: (q) => urls.lookup + "?kind=experiments&q=" + encodeURIComponent(q), chip: "experiments", link: "entries"},
    };

    function openReferenceModal(kind, editor) {
        const config = REF_KINDS[kind];
        const modalEl = document.getElementById("bx-ref-modal");
        const input = document.getElementById("bx-ref-search");
        const results = document.getElementById("bx-ref-results");
        document.getElementById("bx-ref-title").textContent = config.title;
        input.value = "";
        results.innerHTML = "";
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

        const search = debounce(function () {
            getJson(config.search(input.value.trim())).then(function (data) {
                const items = (data && data.results) || [];
                results.innerHTML = items.length
                    ? items.map((i) => `<button type="button" class="list-group-item list-group-item-action small" data-id="${esc(i.id)}" data-label="${esc(i.label)}">${esc(i.label)}</button>`).join("")
                    : '<div class="list-group-item small text-muted">No matches</div>';
            });
        }, 250);
        input.oninput = search;
        results.onclick = function (event) {
            const button = event.target.closest("[data-id]");
            if (!button) return;
            const id = button.dataset.id;
            const label = button.dataset.label.split(" · ")[0];
            const href = kind === "entries" ? entryUrl(id) : "";
            const chip = href
                ? `<a class="b3-ref" data-kind="${config.chip}" data-id="${esc(id)}" href="${esc(href)}">${esc(label)}</a>&nbsp;`
                : `<span class="b3-ref" data-kind="${config.chip}" data-id="${esc(id)}" contenteditable="false">${esc(label)}</span>&nbsp;`;
            editor.insertContent(chip);
            if (document.getElementById("bx-ref-link").checked) {
                if (kind === "entries") {
                    postJson(document.getElementById("nb-composer").dataset.linksUrl, {action: "add", target_id: Number(id)})
                        .then(() => window.location.hash = "");
                } else {
                    postJson(urls.relevant, {action: "link", kind: config.link, id: Number(id)}).then(function (data) {
                        if (data.status === "success") { state.relevant = data.relevant; renderRelevant(); }
                    });
                }
            }
            modal.hide();
        };
        modal.show();
        modalEl.addEventListener("shown.bs.modal", () => { input.focus(); search(); }, {once: true});
    }

    // ---------------------------------------------------------------- TinyMCE

    function initEditor() {
        const textarea = document.getElementById("bx-editor");
        if (!textarea) {
            renderToc(document.querySelector(".bx-readonly-body"));
            return;
        }
        if (!window.tinymce) {
            document.getElementById("bx-editor-loading").textContent = "The editor could not be loaded.";
            return;
        }

        const saveContent = debounce(function (editor) {
            if (!editor.isDirty()) return;
            editor.setDirty(false);
            updateEntry({content: editor.getContent()});
        }, 1200);

        tinymce.init({
            target: textarea,
            base_url: window.B3_TINYMCE_BASE,
            suffix: ".min",
            promotion: false,
            branding: false,
            license_key: "gpl",
            height: 640,
            min_height: 420,
            resize: true,
            menubar: "file edit view insert format tools table biobank",
            menu: {
                file: {title: "File", items: "preview print | b3duplicate"},
                biobank: {title: "Biobank", items: "b3sample b3reagent b3molecule b3entry | b3sheet | b3stamp"},
            },
            plugins: "advlist anchor autolink charmap code codesample emoticons fullscreen help image insertdatetime link lists nonbreaking pagebreak preview quickbars searchreplace table visualblocks visualchars wordcount",
            toolbar: "undo redo | blocks fontsize | bold italic underline strikethrough superscript subscript | forecolor backcolor | alignleft aligncenter alignright alignjustify | bullist numlist checklist outdent indent | b3refs table image link codesample | charmap emoticons b3stamp | searchreplace removeformat | code fullscreen",
            toolbar_mode: "sliding",
            toolbar_sticky: false,
            quickbars_selection_toolbar: "bold italic underline | forecolor backcolor | quicklink h2 h3 blockquote",
            quickbars_insert_toolbar: false,
            contextmenu: "link image table",
            insertdatetime_formats: ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%H:%M:%S", "%d/%m/%Y"],
            table_default_styles: {"border-collapse": "collapse", width: "100%"},
            table_header_type: "sectionCells",
            codesample_languages: [
                {text: "Plain text", value: "none"}, {text: "Python", value: "python"}, {text: "R", value: "r"},
                {text: "Bash", value: "bash"}, {text: "JSON", value: "json"}, {text: "SQL", value: "sql"},
            ],
            relative_urls: false,
            convert_urls: false,
            paste_data_images: true,
            automatic_uploads: true,
            images_reuse_filename: true,
            images_upload_handler: function (blobInfo) {
                const form = new FormData();
                form.append("file", blobInfo.blob(), blobInfo.filename());
                form.append("caption", "Image in notes");
                return fetch(urls.upload, {method: "POST", credentials: "same-origin", headers: {"X-CSRFToken": csrf()}, body: form})
                    .then((r) => r.json())
                    .then(function (data) {
                        if (data.status !== "success") throw new Error(data.message || "Upload failed");
                        refreshFiles();
                        return data.url;
                    });
            },
            content_css: window.B3_CONTENT_CSS,
            content_style: "",
            extended_valid_elements: "span[class|data-kind|data-id|contenteditable|style],a[class|data-kind|data-id|href|target|rel|title]",
            setup: function (editor) {
                editorRef = editor;
                editor.ui.registry.addMenuItem("b3sample", {text: "Sample…", icon: "user", onAction: () => openReferenceModal("samples", editor)});
                editor.ui.registry.addMenuItem("b3reagent", {text: "Reagent / compound…", icon: "color-swatch", onAction: () => openReferenceModal("chemicals", editor)});
                editor.ui.registry.addMenuItem("b3molecule", {text: "Molecular record…", icon: "code-sample", onAction: () => openReferenceModal("molecules", editor)});
                editor.ui.registry.addMenuItem("b3entry", {text: "Link to another entry…", icon: "link", onAction: () => openReferenceModal("entries", editor)});
                editor.ui.registry.addMenuItem("b3sheet", {text: "Spreadsheet with formulas", icon: "table", onAction: addSheet});
                editor.ui.registry.addMenuItem("b3duplicate", {text: "Duplicate entry", icon: "copy", onAction: () => document.getElementById("bx-duplicate").click()});
                editor.ui.registry.addButton("b3stamp", {
                    icon: "insert-time", tooltip: "Insert a date/time stamp with your name",
                    onAction: function () {
                        const now = new Date();
                        const pad = (n) => String(n).padStart(2, "0");
                        const stamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
                        editor.insertContent(`<strong>[${esc(stamp)} · ${esc(state.user || "")}]</strong>&nbsp;`);
                    },
                });
                editor.ui.registry.addMenuItem("b3stamp", {
                    text: "Date/time stamp", icon: "insert-time",
                    onAction: () => editor.execCommand("mceInsertDate"),
                });
                editor.ui.registry.addMenuButton("b3refs", {
                    text: "Biobank", icon: "bookmark", tooltip: "Insert a reference to a Biobank record",
                    fetch: function (callback) {
                        callback([
                            {type: "menuitem", text: "Sample…", onAction: () => openReferenceModal("samples", editor)},
                            {type: "menuitem", text: "Reagent / compound…", onAction: () => openReferenceModal("chemicals", editor)},
                            {type: "menuitem", text: "Molecular record…", onAction: () => openReferenceModal("molecules", editor)},
                            {type: "menuitem", text: "Another entry…", onAction: () => openReferenceModal("entries", editor)},
                            {type: "separator"},
                            {type: "menuitem", text: "Spreadsheet with formulas", onAction: addSheet},
                        ]);
                    },
                });
                // Checklist as a simple bullet list styled with checkboxes.
                editor.ui.registry.addButton("checklist", {
                    icon: "checklist", tooltip: "Checklist",
                    onAction: () => editor.insertContent('<ul class="b3-checklist"><li>☐&nbsp;</li></ul>'),
                });

                editor.on("init", function () {
                    const loading = document.getElementById("bx-editor-loading");
                    if (loading) loading.remove();
                    if (readOnly) editor.mode.set("readonly");
                    renderToc(editor.getBody());
                });
                let ready = false;
                editor.on("init", () => { setTimeout(() => { ready = true; }, 300); });
                editor.on("input change undo redo", function () {
                    if (!ready || !editor.isDirty()) return;
                    status("Editing…");
                    saveContent(editor);
                    renderTocSoon(editor);
                });
                editor.on("blur", () => saveContent.flush(editor));
                editor.addShortcut("meta+s", "Save", () => saveContent.flush(editor));
            },
        });

        const renderTocSoon = debounce((editor) => renderToc(editor.getBody()), 600);
    }

    // ---------------------------------------------------------------- spreadsheets

    const sheets = [];

    function sheetDimensions(data) {
        const rows = data.length;
        const cols = data.reduce((m, r) => Math.max(m, r.length), 0);
        return `${rows} row${rows === 1 ? "" : "s"} × ${cols} column${cols === 1 ? "" : "s"}`;
    }

    function mountSheet(sheet) {
        const container = document.getElementById("bx-sheets");
        const wrapper = document.createElement("div");
        wrapper.className = "bx-sheet";
        wrapper.dataset.sheet = sheet.id;
        wrapper.innerHTML = `
            <div class="bx-sheet-head">
                <i class="bi bi-table text-success"></i>
                <input class="bx-sheet-title" value="${esc(sheet.title)}" maxlength="120" ${canEdit ? "" : "readonly"} aria-label="Spreadsheet title">
                ${canEdit ? `<button type="button" class="btn btn-sm btn-outline-secondary" data-act="row" title="Add a row"><i class="bi bi-plus"></i> Row</button>
                <button type="button" class="btn btn-sm btn-outline-secondary" data-act="col" title="Add a column"><i class="bi bi-plus"></i> Column</button>` : ""}
                <button type="button" class="btn btn-sm btn-outline-secondary" data-act="csv" title="Download as CSV"><i class="bi bi-download"></i></button>
                ${canEdit ? `<button type="button" class="btn btn-sm btn-outline-danger" data-act="delete" title="Delete spreadsheet"><i class="bi bi-trash"></i></button>` : ""}
            </div>
            <div class="bx-sheet-body"><div class="bx-sheet-grid"></div></div>
            <div class="bx-sheet-foot"><span class="bx-sheet-size"></span><span>Formulas: <code>=A1+B1</code> <code>=SUM(B2:B6)</code> <code>=AVERAGE()</code> <code>=B3*$B$1</code></span><span class="bx-sheet-state ms-auto"></span></div>`;
        container.appendChild(wrapper);

        const grid = wrapper.querySelector(".bx-sheet-grid");
        const sizeLabel = wrapper.querySelector(".bx-sheet-size");
        const stateLabel = wrapper.querySelector(".bx-sheet-state");
        let instance;

        const save = debounce(function () {
            const data = instance.getData();
            const widths = (instance.getWidth ? instance.getWidth() : []) || [];
            stateLabel.textContent = "Saving…";
            postJson(urls.sheets, {action: "save", sheet_id: sheet.id, data: data, column_widths: widths}).then(function (r) {
                stateLabel.textContent = r.status === "success" ? "Saved" : (r.message || "Not saved");
                sizeLabel.textContent = sheetDimensions(data);
            });
        }, 800);

        const data = (sheet.data && sheet.data.length) ? sheet.data : [["", "", "", ""]];
        const columns = (sheet.column_widths || []).map((w) => ({width: w}));
        const options = {
            data: data,
            minDimensions: [4, 6],
            defaultColWidth: 140,
            tableOverflow: true,
            tableWidth: "100%",
            tableHeight: "460px",
            editable: canEdit,
            allowInsertRow: canEdit,
            allowInsertColumn: canEdit,
            allowDeleteRow: canEdit,
            allowDeleteColumn: canEdit,
            columnDrag: canEdit,
            rowDrag: canEdit,
            parseFormulas: true,
            onafterchanges: save,
            oninsertrow: save,
            ondeleterow: save,
            oninsertcolumn: save,
            ondeletecolumn: save,
            onresizecolumn: save,
            onmoverow: save,
            onmovecolumn: save,
        };
        if (columns.length) options.columns = columns;
        instance = jspreadsheet(grid, options);
        sizeLabel.textContent = sheetDimensions(instance.getData());

        wrapper.querySelector(".bx-sheet-title").addEventListener("change", function () {
            postJson(urls.sheets, {action: "rename", sheet_id: sheet.id, title: this.value});
        });
        wrapper.querySelector(".bx-sheet-head").addEventListener("click", function (event) {
            const button = event.target.closest("[data-act]");
            if (!button) return;
            const act = button.dataset.act;
            if (act === "row") instance.insertRow();
            else if (act === "col") instance.insertColumn();
            else if (act === "csv") instance.download();
            else if (act === "delete") {
                if (!window.confirm("Delete this spreadsheet?")) return;
                postJson(urls.sheets, {action: "delete", sheet_id: sheet.id}).then(function (r) {
                    if (r.status === "success") { wrapper.remove(); toggleSheetHint(); }
                });
            }
        });

        sheets.push({id: sheet.id, instance: instance, refresh: function () { /* layout is CSS driven */ }});
        toggleSheetHint();
        return wrapper;
    }

    function toggleSheetHint() {
        const empty = document.getElementById("bx-sheets-empty");
        if (empty) empty.classList.toggle("d-none", document.querySelectorAll(".bx-sheet").length > 0);
    }

    function addSheet() {
        if (!canEdit) return;
        const header = [["Component", "Amount per reaction", "Reactions", "Total"], ["", "", "", "=B2*C2"]];
        postJson(urls.sheets, {action: "add", title: "Table " + (document.querySelectorAll(".bx-sheet").length + 1), data: header}).then(function (r) {
            if (r.status !== "success") { window.alert(r.message || "Could not add a spreadsheet"); return; }
            document.querySelector('.bx-section[data-pane="notes"]').click();
            const wrapper = mountSheet(r.sheet);
            wrapper.scrollIntoView({behavior: "smooth", block: "center"});
        });
    }

    function initSheets() {
        if (!window.jspreadsheet) {
            document.getElementById("bx-sheets").innerHTML = '<p class="bx-hint">The spreadsheet component could not be loaded.</p>';
            return;
        }
        state.spreadsheets.forEach(mountSheet);
        toggleSheetHint();
        const add = document.getElementById("bx-add-sheet");
        if (add) add.addEventListener("click", addSheet);
    }

    // ---------------------------------------------------------------- relevant items

    const RELEVANT = [
        {key: "samples", title: "Samples", icon: "bi-droplet", placeholder: "Search samples by ID, organism or type"},
        {key: "chemicals", title: "Reagents & compounds", icon: "bi-flask", placeholder: "Search reagents by name, formula or CAS"},
        {key: "molecules", title: "Molecular records", icon: "bi-bezier2", placeholder: "Search sequences and plasmids"},
        {key: "jupyter", title: "Jupyter notebooks", icon: "bi-journal-code", placeholder: "Search the owner's notebooks"},
    ];

    function renderRelevant() {
        const root = document.getElementById("bx-relevant");
        const relevant = state.relevant;
        let total = 0;
        root.innerHTML = RELEVANT.map(function (group) {
            const items = relevant[group.key] || [];
            total += items.length;
            return `<div class="bx-card" data-group="${group.key}">
                <div class="bx-card-head"><span><i class="bi ${group.icon}"></i> ${group.title}</span><span class="badge text-bg-light">${items.length}</span></div>
                <div class="bx-card-body">
                    ${canEdit ? `<div class="nb-picker mb-2" data-kind="${group.key}">
                        <input type="search" class="form-control form-control-sm nb-picker-input" placeholder="${esc(group.placeholder)}">
                        <div class="nb-picker-results list-group d-none"></div></div>` : ""}
                    <ul class="bx-rel-list">${items.map((i) => `<li>
                        ${i.url ? `<a href="${esc(i.url)}">${esc(i.label)}</a>` : `<span>${esc(i.label)}</span>`}
                        ${canEdit ? `<button type="button" class="bx-rel-remove" data-unlink="${esc(i.link_id)}" title="Remove"><i class="bi bi-x-lg"></i></button>` : ""}
                    </li>`).join("") || '<li class="bx-hint">Nothing linked yet.</li>'}</ul>
                </div></div>`;
        }).join("");
        const counter = document.getElementById("bx-count-relevant");
        const links = document.getElementById("nb-links-count");
        const totalLinks = total + (links ? Number(links.textContent || 0) : 0);
        if (counter) counter.textContent = totalLinks ? totalLinks : "";

        if (!canEdit) return;
        root.querySelectorAll(".nb-picker").forEach(function (picker) {
            const kind = picker.dataset.kind;
            const input = picker.querySelector(".nb-picker-input");
            const results = picker.querySelector(".nb-picker-results");
            const search = debounce(function () {
                getJson(urls.relevant + "?kind=" + kind + "&q=" + encodeURIComponent(input.value.trim())).then(function (data) {
                    const items = (data && data.results) || [];
                    results.innerHTML = items.length
                        ? items.map((i) => `<button type="button" class="list-group-item list-group-item-action py-1 small" data-id="${esc(i.id)}">${esc(i.label)}</button>`).join("")
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
                postJson(urls.relevant, {action: "link", kind: kind, id: Number(button.dataset.id)}).then(function (data) {
                    if (data.status === "success") { state.relevant = data.relevant; renderRelevant(); }
                    else window.alert(data.message || "Could not link");
                });
            });
            document.addEventListener("click", function (event) { if (!picker.contains(event.target)) results.classList.add("d-none"); });
        });
        root.querySelectorAll("[data-unlink]").forEach(function (button) {
            button.addEventListener("click", function () {
                const kind = button.closest("[data-group]").dataset.group;
                postJson(urls.relevant, {action: "unlink", kind: kind, link_id: Number(button.dataset.unlink)}).then(function (data) {
                    if (data.status === "success") { state.relevant = data.relevant; renderRelevant(); }
                });
            });
        });
    }

    // ---------------------------------------------------------------- files

    function formatSize(bytes) {
        if (bytes == null) return "—";
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " kB";
        return (bytes / 1024 / 1024).toFixed(1) + " MB";
    }

    function renderFiles() {
        const files = state.attachments;
        const counter = document.getElementById("bx-count-files");
        if (counter) counter.textContent = files.length ? files.length : "";
        document.getElementById("bx-files").innerHTML = files.length
            ? `<table class="bx-files-table"><thead><tr><th></th><th>File</th><th>Type</th><th>Size</th><th>SHA-256</th><th>Uploaded</th>${canEdit ? "<th></th>" : ""}</tr></thead><tbody>
                ${files.map((f) => `<tr data-file="${f.id}">
                    <td>${f.type === "image" ? `<img class="bx-thumb" src="${esc(f.url)}" alt="">` : '<i class="bi bi-file-earmark fs-4 text-secondary"></i>'}</td>
                    <td><a href="${esc(f.url)}">${esc(f.name)}</a> ${f.version > 1 ? `<span class="badge text-bg-light bx-version">v${f.version}</span>` : ""}
                        <div class="bx-hint">${canEdit
                            ? `<span class="bx-caption-edit" data-caption="${f.id}" title="Click to edit the description">${esc(f.caption || "Add a description")}</span>`
                            : esc(f.caption && f.caption !== f.name ? f.caption : "")}</div>
                        ${f.history && f.history.length ? `<details class="bx-versions"><summary>${f.history.length} earlier version${f.history.length > 1 ? "s" : ""}</summary><ul>
                            ${f.history.map((h) => `<li><a href="${esc(h.url)}">v${h.version}</a> · ${esc(h.uploaded_at)} · ${esc(h.uploaded_by)} · ${formatSize(h.size)}</li>`).join("")}</ul></details>` : ""}</td>
                    <td class="text-capitalize">${esc(f.type)}</td>
                    <td>${formatSize(f.size)}</td>
                    <td><code title="SHA-256">${esc(f.checksum || "—")}${f.checksum ? "…" : ""}</code></td>
                    <td class="small text-muted">${esc(f.uploaded_by)}<br>${esc(f.uploaded_at)}</td>
                    ${canEdit ? `<td class="bx-file-actions"><label class="btn btn-sm btn-outline-secondary mb-0" title="Upload a new version of this file"><i class="bi bi-arrow-repeat"></i> New version<input type="file" hidden data-replace="${f.id}"></label>
                        <button type="button" class="btn btn-sm btn-outline-danger" data-delete-file="${f.id}" title="Remove this file and its versions"><i class="bi bi-trash3"></i></button></td>` : ""}
                </tr>`).join("")}</tbody></table>`
            : '<p class="bx-hint mt-3">No files yet.</p>';
    }

    function wireFileActions() {
        const root = document.getElementById("bx-files");
        root.addEventListener("change", function (event) {
            const input = event.target.closest("[data-replace]");
            if (!input || !input.files.length) return;
            const form = new FormData();
            form.append("file", input.files[0]);
            form.append("attachment_id", input.dataset.replace);
            status("Uploading new version…");
            fetch(urls.replace, {method: "POST", credentials: "same-origin", headers: {"X-CSRFToken": csrf()}, body: form})
                .then((r) => r.json()).then(function (data) {
                    status(data.status === "success" ? "New version uploaded" : (data.message || "Upload failed"), data.status !== "success");
                    refreshFiles();
                });
        });
        root.addEventListener("click", function (event) {
            const del = event.target.closest("[data-delete-file]");
            if (del && canEdit) {
                const file = state.attachments.find((f) => String(f.id) === del.dataset.deleteFile);
                const extra = file && file.history && file.history.length ? " and its " + file.history.length + " earlier version(s)" : "";
                if (!window.confirm("Remove " + (file ? file.name : "this file") + extra + "? Images from this file used in the notes will stop showing. This cannot be undone.")) return;
                postJson(urls.file_delete, {attachment_id: Number(del.dataset.deleteFile)}).then(function (data) {
                    status(data.status === "success" ? "File removed" : (data.message || "Could not remove the file"), data.status !== "success");
                    refreshFiles();
                });
                return;
            }
            const span = event.target.closest("[data-caption]");
            if (!span || !canEdit) return;
            const id = span.dataset.caption;
            const file = state.attachments.find((f) => String(f.id) === id);
            const field = document.createElement("input");
            field.type = "text"; field.className = "form-control form-control-sm"; field.maxLength = 255;
            field.value = file ? file.caption : "";
            span.replaceWith(field);
            field.focus();
            let done = false;
            function finish(save) {
                if (done) return;
                done = true;
                if (!save) { renderFiles(); return; }
                postJson(urls.file_caption, {attachment_id: Number(id), caption: field.value}).then(function (data) {
                    if (data.status === "success" && file) file.caption = data.caption;
                    renderFiles();
                });
            }
            field.addEventListener("keydown", (e) => { if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); });
            field.addEventListener("blur", () => finish(true));
        });
    }

    function refreshFiles() {
        getJson(urls.files).then(function (data) {
            if (data.status === "success") { state.attachments = data.attachments; renderFiles(); }
        });
    }

    function uploadFiles(fileList) {
        const files = Array.from(fileList || []);
        if (!files.length) return;
        status(`Uploading ${files.length} file${files.length > 1 ? "s" : ""}…`);
        Promise.all(files.map(function (file) {
            const form = new FormData();
            form.append("file", file);
            form.append("caption", file.name);
            return fetch(urls.upload, {method: "POST", credentials: "same-origin", headers: {"X-CSRFToken": csrf()}, body: form})
                .then((r) => r.json());
        })).then(function (results) {
            const failed = results.filter((r) => r.status !== "success").length;
            status(failed ? `${failed} upload(s) failed` : "Uploaded", !!failed);
            refreshFiles();
        });
    }

    function initFiles() {
        renderFiles();
        wireFileActions();
        const drop = document.getElementById("bx-drop");
        if (!drop) return;
        const input = document.getElementById("bx-file-input");
        input.addEventListener("change", () => { uploadFiles(input.files); input.value = ""; });
        ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
        ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
        drop.addEventListener("drop", (e) => uploadFiles(e.dataTransfer.files));
    }


    // ---------------------------------------------------------------- exclusive edit

    const lockBanner = document.getElementById("bx-lock-banner");
    let heartbeatTimer = null;
    let readOnly = false;

    function tabToken() {
        const key = "b3eln.lock." + entryId;
        try {
            let token = window.sessionStorage.getItem(key);
            if (!token) {
                const bytes = new Uint8Array(16);
                window.crypto.getRandomValues(bytes);
                token = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
                window.sessionStorage.setItem(key, token);
            }
            return token;
        } catch (e) {
            return String(Date.now()) + Math.random().toString(16).slice(2);
        }
    }

    function applyReadOnly(on) {
        readOnly = on;
        if (editorRef && editorRef.mode) editorRef.mode.set(on ? "readonly" : "design");
        document.querySelectorAll(".bx-sheet-add, #bx-add-sheet").forEach((b) => { b.disabled = on; });
    }

    function lockLost(info, wasMine) {
        applyReadOnly(true);
        if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
        const same = info && info.holder && info.holder === state.user;
        const who = same ? "Another window or tab of yours" : ((info && info.holder) || "Another window");
        lockBanner.innerHTML = `<i class="bi bi-lock-fill"></i><span><strong>${esc(who)}</strong> ${wasMine ? "took over editing of this entry." : "is editing this entry" + (info && info.since ? " since " + esc(info.since) : "") + "."} You are viewing it read-only.</span>
            <button type="button" class="btn btn-sm btn-outline-warning" id="bx-lock-take">Take over editing</button>`;
        lockBanner.classList.remove("d-none");
        document.getElementById("bx-lock-take").addEventListener("click", function () {
            if (!window.confirm("Taking over will stop the other window from saving. Unsaved text there will be lost. Continue?")) return;
            postJson(urls.lock, {action: "acquire", token: lockToken, force: true}).then(function (r) {
                if (r.status === "success" && r.granted) window.location.reload();
            });
        });
    }

    function lockHeld() {
        lockBanner.classList.add("d-none");
        lockBanner.innerHTML = "";
        applyReadOnly(false);
        if (heartbeatTimer) clearInterval(heartbeatTimer);
        heartbeatTimer = setInterval(function () {
            postJson(urls.lock, {action: "heartbeat", token: lockToken}).then(function (r) {
                if (r.status === "success" && !r.granted) lockLost(r, true);
            });
        }, 30000);
    }

    function initLock() {
        if (!canEdit) return;
        lockToken = tabToken();
        postJson(urls.lock, {action: "acquire", token: lockToken}).then(function (r) {
            if (r.status !== "success") return;
            if (r.granted) lockHeld(); else lockLost(r, false);
        });
        window.addEventListener("pagehide", function () {
            if (readOnly) return;
            try {
                fetch(urls.lock, {
                    method: "POST", keepalive: true, credentials: "same-origin",
                    headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
                    body: JSON.stringify({action: "release", token: lockToken}),
                });
            } catch (e) { /* best effort */ }
        });
    }

    // ---------------------------------------------------------------- remove (trash)

    function initTrash() {
        const button = document.getElementById("bx-trash");
        if (!button) return;
        button.addEventListener("click", function () {
            if (!window.confirm("Remove this entry? It moves to the Trash, where you can restore it or delete it for good.")) return;
            postJson(urls.batch, {action: "trash", ids: [entryId]}).then(function (data) {
                if (data.status !== "success" || !data.changed) { status(data.message || "Could not remove the entry", true); return; }
                try {
                    const tabs = store.get("openTabs", []).filter((t) => t && t.id !== entryId);
                    store.set("openTabs", tabs);
                    window.sessionStorage.removeItem("b3eln.lock." + entryId);
                } catch (e) { /* ignore */ }
                pending = 0;
                window.location.href = urls.dashboard;
            });
        });
    }

    // ---------------------------------------------------------------- sharing

    function initSharing() {
        const button = document.getElementById("bx-share");
        const modalEl = document.getElementById("bx-share-modal");
        if (!button || !modalEl || !urls.sharing) return;
        const el = (id) => document.getElementById(id);
        const visSel = el("bx-share-visibility"), level = el("bx-share-level");
        const results = el("bx-share-results"), q = el("bx-share-q"), list = el("bx-share-list");
        const hints = {
            private: "Only the author sees this entry. People added below keep their access but cannot open it until you share it again.",
            shared: "The author and the people or groups listed below.",
            lab: "Everyone in the lab can read it. People listed below can also edit it.",
        };
        let state = null, picked = null, timer = null;

        function text(node, value) { node.textContent = value; return node; }
        function error(message) { text(el("bx-share-error"), message || ""); }

        function render() {
            const isAuthor = state.your_access === "author" || state.your_access === "admin";
            text(el("bx-share-you"), "Author: " + state.author + (isAuthor ? "" : ". Your access: " + state.your_access));
            visSel.innerHTML = "";
            state.visibilities.forEach(function (v) {
                const o = document.createElement("option");
                o.value = v.value; o.textContent = v.label; o.selected = v.value === state.visibility;
                visSel.appendChild(o);
            });
            visSel.disabled = !isAuthor;
            text(el("bx-share-hint"), hints[state.visibility] || "");
            el("bx-share-manage").hidden = !state.can_manage;
            if (!state.can_manage) return;
            level.innerHTML = "";
            state.levels.forEach(function (l) {
                const o = document.createElement("option");
                o.value = l.value; o.textContent = l.label; level.appendChild(o);
            });
            list.innerHTML = "";
            if (!state.grants.length) {
                const empty = document.createElement("li");
                empty.className = "list-group-item small text-muted px-0";
                empty.textContent = "Nobody yet.";
                list.appendChild(empty);
            }
            state.grants.forEach(function (g) {
                const li = document.createElement("li");
                li.className = "list-group-item d-flex align-items-center gap-2 px-0";
                const icon = document.createElement("i");
                icon.className = "bi " + (g.kind === "group" ? "bi-diagram-3" : "bi-person");
                const who = document.createElement("div");
                who.className = "flex-grow-1 small";
                who.appendChild(text(document.createElement("div"), g.name));
                const sub = g.detail + (g.expires_at ? " · until " + g.expires_at : "");
                who.appendChild(text(Object.assign(document.createElement("div"), {className: "text-muted"}), sub));
                const sel = document.createElement("select");
                sel.className = "form-select form-select-sm w-auto";
                sel.setAttribute("aria-label", "Access level for " + g.name);
                state.levels.forEach(function (l) {
                    const o = document.createElement("option");
                    o.value = l.value; o.textContent = l.label; o.selected = l.value === g.level; sel.appendChild(o);
                });
                sel.addEventListener("change", () => act({action: "grant", kind: g.kind, principal_id: g.principal_id, level: sel.value, expires: g.expires_at}));
                const rm = document.createElement("button");
                rm.type = "button"; rm.className = "btn btn-sm btn-outline-danger";
                rm.setAttribute("aria-label", "Remove access for " + g.name);
                rm.innerHTML = '<i class="bi bi-x-lg"></i>';
                rm.addEventListener("click", () => act({action: "revoke", grant_id: g.id}));
                li.append(icon, who, sel, rm);
                list.appendChild(li);
            });
        }

        function load() {
            return getJson(urls.sharing).then(function (data) {
                if (data.status !== "success") { error(data.message || "Could not load sharing"); return; }
                state = data; render();
            });
        }
        function act(body) {
            error("");
            return postJson(urls.sharing, body).then(function (data) {
                if (data.status !== "success") { error(data.message || "Could not save"); return; }
                state = data; render();
                const select = document.getElementById("bx-visibility");
                if (select) select.value = data.visibility;
                const info = document.getElementById("bx-info-visibility");
                if (info && select && select.selectedOptions[0]) info.textContent = select.selectedOptions[0].textContent;
                picked = null; el("bx-share-add").classList.add("d-none"); q.value = "";
            });
        }

        button.addEventListener("click", function () {
            picked = null; el("bx-share-add").classList.add("d-none"); results.classList.add("d-none"); error("");
            load().then(() => bootstrap.Modal.getOrCreateInstance(modalEl).show());
        });
        visSel.addEventListener("change", () => act({action: "visibility", value: visSel.value}));
        q.addEventListener("input", function () {
            window.clearTimeout(timer);
            const term = q.value.trim();
            if (term.length < 2) { results.classList.add("d-none"); return; }
            timer = window.setTimeout(function () {
                getJson(urls.sharing + "?q=" + encodeURIComponent(term)).then(function (data) {
                    results.innerHTML = "";
                    const found = (data && data.results) || [];
                    if (!found.length) {
                        results.appendChild(text(Object.assign(document.createElement("div"), {className: "list-group-item small text-muted"}), "No match"));
                    }
                    found.forEach(function (r) {
                        const item = document.createElement("button");
                        item.type = "button"; item.className = "list-group-item list-group-item-action small";
                        item.textContent = (r.kind === "group" ? "Group · " : "") + r.name + (r.kind === "user" ? " (" + r.detail + ")" : "");
                        item.addEventListener("click", function () {
                            picked = r; results.classList.add("d-none"); q.value = "";
                            text(el("bx-share-picked"), r.name); el("bx-share-add").classList.remove("d-none");
                        });
                        results.appendChild(item);
                    });
                    results.classList.remove("d-none");
                });
            }, 250);
        });
        el("bx-share-grant").addEventListener("click", function () {
            if (!picked) return;
            act({action: "grant", kind: picked.kind, principal_id: picked.principal_id, level: level.value, expires: el("bx-share-expires").value});
        });
    }

    // ---------------------------------------------------------------- revisions

    function initRevisions() {
        const button = document.getElementById("bx-revisions");
        const modalEl = document.getElementById("bx-rev-modal");
        if (!button || !modalEl) return;
        const list = document.getElementById("bx-rev-list");
        const view = document.getElementById("bx-rev-view");
        const legend = document.getElementById("bx-rev-legend");
        const restore = document.getElementById("bx-rev-restore");
        let revisions = [];
        let selected = null;
        let mode = "prev";

        function renderList() {
            list.innerHTML = revisions.length
                ? revisions.map((r, i) => `<button type="button" class="list-group-item list-group-item-action ${selected && selected.id === r.id ? "active" : ""}" data-index="${i}">
                        <div class="fw-semibold">${esc(r.at)}</div><div>${esc(r.author)}${i === 0 ? " · latest" : ""}${i === revisions.length - 1 ? " · first" : ""}</div></button>`).join("")
                : '<div class="list-group-item small text-muted">No revisions yet. They appear after the first edit of the text.</div>';
        }

        function renderDiff(rows) {
            view.innerHTML = rows.length
                ? rows.map((row) => `<div class="bx-diff-row ${esc(row.type)}">${esc(row.text)}</div>`).join("")
                : '<p class="bx-hint p-2 mb-0">No differences.</p>';
        }

        function load() {
            if (!selected) return;
            const index = revisions.findIndex((r) => r.id === selected.id);
            const older = revisions[index + 1];
            if (restore) restore.disabled = false;
            if (mode === "preview") {
                legend.textContent = "";
                getJson(urls.revisions + "?id=" + selected.id).then(function (data) {
                    view.innerHTML = `<div class="bx-rev-preview">${data.preview || ""}</div>`;
                });
                return;
            }
            let query;
            if (mode === "prev") {
                legend.innerHTML = "Green: added in this revision. Red: removed in this revision.";
                query = older ? "?id=" + older.id + "&against=" + selected.id : "?id=" + selected.id + "&against=" + selected.id;
            } else {
                legend.innerHTML = "Green: in the current text only. Red: in this revision only.";
                query = "?id=" + selected.id;
            }
            getJson(urls.revisions + query).then(function (data) {
                if (data.status === "success") renderDiff(data.diff);
            });
        }

        function refresh() {
            return getJson(urls.revisions).then(function (data) {
                revisions = (data && data.revisions) || [];
                renderList();
            });
        }

        button.addEventListener("click", function () {
            selected = null;
            if (restore) restore.disabled = true;
            view.innerHTML = '<p class="bx-hint p-2 mb-0">Select a revision on the left.</p>';
            legend.textContent = "";
            refresh().then(() => bootstrap.Modal.getOrCreateInstance(modalEl).show());
        });
        list.addEventListener("click", function (event) {
            const item = event.target.closest("[data-index]");
            if (!item) return;
            selected = revisions[Number(item.dataset.index)];
            renderList();
            const active = list.querySelector(".active");
            if (active) active.focus();  // keep focus inside the modal so Esc still closes it
            load();
        });
        modalEl.querySelectorAll("[data-mode]").forEach(function (b) {
            b.addEventListener("click", function () {
                modalEl.querySelectorAll("[data-mode]").forEach((x) => x.classList.toggle("active", x === b));
                mode = b.dataset.mode;
                load();
            });
        });
        if (restore) {
            restore.addEventListener("click", function () {
                if (!selected || !window.confirm("Replace the current text with the version from " + selected.at + "? The current text is kept as a revision.")) return;
                postJson(urls.revisions, {revision_id: selected.id}).then(function (r) {
                    if (r.status !== "success") { status(r.message || "Could not restore", true); return; }
                    if (editorRef) { editorRef.setContent(r.content); editorRef.setDirty(false); }
                    status("Restored " + r.updated_at.slice(11));
                    bootstrap.Modal.getOrCreateInstance(modalEl).hide();
                });
            });
        }
    }

    // ---------------------------------------------------------------- comments

    function initComments() {
        const box = document.getElementById("bx-comments");
        const input = document.getElementById("bx-comment-input");
        const post = document.getElementById("bx-comment-post");
        if (!box) return;
        let rows = [];
        let editing = null;

        function draw() {
            const counter = document.getElementById("bx-count-comments");
            if (counter) counter.textContent = rows.length ? rows.length : "";
            box.innerHTML = rows.length ? rows.map((c) => `<div class="bx-comment" data-id="${c.id}">
                <div class="bx-comment-head"><strong>${esc(c.author)}</strong><span>${esc(c.at)}${c.edited ? " · edited" : ""}</span>
                    <span class="bx-comment-actions">
                        ${c.can_edit ? `<a href="#" data-act="edit">Edit</a>` : ""}
                        ${c.can_delete ? `<a href="#" class="text-danger" data-act="delete">Delete</a>` : ""}
                    </span></div>
                ${editing === c.id
                    ? `<textarea class="form-control mt-2" rows="3" maxlength="5000" data-edit-box>${esc(c.body)}</textarea>
                       <div class="mt-2"><button type="button" class="btn btn-sm btn-primary" data-act="save">Save</button> <button type="button" class="btn btn-sm btn-link" data-act="cancel">Cancel</button></div>`
                    : `<div class="bx-comment-body">${esc(c.body)}</div>`}
            </div>`).join("") : '<p class="bx-hint">No comments yet.</p>';
        }

        function apply(data) {
            if (data.status === "success") { rows = data.comments; editing = null; draw(); }
            else status(data.message || "Could not save the comment", true);
        }

        getJson(urls.comments).then((data) => { if (data.status === "success") { rows = data.comments; draw(); } });
        post.addEventListener("click", function () {
            const body = input.value.trim();
            if (!body) return;
            post.disabled = true;
            postJson(urls.comments, {action: "add", body: body}).then(function (data) {
                post.disabled = false;
                if (data.status === "success") input.value = "";
                apply(data);
            });
        });
        box.addEventListener("click", function (event) {
            const link = event.target.closest("[data-act]");
            if (!link) return;
            event.preventDefault();
            const id = Number(link.closest("[data-id]").dataset.id);
            const act = link.dataset.act;
            if (act === "edit") { editing = id; draw(); }
            else if (act === "cancel") { editing = null; draw(); }
            else if (act === "save") {
                postJson(urls.comments, {action: "edit", id: id, body: box.querySelector("[data-edit-box]").value}).then(apply);
            } else if (act === "delete" && window.confirm("Delete this comment?")) {
                postJson(urls.comments, {action: "delete", id: id}).then(apply);
            }
        });
    }

    // ---------------------------------------------------------------- boot

    initNavigator();
    initTabs();
    initHeader();
    initSheets();
    initSections();
    renderRelevant();
    initFiles();
    initLock();
    initTrash();
    initSharing();
    initRevisions();
    initComments();
    initEditor();
})();
