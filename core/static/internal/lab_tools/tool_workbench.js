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

    function render() {
        WINDOWS.forEach(key => {
            const isOpen = open.indexOf(key) !== -1;
            const pane = paneOf(key);

            pane.hidden = !isOpen;
            page.querySelector('[data-tw-toggle="' + key + '"]').classList.toggle("is-open", isOpen);
        });
        document.getElementById("tw-none").hidden = open.length > 0;

        if (open.indexOf("gel") !== -1 && window.BiobankGel) {
            window.requestAnimationFrame(() => window.BiobankGel.refresh());
        }

        schedule();
    }

    function toggle(key, force) {
        const isOpen = open.indexOf(key) !== -1;
        const want = force === undefined ? !isOpen : force;

        if (want && !isOpen) open.push(key);
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
        const data = {windows: open.slice(), notes: notes.value};

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
