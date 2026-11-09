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

    /*
     * Mol* opens with its Structure Tools panel beside the 3D view, which halves
     * a small window. The panel starts closed and a "Tools" button on the view
     * opens it (CSS: molecular_pro.css, .mw-mol-tools-open).
     */
    let toolsTimer = 0;

    function addToolsToggles() {
        host.querySelectorAll(".msp-plugin").forEach(plugin => {
            const stage = plugin.parentElement;

            // Mol* may rebuild its container, so look for the button itself.
            if (!stage || stage.querySelector(":scope > .mw-mol-tools-btn")) return;

            stage.classList.add("mw-mol-stage");

            const button = document.createElement("button");

            button.type = "button";
            button.className = "mw-mol-tools-btn";
            button.textContent = "Tools";
            button.title = "Show or hide the Mol* tools panel";
            button.classList.toggle("is-on", stage.classList.contains("mw-mol-tools-open"));
            button.addEventListener("click", () => {
                const open = stage.classList.toggle("mw-mol-tools-open");

                button.classList.toggle("is-on", open);
                window.setTimeout(() => window.dispatchEvent(new Event("resize")), 60);
            });
            stage.appendChild(button);
        });
    }

    new MutationObserver(() => {
        window.clearTimeout(toolsTimer);
        toolsTimer = window.setTimeout(addToolsToggles, 150);
    }).observe(host, {childList: true, subtree: true});

    poll();
})();
