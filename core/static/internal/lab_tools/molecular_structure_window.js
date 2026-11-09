/*
 * Structure window.
 *
 * The RNA secondary-structure card and the Protein structure (Mol*) card are
 * built by their own modules inside the page. Here they are moved into the
 * "Structure" window of the viewer, so they sit on the same plane as the map
 * and the sequence and can be compared side by side with either of them.
 */
(() => {
    "use strict";

    const root = document.getElementById("molecular-workspace");
    const host = document.getElementById("mw-structure");

    if (!root || !host) return;

    const SELECTOR = {rna: "#mw-rna-secondary-structure", protein: "#mw-protein-structure"}[root.dataset.sequenceType];

    if (!SELECTOR) return;

    let tries = 0;

    function adopt() {
        const card = root.querySelector(SELECTOR);

        if (card && !host.contains(card)) {
            host.appendChild(card);

            if (card.hasAttribute("hidden")) card.removeAttribute("hidden");

            // Mol* and the SVG views size themselves to their container.
            window.setTimeout(() => window.dispatchEvent(new Event("resize")), 50);

            return true;
        }

        return Boolean(card);
    }

    function poll() {
        if (adopt() || tries > 100) return;

        tries += 1;
        window.setTimeout(poll, 100);
    }

    // Opening the window changes the size of what is inside it.
    document.addEventListener("biobank:viewer-layout", event => {
        if (event.detail && event.detail.layout === "structure") {
            window.setTimeout(() => window.dispatchEvent(new Event("resize")), 60);
        }
    });

    poll();
})();
