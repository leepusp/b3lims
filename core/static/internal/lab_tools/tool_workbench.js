/*
 * Independent tool page. Every record type opens its own tool; any window of
 * another tool can be opened beside it and closed again. The state of every
 * window is saved with the record (PostgreSQL); the record's file (a gel
 * photo, a structure) is stored in the owner's biobank folder.
 */
(function () {
    "use strict";

    const page = document.getElementById("tool-workbench");

    if (!page) return;

    const tool = page.dataset.tool;
    const WINDOWS = ["gel", "assembly", "chemical", "notes"];
    const statusEl = document.getElementById("tw-status");
    const nameInput = document.getElementById("tw-name");
    const notes = document.getElementById("tw-notes");
    const csrf = () => (document.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";
    const fileNameEl = document.getElementById("tw-file-name");
    const pickBtn = document.getElementById("tw-file-pick");
    const removeBtn = document.getElementById("tw-file-remove");
    const openLink = document.getElementById("tw-file-open");
    const fileInput = document.getElementById("tw-file-input");
    const fileLabel = document.getElementById("tw-file-label");
    let initial = {};
    let open = [];
    let lastSaved = "";
    let timer = 0;
    let fileError = "";
    let hasFile = page.dataset.hasFile === "1";
    let filename = page.dataset.filename || "";

    try {
        initial = JSON.parse(document.getElementById("tw-initial").textContent || "{}");
    } catch (error) {
        initial = {};
    }

    const stored = initial && typeof initial === "object" ? initial : {};

    function setStatus(text, isError) {
        statusEl.textContent = text;
        statusEl.classList.toggle("is-error", !!isError);
    }

    // A gel photo that is only in the browser is not part of the record yet.
    function photoPending() {
        return tool === "gel" && !hasFile && !!window.BiobankGel && window.BiobankGel.hasPhoto();
    }

    function savedStatus() {
        if (fileError) {
            setStatus("Saved, but the file was not stored: " + fileError, true);
        } else if (photoPending()) {
            setStatus("Saved, but the photo is not stored in the record yet. Press Save to store it.", true);
        } else {
            setStatus("Saved");
        }
    }

    /* ---------- windows ---------- */

    function paneOf(key) {
        return page.querySelector('[data-tw-pane="' + key + '"]');
    }

    /* ---------- layout ---------- */

    const L = {mode: "split", order: [], collapsed: [], sideWidth: 0, focus: "", active: ""};
    const mainEl = document.getElementById("tw-main");
    const sideEl = document.getElementById("tw-side");
    const dividerEl = document.getElementById("tw-divider");
    const gridEl = document.getElementById("tw-grid");
    const tabsEl = document.getElementById("tw-tabs");
    const noneEl = document.getElementById("tw-none");
    const TITLES = {gel: "Gel", assembly: "Plasmid assembly", chemical: "Chemical", notes: "Notes"};
    const MODES = ["split", "stack", "tabs"];

    L.order = [tool].concat(WINDOWS.filter(key => key !== tool));

    function applyLayoutState(state) {
        if (!state || typeof state !== "object") return;

        if (MODES.indexOf(state.mode) !== -1) L.mode = state.mode;

        if (Array.isArray(state.order)) {
            const known = state.order.filter(key => WINDOWS.indexOf(key) !== -1);

            L.order = known.concat(WINDOWS.filter(key => known.indexOf(key) === -1));
        }

        if (Array.isArray(state.collapsed)) L.collapsed = state.collapsed.filter(key => WINDOWS.indexOf(key) !== -1);

        L.sideWidth = Math.max(0, Number(state.sideWidth) || 0);
        L.active = WINDOWS.indexOf(state.active) !== -1 ? state.active : "";
    }

    function notifyLayout() {
        window.requestAnimationFrame(() => {
            if (window.BiobankGel && open.indexOf("gel") !== -1) window.BiobankGel.refresh();
        });
    }

    function render() {
        const visible = L.order.filter(key => open.indexOf(key) !== -1);
        let shown = visible;

        if (L.focus && visible.indexOf(L.focus) !== -1) {
            shown = [L.focus];
        } else {
            L.focus = "";

            if (L.mode === "tabs") {
                if (visible.indexOf(L.active) === -1) L.active = visible[0] || "";

                shown = L.active ? [L.active] : [];
            }
        }

        const split = L.mode === "split" && !L.focus && shown.length > 1;
        const mainKeys = split ? [shown[0]] : shown;
        const sideKeys = split ? shown.slice(1) : [];

        WINDOWS.forEach(key => {
            const pane = paneOf(key);
            const isShown = shown.indexOf(key) !== -1;

            pane.hidden = !isShown;
            pane.classList.toggle("is-collapsed", L.collapsed.indexOf(key) !== -1);
            page.querySelector('[data-tw-toggle="' + key + '"]').classList.toggle("is-open", open.indexOf(key) !== -1);
            updatePaneTools(pane, key, visible, shown);
        });
        mainKeys.forEach(key => mainEl.insertBefore(paneOf(key), noneEl));
        sideKeys.forEach(key => sideEl.append(paneOf(key)));
        sideEl.hidden = dividerEl.hidden = !sideKeys.length;
        sideEl.style.flexBasis = (L.sideWidth || 544) + "px";
        noneEl.hidden = shown.length > 0;
        page.querySelectorAll("[data-tw-layout]").forEach(node => node.classList.toggle("is-open", node.dataset.twLayout === L.mode));

        tabsEl.hidden = L.mode !== "tabs" || !visible.length;
        tabsEl.replaceChildren();
        visible.forEach(key => {
            const tab = document.createElement("button");

            tab.type = "button";
            tab.className = "tw-tab" + (key === L.active ? " is-active" : "");
            tab.textContent = TITLES[key];
            tab.setAttribute("role", "tab");
            tab.addEventListener("click", () => {
                L.active = key;
                render();
            });
            tabsEl.append(tab);
        });

        notifyLayout();
        schedule();
    }

    function tool_(label, title, onClick) {
        const node = document.createElement("button");

        node.type = "button";
        node.className = "tw-x";
        node.textContent = label;
        node.title = title;
        node.setAttribute("aria-label", title);
        node.addEventListener("click", onClick);

        return node;
    }

    function swapOrder(key, delta) {
        const visible = L.order.filter(item => open.indexOf(item) !== -1);
        const at = visible.indexOf(key);
        const other = visible[at + delta];

        if (other === undefined) return;

        const i = L.order.indexOf(key);
        const j = L.order.indexOf(other);

        L.order[i] = other;
        L.order[j] = key;
        render();
    }

    // Window tools are built once per pane and refreshed for state-dependent bits.
    function updatePaneTools(pane, key, visible, shown) {
        let tools = pane.querySelector(".tw-pane-tools");

        if (!tools) {
            const head = pane.querySelector(".tw-pane-head");
            const close = head.querySelector("[data-tw-close]");

            tools = document.createElement("span");
            tools.className = "tw-pane-tools";
            tools.append(
                tool_("▲", "Move up / make it the main window", () => swapOrder(key, -1)),
                tool_("▼", "Move down", () => swapOrder(key, 1)),
                tool_("–", "Collapse or expand this window", () => {
                    const at = L.collapsed.indexOf(key);

                    if (at === -1) L.collapsed.push(key);
                    else L.collapsed.splice(at, 1);

                    render();
                }),
                tool_("⤢", "Show only this window (press again to go back)", () => {
                    L.focus = L.focus === key ? "" : key;
                    render();
                }),
            );
            head.insertBefore(tools, close);
        }

        const buttons = tools.querySelectorAll("button");

        buttons[0].disabled = visible.indexOf(key) <= 0;
        buttons[1].disabled = visible.indexOf(key) === visible.length - 1;
        buttons[3].textContent = L.focus === key ? "⤡" : "⤢";
    }

    page.querySelectorAll("[data-tw-layout]").forEach(node => {
        node.addEventListener("click", () => {
            L.mode = node.dataset.twLayout;
            L.focus = "";
            render();
        });
    });

    // Drag the divider to give the side column more or less room.
    function setSideFromPointer(clientX) {
        const box = gridEl.getBoundingClientRect();
        const width = Math.round(box.right - clientX - dividerEl.offsetWidth / 2);

        L.sideWidth = Math.max(288, Math.min(Math.round(box.width * 0.7), width));
        sideEl.style.flexBasis = L.sideWidth + "px";
    }

    dividerEl.addEventListener("pointerdown", event => {
        dividerEl.setPointerCapture(event.pointerId);
        dividerEl.classList.add("is-drag");
        event.preventDefault();
    });
    dividerEl.addEventListener("pointermove", event => {
        if (dividerEl.classList.contains("is-drag")) setSideFromPointer(event.clientX);
    });
    ["pointerup", "pointercancel"].forEach(type => dividerEl.addEventListener(type, () => {
        if (!dividerEl.classList.contains("is-drag")) return;

        dividerEl.classList.remove("is-drag");
        notifyLayout();
        schedule();
    }));
    dividerEl.addEventListener("keydown", event => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;

        L.sideWidth = Math.max(288, (L.sideWidth || sideEl.offsetWidth) + (event.key === "ArrowLeft" ? 40 : -40));
        sideEl.style.flexBasis = L.sideWidth + "px";
        notifyLayout();
        schedule();
        event.preventDefault();
    });

    function toggle(key, force) {
        const isOpen = open.indexOf(key) !== -1;
        const want = force === undefined ? !isOpen : force;

        if (want && !isOpen) {
            open.push(key);
            L.active = key;
            L.focus = "";
        }
        if (!want && isOpen) open = open.filter(item => item !== key);

        render();
    }

    page.querySelectorAll("[data-tw-toggle]").forEach(node => {
        node.addEventListener("click", () => toggle(node.dataset.twToggle));
    });
    page.querySelectorAll("[data-tw-close]").forEach(node => {
        node.addEventListener("click", () => toggle(node.dataset.twClose, false));
    });

    /* ---------- state ---------- */

    function collect() {
        const data = {windows: open.slice(), notes: notes.value, layout: JSON.parse(JSON.stringify(L))};

        if (window.BiobankGel) data.gel = window.BiobankGel.getState();
        if (window.BiobankAssembly) data.assembly = window.BiobankAssembly.getState();
        if (window.BiobankChemical) data.chemical = window.BiobankChemical.getState();

        return data;
    }

    function payload() {
        return {data: collect(), name: nameInput.value, description: notes.value};
    }

    async function save(force) {
        timer = 0;

        const body = JSON.stringify(payload());

        if (body === lastSaved && force !== true) {
            savedStatus();

            return;
        }

        setStatus("Saving…");

        try {
            const response = await fetch(page.dataset.stateUrl, {
                method: "POST",
                credentials: "same-origin",
                keepalive: body.length < 60000,
                headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
                body,
            });
            const result = await response.json().catch(() => ({}));

            if (!response.ok || result.status !== "success") {
                throw new Error(result.message || "The record could not be saved.");
            }

            lastSaved = body;
            savedStatus();
        } catch (error) {
            setStatus(error.message, true);
        }
    }

    function schedule() {
        if (timer) window.clearTimeout(timer);

        setStatus("Unsaved changes…");
        timer = window.setTimeout(() => save(), 1500);
    }

    document.getElementById("tw-save").addEventListener("click", async () => {
        if (timer) window.clearTimeout(timer);

        if (photoPending()) {
            const blob = await window.BiobankGel.photoBlob();

            if (blob) await uploadFile(new File([blob], (nameInput.value || "gel").replace(/[^A-Za-z0-9._-]+/g, "_") + ".png", {type: "image/png"}));
        }

        await save(true);
    });

    ["biobank:gel-change", "biobank:assembly-change", "biobank:chemical-change"].forEach(name => {
        document.addEventListener(name, () => {
            if (initialised) schedule();
        });
    });
    notes.addEventListener("input", schedule);
    nameInput.addEventListener("input", schedule);
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden" && timer) {
            window.clearTimeout(timer);
            save();
        }
    });

    /* ---------- file ---------- */

    function showFile() {
        fileNameEl.textContent = hasFile ? filename : fileError;
        removeBtn.hidden = !hasFile;
        openLink.hidden = !hasFile;
        openLink.href = page.dataset.fileUrl;
        fileLabel.textContent = hasFile ? "Replace file" : (tool === "gel" ? "Attach gel photo" : "Attach file");
    }

    async function uploadFile(file) {
        const form = new FormData();

        form.append("file", file, file.name || "photo.png");
        setStatus("Uploading…");

        const response = await fetch(page.dataset.fileUrl, {
            method: "POST",
            body: form,
            credentials: "same-origin",
            headers: {"X-CSRFToken": csrf()},
        });
        const result = await response.json().catch(() => ({}));

        if (!response.ok || result.status !== "success") {
            fileError = result.message || "The file could not be stored (server error " + response.status + ").";
            setStatus(fileError, true);
            fileNameEl.textContent = fileError;
            fileNameEl.classList.add("tw-bad");

            return false;
        }

        fileError = "";
        fileNameEl.classList.remove("tw-bad");
        hasFile = true;
        filename = result.filename || file.name;
        showFile();
        setStatus("Saved");

        return true;
    }

    pickBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
        const file = fileInput.files[0];

        fileInput.value = "";

        if (!file) return;

        if (tool === "gel" && window.BiobankGel && /^image\//.test(file.type)) {
            // The Gel window announces the photo and it is stored with the record.
            if (open.indexOf("gel") === -1) toggle("gel", true);

            window.BiobankGel.loadFile(file);
        } else {
            await uploadFile(file);
        }
    });
    removeBtn.addEventListener("click", async () => {
        if (!window.confirm("Remove the stored file from this record?")) return;

        const form = new FormData();

        form.append("remove", "1");

        const response = await fetch(page.dataset.fileUrl, {
            method: "POST",
            body: form,
            credentials: "same-origin",
            headers: {"X-CSRFToken": csrf()},
        });

        if (response.ok) {
            hasFile = false;
            filename = "";
            showFile();
        }
    });
    // A photo loaded in the Gel window of a Gel record is kept with the record.
    document.addEventListener("biobank:gel-photo", event => {
        if (tool === "gel" && initialised) uploadFile(event.detail.file);
    });

    document.getElementById("tw-delete").addEventListener("click", async () => {
        if (!window.confirm('Permanently delete "' + nameInput.value + '" and its stored file?')) return;

        const response = await fetch(page.dataset.deleteUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: {"X-CSRFToken": csrf(), Accept: "application/json"},
        });
        const result = await response.json().catch(() => ({}));

        if (response.ok) window.location.href = result.redirect_url || page.dataset.registryUrl;
        else setStatus("The record could not be deleted.", true);
    });

    /* ---------- start ---------- */

    let initialised = false;

    async function start() {
        open = Array.isArray(stored.windows) && stored.windows.length
            ? stored.windows.filter(key => WINDOWS.indexOf(key) !== -1)
            : [tool];

        applyLayoutState(stored.layout);

        if (stored.assembly && window.BiobankAssembly) window.BiobankAssembly.setState(stored.assembly);
        if (stored.chemical && window.BiobankChemical) window.BiobankChemical.setState(stored.chemical);

        showFile();
        render();

        if (window.BiobankGel) {
            try {
                if (hasFile && tool === "gel") {
                    await window.BiobankGel.loadUrl(page.dataset.fileUrl + "?t=" + Date.now(), stored.gel);
                } else if (stored.gel) {
                    window.BiobankGel.setState(stored.gel);
                }
            } catch (error) {
                setStatus(error.message, true);
            }
        }

        initialised = true;
        lastSaved = JSON.stringify(payload());
        savedStatus();
    }

    start();
}());
