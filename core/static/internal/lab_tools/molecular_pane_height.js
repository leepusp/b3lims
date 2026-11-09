/*
 * Height of the viewer windows (map, sequence, features, structure ...).
 * Standard fits the screen; Tall and Full let the windows grow downward so
 * large panels (force layout, 3D, alignments) are not cut off. The choice is
 * remembered per browser.
 */
(() => {
    "use strict";

    const split = document.getElementById("mw-split");
    const zoom = document.querySelector(".mwv-zoom");

    if (!split || !zoom) return;

    const MODES = [
        ["standard", "Standard", ""],
        ["tall", "Tall", "max(900px, 120vh)"],
        ["full", "Full", "max(1300px, 170vh)"],
    ];
    const KEY = "biobank.paneHeight";
    let index = 0;

    try {
        const saved = window.localStorage.getItem(KEY);

        index = Math.max(0, MODES.findIndex(m => m[0] === saved));
    } catch (error) {
        index = 0;
    }

    const button = document.createElement("button");

    button.type = "button";
    button.className = "mwv-height-btn";
    zoom.insertAdjacentElement("afterend", button);

    function apply() {
        const [key, label, height] = MODES[index];

        if (height) split.style.setProperty("--mw-pane-h", height);
        else split.style.removeProperty("--mw-pane-h");

        split.dataset.paneHeight = key;
        button.textContent = `Height: ${label}`;
        button.title = "Make the windows taller so nothing is cut off (click to cycle: Standard, Tall, Full)";
        button.classList.toggle("is-on", key !== "standard");

        try {
            window.localStorage.setItem(KEY, key);
        } catch (error) { /* storage unavailable */ }

        window.setTimeout(() => window.dispatchEvent(new Event("resize")), 60);
    }

    button.addEventListener("click", () => {
        index = (index + 1) % MODES.length;
        apply();
    });
    apply();
})();
