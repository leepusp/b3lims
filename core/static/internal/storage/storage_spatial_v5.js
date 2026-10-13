/* Read-only 2D position map synchronized with Three.js. */
(() => {
    "use strict";

    const $ = id => document.getElementById(id);

    const host = $("b3-v5-views");
    const map = $("b3-v5-map");
    const list = $("b3-v5-samples");
    const detail = $("b3-v5-detail");
    const summary = $("b3-v5-summary");

    if (!host || !map || !list || !detail || !summary) return;

    let data = {
        mode: "live",
        box: null,
        samples: [],
        picked: null
    };

    const position = raw => {
        const m = /^([A-Z])([1-9][0-9]?)$/i.exec(
            String(raw || "").trim()
        );

        return m ? {
            r: m[1].toUpperCase().charCodeAt(0) - 65,
            c: Number(m[2]) - 1
        } : null;
    };

    const add = (parent, text, fn, cls = "") => {
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = text;
        b.className = cls;
        b.addEventListener("click", fn);
        parent.append(b);
        return b;
    };

    function card(sample) {
        detail.replaceChildren();

        if (!sample) {
            detail.textContent =
                "Select a recorded tube or position.";
            return;
        }

        const properties = {
            Sample: sample.code,
            Location: data.box?.path,
            Position: sample.position,
            Organism: sample.organism,
            Source: data.mode === "demo"
                ? "Example"
                : sample.legacy
                    ? "Historical text"
                    : "Physical assignment"
        };

        for (const [label, value] of Object.entries(properties)) {
            if (!value) continue;

            const line = document.createElement("div");
            const strong = document.createElement("strong");

            strong.textContent = label + ": ";

            line.append(
                strong,
                document.createTextNode(String(value))
            );

            detail.append(line);
        }

        if (
            data.mode === "live" &&
            typeof sample.url === "string" &&
            sample.url.startsWith("/") &&
            !sample.url.startsWith("//")
        ) {
            const a = document.createElement("a");
            a.href = sample.url;
            a.textContent = "View Sample record →";
            a.className =
                "btn btn-sm btn-outline-primary mt-2";

            detail.append(a);
        }
    }

    function pick(sample) {
        data.picked = sample.key;
        draw();

        document.dispatchEvent(
            new CustomEvent("b3-spatial-v5-pick", {
                detail: {
                    mode: data.mode,
                    box: data.box?.id,
                    key: sample.key
                }
            })
        );
    }

    function draw() {
        map.replaceChildren();
        list.replaceChildren();

        if (!data.box) {
            summary.textContent =
                "Select a Box to inspect its recorded positions.";
            card(null);
            return;
        }

        summary.textContent =
            `${data.box.name} · ${data.samples.length} Sample(s). ` +
            "Blank cells are unrecorded, not confirmed free positions.";

        const occupied = new Map();
        let maxR = -1;
        let maxC = -1;

        for (const s of data.samples) {
            const p = position(s.position);
            if (!p) continue;

            maxR = Math.max(maxR, p.r);
            maxC = Math.max(maxC, p.c);

            const key = `${p.r}:${p.c}`;
            const group = occupied.get(key) || [];

            group.push(s);
            occupied.set(key, group);
        }

        if (maxR >= 0 && maxR < 20 && maxC < 20) {
            map.style.gridTemplateColumns =
                `24px repeat(${maxC + 1}, minmax(26px, 1fr))`;

            map.append(document.createElement("span"));

            for (let c = 0; c <= maxC; c++) {
                const t = document.createElement("span");
                t.textContent = c + 1;
                map.append(t);
            }

            for (let r = 0; r <= maxR; r++) {
                const t = document.createElement("span");
                t.textContent = String.fromCharCode(65 + r);
                map.append(t);

                for (let c = 0; c <= maxC; c++) {
                    const group =
                        occupied.get(`${r}:${c}`) || [];

                    const b = add(
                        map,
                        group.length ? String(group.length) : "·",
                        () => group.length === 1 &&
                            pick(group[0]),
                        group.length ? "recorded" : ""
                    );

                    b.disabled = group.length !== 1;

                    b.title =
                        `${String.fromCharCode(65 + r)}${c + 1}: ` +
                        `${group.length} recorded Sample(s)`;

                    if (
                        group.some(
                            s => s.key === data.picked
                        )
                    ) {
                        b.classList.add("selected");
                    }
                }
            }
        }

        for (const s of data.samples) {
            add(
                list,
                `${s.position || "Unknown"} · ${s.code}`,
                () => pick(s),
                "btn btn-sm " +
                (s.key === data.picked
                    ? "btn-primary"
                    : "btn-outline-secondary")
            );
        }

        card(
            data.samples.find(
                s => s.key === data.picked
            ) || null
        );
    }

    document.addEventListener(
        "b3-spatial-v5-box",
        event => {
            data = event.detail;
            draw();
        }
    );

    for (
        const control of
        document.querySelectorAll("[data-v5-view]")
    ) {
        control.addEventListener("click", () => {
            const view = control.dataset.v5View;
            host.dataset.view = view;

            for (
                const b of
                document.querySelectorAll("[data-v5-view]")
            ) {
                const active =
                    b.dataset.v5View === view;

                b.setAttribute(
                    "aria-pressed",
                    String(active)
                );

                b.className =
                    "btn btn-sm " +
                    (active
                        ? "btn-primary"
                        : "btn-outline-secondary");
            }

            window.dispatchEvent(new Event("resize"));
        });
    }

    draw();
})();
