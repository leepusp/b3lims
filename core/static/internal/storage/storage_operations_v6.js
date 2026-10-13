/*
 * B3 LIMS Storage Designer V6.
 *
 * Presents existing server-rendered Django management cards in
 * the spatial workspace. Does not duplicate or submit forms.
 */
(() => {
    "use strict";

    const source = document.getElementById("b3-ops-source");
    const host = document.getElementById("b3-v6-ops-host");
    const spatial = document.getElementById("b3-v5-views");
    const spatialControls = document.querySelector(".b3-v5-controls");

    const buttons = Array.from(
        document.querySelectorAll("[data-b3-v6-tab]")
    );

    const panes = new Map(
        Array.from(
            document.querySelectorAll("[data-b3-v6-panel]")
        ).map(element => [
            element.dataset.b3V6Panel,
            element
        ])
    );

    if (
        !source ||
        !host ||
        !spatial ||
        !spatialControls ||
        buttons.length !== 6 ||
        panes.size !== 5
    ) {
        console.error(
            "Storage V6 integration aborted: required components missing."
        );
        return;
    }

    const classify = raw => {
        const label = raw
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();

        if (label.includes("storage hierarchy")) {
            return "locations";
        }

        if (label.includes("current sample occupancy") ||
            label.includes("set sample location")) {
            return "samples";
        }

        if (label.includes("move container") ||
            label.includes("move sample") ||
            label.includes("bulk transfer")) {
            return "transfers";
        }

        if (label.includes("movement history")) {
            return "history";
        }

        if (label.includes("add location")) {
            return "builder";
        }

        return "more";
    };

    const headings = Array.from(
        source.querySelectorAll(".card-header")
    );

    const entries = headings.map(header => ({
        card: header.closest(".card"),
        group: classify(header.textContent || ""),
        name: (header.textContent || "").trim()
    })).filter(entry => entry.card);

    const groupsFound = new Set(
        entries.map(entry => entry.group)
    );

    if (
        !groupsFound.has("locations") ||
        !groupsFound.has("samples") ||
        !groupsFound.has("history")
    ) {
        console.error(
            "Storage V6 integration aborted: essential management cards missing.",
            [...groupsFound]
        );
        return;
    }

    // Record every DOM move so incomplete integration can
    // restore the original server-rendered workspace.
    const relocationJournal = [];

    function move(node, destination) {
        const parent = node.parentNode;
        if (!parent) {
            throw new Error("Cannot relocate a detached element");
        }

        relocationJournal.push({
            node,
            parent,
            next: node.nextSibling
        });

        destination.append(node);
    }

    function restore() {
        for (const entry of relocationJournal.reverse()) {
            const next = entry.next &&
                entry.next.parentNode === entry.parent
                ? entry.next
                : null;

            entry.parent.insertBefore(entry.node, next);
        }

        relocationJournal.length = 0;
    }

    // Move the existing statistics as one group.
    const stats = source.querySelector(
        ".container-fluid > .row.g-3.mb-4"
    );

    if (stats) {
        move(stats, panes.get("locations"));
    }

    const moved = new Set();

    for (const entry of entries) {
        const {card, group} = entry;

        if (moved.has(card)) continue;
        moved.add(card);

        if (group === "builder") {
            // V4 already moves the real create-location form
            // into the left-hand Build location panel.
            // If that integration did not happen, preserve the form.
            if (card.querySelector("form")) {
                move(card, panes.get("locations"));
            }
            continue;
        }

        move(card, panes.get(group));
    }

    // Preserve all remaining cards, including read-only messages
    // and empty states that contain no forms.
    for (const card of Array.from(source.querySelectorAll(".card"))) {
        move(card, panes.get("more"));
    }

    // Do not hide the original workspace if a form remains
    // outside the relocated cards.
    if (source.querySelector("form")) {
        restore();

        console.error(
            "Storage V6 integration incomplete: original workspace restored."
        );
        return;
    }

    const moreButton = buttons.find(
        button => button.dataset.b3V6Tab === "more"
    );

    if (panes.get("more").querySelector(".card, form")) {
        moreButton.hidden = false;
    }

    source.dataset.integrated = "true";

    const storageKey = "b3lims-storage-workspace-v6-tab";

    function activate(tab) {
        if (
            tab !== "explore" &&
            !panes.has(tab)
        ) {
            tab = "explore";
        }

        if (tab === "more" && moreButton.hidden) {
            tab = "explore";
        }

        const exploring = tab === "explore";

        spatial.hidden = !exploring;
        spatialControls.hidden = !exploring;
        host.hidden = exploring;

        for (const [name, pane] of panes) {
            pane.hidden = exploring || name !== tab;
        }

        for (const button of buttons) {
            const selected = button.dataset.b3V6Tab === tab;

            button.setAttribute(
                "aria-pressed",
                String(selected)
            );

            button.classList.toggle(
                "btn-primary",
                selected
            );

            button.classList.toggle(
                "btn-outline-secondary",
                !selected
            );
        }

        try {
            sessionStorage.setItem(storageKey, tab);
        } catch (_) {
            // Browser storage is optional.
        }

        if (exploring) {
            window.dispatchEvent(new Event("resize"));
        }
    }

    for (const button of buttons) {
        button.addEventListener(
            "click",
            () => activate(button.dataset.b3V6Tab)
        );
    }

    let initial = "explore";

    try {
        initial = sessionStorage.getItem(storageKey) || initial;
    } catch (_) {
        // Use the default when session storage is disabled.
    }

    activate(initial);

    console.info(
        "B3 LIMS Storage Designer V6 operations integrated."
    );
})();
