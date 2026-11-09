/*
 * Molecular edit strip: the editing tools of a nucleotide record, in the
 * panel itself.
 *
 * One strip serves the map and the sequence editor. It reads the selection
 * from the workspace (or the live caret of the sequence editor) and edits
 * through window.BiobankMolecularWorkspace, so the annotations follow the
 * text and every step can be undone.
 */
(function () {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const host = document.getElementById("mw-editstrip");

    if (!root || !host) {
        return;
    }

    const COMPLEMENT = {A: "T", T: "A", U: "A", G: "C", C: "G", R: "Y", Y: "R", K: "M", M: "K", B: "V", V: "B", D: "H", H: "D", S: "S", W: "W", N: "N"};
    const api = () => window.BiobankMolecularWorkspace || null;
    const editor = () => window.BiobankSeqCanvas || null;
    const snap = () => (api() ? api().getSnapshot() : null);

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;

        return node;
    }

    function button(label, title, onClick) {
        const node = el("button", "mes-btn", label);

        node.type = "button";
        node.title = title;
        node.addEventListener("click", onClick);

        return node;
    }

    const label = el("span", "mes-label", "Edit");
    const undoBtn = button("Undo", "Undo the last edit (Ctrl+Z)", () => run("undo"));
    const redoBtn = button("Redo", "Redo (Ctrl+Shift+Z)", () => run("redo"));
    const insertBtn = button("Insert…", "Insert pasted bases at the cursor, or replace the selection", () => openDialog());
    const deleteBtn = button("Delete", "Delete the selected bases", () => run("delete"));
    const rcBtn = button("Reverse complement", "Replace the selection by its reverse complement", () => run("rc"));
    const featureBtn = button("Add annotation", "Create an annotation from the selection", () => run("feature"));
    const status = el("span", "mes-status");
    const sep = () => el("span", "mes-sep");
    const dialog = document.createElement("dialog");
    const dialogTitle = el("strong", "mes-dialog-title");
    const dialogText = document.createElement("textarea");
    const dialogApply = button("Insert", "", () => applyDialog());
    const dialogCancel = button("Cancel", "", () => closeDialog());
    const dialogRow = el("div", "mes-dialog-row");
    let noticeUntil = 0;
    let noticeTimer = 0;

    dialog.className = "mes-dialog";
    dialogText.rows = 7;
    dialogText.placeholder = "Paste or type bases here. FASTA headers and spaces are ignored.";
    dialogApply.classList.add("is-primary");
    dialogRow.append(dialogCancel, dialogApply);
    dialog.append(dialogTitle, dialogText, dialogRow);
    host.append(label, undoBtn, redoBtn, sep(), insertBtn, deleteBtn, rcBtn, featureBtn, status, dialog);

    /* ---------- what the edit would act on ---------- */

    function target() {
        const s = snap();

        if (!s) return null;

        const live = editor() && editor().active() ? editor().state() : null;
        let from = null;
        let to = null;

        if (live && live.selA !== live.selB) {
            from = Math.min(live.selA, live.selB);
            to = Math.max(live.selA, live.selB);
        } else if (s.sequenceSelection && s.sequenceSelection.start <= s.sequenceSelection.end && !live) {
            from = s.sequenceSelection.start - 1;
            to = s.sequenceSelection.end;
        }

        const hasRange = from !== null && to > from;
        const caret = live ? live.caret : null;

        return {s, live, hasRange, from, to, caret, canEdit: s.canEdit};
    }

    function notice(text) {
        status.textContent = text;
        noticeUntil = Date.now() + 3000;
        window.clearTimeout(noticeTimer);
        noticeTimer = window.setTimeout(refresh, 3100);
    }

    /* ---------- actions ---------- */

    function afterEdit(position) {
        if (editor() && editor().active()) {
            editor().setCaret(position);
            editor().focus();
        }
    }

    function run(action) {
        const t = target();
        const workspace = api();

        if (!t || !workspace) return;

        if (action === "undo" || action === "redo") {
            const done = workspace[action]();

            if (done && editor() && editor().active()) afterEdit(editor().state().caret);

            return;
        }

        if (action === "feature") {
            if (t.hasRange) workspace.createFeatureFromSelection({focusEditor: true});
            else notice("Select a region first, then add the annotation");

            return;
        }

        if (!t.hasRange) {
            notice("Select a region first");

            return;
        }

        if (action === "delete") {
            workspace.replaceRange(t.from, t.to, "", {source: "edit-strip"});
            afterEdit(t.from);
        } else if (action === "rc") {
            const piece = t.s.sequence.slice(t.from, t.to).split("").reverse().map(base => COMPLEMENT[base] || base).join("");

            workspace.replaceRange(t.from, t.to, piece, {source: "edit-strip"});
            afterEdit(t.to);
        }
    }

    /* ---------- insert / replace dialog ---------- */

    function openDialog() {
        const t = target();

        if (!t || !t.canEdit) return;

        if (!t.hasRange && t.caret === null) {
            notice("Select a region on the map, or open the sequence view to place a cursor");

            return;
        }

        dialogTitle.textContent = t.hasRange
            ? "Replace the selected " + (t.to - t.from).toLocaleString() + " bases with"
            : "Insert at the cursor (after base " + t.caret.toLocaleString() + ")";
        dialogApply.textContent = t.hasRange ? "Replace" : "Insert";
        dialogText.value = "";

        if (typeof dialog.showModal === "function") dialog.showModal();
        else dialog.setAttribute("open", "");

        dialogText.focus();
    }

    function closeDialog() {
        if (typeof dialog.close === "function") dialog.close();
        else dialog.removeAttribute("open");
    }

    function applyDialog() {
        const text = dialogText.value;
        const t = target();

        closeDialog();

        if (!t || !text.trim()) return;

        const from = t.hasRange ? t.from : t.caret;
        const to = t.hasRange ? t.to : t.caret;
        const added = api().replaceRange(from, to, text, {source: "edit-strip"});

        if (added !== false) afterEdit(from + added);
    }

    /* ---------- state ---------- */

    function refresh() {
        const t = target();

        if (!t) return;

        const history = api().history ? api().history() : {undo: 0, redo: 0};
        const editable = Boolean(t.canEdit);
        const unit = t.s.sequenceType === "protein" ? "aa" : "bp";

        undoBtn.disabled = !editable || !history.undo;
        redoBtn.disabled = !editable || !history.redo;
        insertBtn.disabled = !editable;
        deleteBtn.disabled = !editable || !t.hasRange;
        rcBtn.disabled = !editable || !t.hasRange || t.s.sequenceType === "protein";
        featureBtn.disabled = !editable || !t.hasRange;

        if (Date.now() < noticeUntil) return;

        if (!editable) {
            status.textContent = "Read only: you can look and select but not edit this record";
        } else if (t.hasRange) {
            status.textContent = "Selected " + (t.from + 1).toLocaleString() + "–" + t.to.toLocaleString() + " · " + (t.to - t.from).toLocaleString() + " " + unit;
        } else if (t.caret !== null) {
            status.textContent = "Cursor after " + t.caret.toLocaleString() + " of " + t.s.sequence.length.toLocaleString() + " " + unit + " · type in the sequence to edit";
        } else {
            status.textContent = "Select a region, or click in the sequence to type";
        }
    }

    let frame = 0;
    const schedule = () => {
        if (!frame) {
            frame = window.requestAnimationFrame(() => {
                frame = 0;
                refresh();
            });
        }
    };

    root.addEventListener("biobank:molecular-workspace-change", schedule);
    document.addEventListener("msc:caret", schedule);
    document.addEventListener("keyup", schedule);
    document.addEventListener("pointerup", schedule);
    window.setTimeout(refresh, 300);

    window.BiobankEditStrip = {refresh, notice, openInsert: openDialog};
}());
