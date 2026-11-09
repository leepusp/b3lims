/*
 * ELN Tools drawer: calculators, colony counter and multi-timer, available
 * beside any entry. Every calculator can insert its result into the notes.
 * Calculations live in eln_tools_calc.js.
 */
(function () {
    "use strict";

    const C = window.BiobankElnCalc;
    const toggle = document.getElementById("bx-tools");

    if (!C || !toggle) return;

    const el = (tag, cls, text) => {
        const n = document.createElement(tag);

        if (cls) n.className = cls;
        if (text !== undefined) n.textContent = text;

        return n;
    };
    const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[ch]));
    const f = (n) => C.fmt(n);

    function input(label, opts) {
        const wrap = el("label", "bxt-field");
        const i = el("input", "form-control form-control-sm");

        i.type = (opts && opts.type) || "text";
        i.inputMode = i.type === "text" ? "decimal" : "";
        if (opts && opts.placeholder) i.placeholder = opts.placeholder;
        if (opts && opts.value !== undefined) i.value = opts.value;
        wrap.append(el("span", "bxt-label", label), i);

        return {wrap, input: i};
    }

    function insertIntoNotes(title, html) {
        const ed = window.tinymce && window.tinymce.activeEditor;

        if (!ed || (ed.mode && ed.mode.get && ed.mode.get() === "readonly")) {
            window.alert("Open the Notes tab in edit mode to insert the result.");

            return;
        }

        const tbl = ed.dom.getParent(ed.selection.getNode(), "table");

        if (tbl) {
            // Never drop a result inside a table cell: continue after the table.
            const p = ed.dom.create("p", {}, "<br>");

            ed.dom.insertAfter(p, tbl);
            ed.selection.setCursorLocation(p, 0);
        }

        ed.insertContent(`<h3>${esc(title)}</h3>${html}<p><br></p>`);
        ed.setDirty(true);
    }

    const tableHtml = (headers, rows) =>
        `<table class="b3-tpl"><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows
            .map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`)
            .join("")}</tbody></table>`;

    /* A calculator = form fields + run() returning {text, error, html, title}. */
    function calculator(title, intro, fieldDefs, run) {
        const root = el("div", "bxt-calc");
        const out = el("div", "bxt-out");
        const actions = el("div", "bxt-actions");
        const insert = el("button", "btn btn-sm btn-outline-primary", "Insert in notes");
        let last = null;

        insert.type = "button";
        insert.hidden = true;
        insert.addEventListener("click", () => last && last.html && insertIntoNotes(title, last.html));
        actions.append(insert);

        if (intro) root.append(el("p", "bxt-hint", intro));

        const grid = el("div", "bxt-grid");

        fieldDefs.forEach((d) => grid.append(d.wrap));
        root.append(grid, out, actions);

        function update() {
            last = run();
            out.textContent = "";
            out.className = "bxt-out" + (last && last.error ? " is-error" : "");
            insert.hidden = !(last && last.html);

            if (!last) return;
            if (last.error) out.textContent = last.error;
            else if (last.node) out.append(last.node);
            else out.textContent = last.text || "";
            if (last.warning) out.append(el("div", "bxt-warn", last.warning));
        }

        fieldDefs.forEach((d) => d.input.addEventListener("input", update));
        update();

        return root;
    }

    /* Editable rows (name + numeric columns) shared by recipe and master mix. */
    function rowsEditor(columns, initial, onChange) {
        const box = el("div", "bxt-rows");
        const list = el("div");
        const add = el("button", "btn btn-sm btn-link p-0", "+ Add row");
        const rows = [];

        add.type = "button";

        function addRow(values) {
            const row = el("div", "bxt-row");
            const inputs = columns.map((c, idx) => {
                const i = el("input", "form-control form-control-sm");

                i.placeholder = c;
                i.value = (values && values[idx]) || "";
                i.addEventListener("input", onChange);
                row.append(i);

                return i;
            });
            const rm = el("button", "btn btn-sm btn-link text-danger p-0", "×");

            rm.type = "button";
            rm.addEventListener("click", () => {
                rows.splice(rows.indexOf(inputs), 1);
                row.remove();
                onChange();
            });
            row.append(rm);
            list.append(row);
            rows.push(inputs);
        }

        add.addEventListener("click", () => addRow());
        initial.forEach(addRow);
        box.append(list, add);

        return {node: box, values: () => rows.map((r) => r.map((i) => i.value))};
    }

    function buildDilution() {
        const c1 = input("C1 (stock)");
        const v1 = input("V1");
        const c2 = input("C2 (final)");
        const v2 = input("V2 (final volume)");

        return calculator(
            "Dilution (C1·V1 = C2·V2)",
            "Fill three values; the empty one is calculated. Use the same units on both sides.",
            [c1, v1, c2, v2],
            () => {
                if (![c1, v1, c2, v2].some((x) => x.input.value.trim())) return {text: ""};

                const r = C.dilution(c1.input.value, v1.input.value, c2.input.value, v2.input.value);

                if (r.error) return {error: r.error};

                const names = {c1: "C1", v1: "V1", c2: "C2", v2: "V2"};

                return {
                    text: `${names[r.solved]} = ${f(r.value)}  ·  add ${f(r.v1)} of stock + ${f(r.diluent)} of diluent`,
                    warning: r.warning,
                    html: tableHtml(["C1", "V1", "C2", "V2", "Diluent"], [[f(r.c1), f(r.v1), f(r.c2), f(r.v2), f(r.diluent)]]),
                };
            }
        );
    }

    function buildSolution() {
        const mw = input("Molecular weight (g/mol)");
        const conc = input("Concentration (mM)");
        const vol = input("Volume (mL)");
        const mass = input("Mass (mg)");

        return calculator(
            "Solution / molarity",
            "Fill MW and two of the other fields; the empty one is calculated.",
            [mw, conc, vol, mass],
            () => {
                if (![mw, conc, vol, mass].some((x) => x.input.value.trim())) return {text: ""};

                const r = C.solution(mw.input.value, conc.input.value, vol.input.value, mass.input.value);

                if (r.error) return {error: r.error};

                return {
                    text: `Weigh ${f(r.mass)} mg and make up to ${f(r.vol)} mL for ${f(r.conc)} mM (MW ${f(r.mw)})`,
                    html: tableHtml(["MW (g/mol)", "Concentration (mM)", "Volume (mL)", "Mass (mg)"], [[f(r.mw), f(r.conc), f(r.vol), f(r.mass)]]),
                };
            }
        );
    }

    function buildRecipe() {
        const vf = input("Final volume (mL)", {value: "100"});
        let editor;
        const calc = calculator(
            "Buffer / stock recipe",
            "Per component: stock and final concentration in the same unit (for a 10x stock use 10 and 1). Water fills the rest.",
            [vf],
            () => {
                if (!editor) return {text: ""};

                const comps = editor.values().map((v) => ({name: v[0], stock: v[1], final: v[2]}));
                const r = C.recipe(vf.input.value, comps);

                if (r.error) return {error: r.error};

                const rows = r.rows.map((x) => [x.name, f(x.stock), f(x.final), f(x.volume)]);

                rows.push(["Water", "", "", f(r.water)]);

                const node = el("div");

                rows.forEach((x) => node.append(el("div", "bxt-line", `${x[0] || "—"}: ${x[3]} mL`)));

                return {node, html: tableHtml(["Component", "Stock", "Final", "Volume (mL)"], rows)};
            }
        );

        editor = rowsEditor(["Component", "Stock", "Final"], [["Tris-HCl", "1000", "50"], ["NaCl", "5000", "150"], ["", "", ""]], () => vf.input.dispatchEvent(new Event("input")));
        calc.insertBefore(editor.node, calc.querySelector(".bxt-out"));
        vf.input.dispatchEvent(new Event("input"));

        return calc;
    }

    function buildMasterMix() {
        const n = input("Reactions", {value: "10"});
        const over = input("Overage (%)", {value: "10"});
        let editor;
        const calc = calculator(
            "Master mix",
            "Volumes per reaction in µL; totals include the overage.",
            [n, over],
            () => {
                if (!editor) return {text: ""};

                const comps = editor.values().map((v) => ({name: v[0], perReaction: v[1]}));
                const r = C.masterMix(n.input.value, over.input.value, comps);

                if (r.error) return {error: r.error};

                const rows = r.rows.map((x) => [x.name, f(x.perReaction), f(x.total)]);

                rows.push(["Total", f(r.perReactionTotal), f(r.total)]);

                const node = el("div");

                rows.forEach((x) => node.append(el("div", "bxt-line", `${x[0] || "—"}: ${x[2]} µL`)));

                return {node, html: tableHtml(["Component", "Per reaction (µL)", `Total for ${f(r.reactions)} + ${f(r.overage)}% (µL)`], rows)};
            }
        );

        editor = rowsEditor(["Component", "µL / rxn"], [["Buffer", "2"], ["dNTPs", "1"], ["Primer F", "1"], ["Primer R", "1"], ["Polymerase", "0.5"], ["Water", "14.5"]], () => n.input.dispatchEvent(new Event("input")));
        calc.insertBefore(editor.node, calc.querySelector(".bxt-out"));
        n.input.dispatchEvent(new Event("input"));

        return calc;
    }

    function buildColony() {
        const root = el("div", "bxt-calc");
        const pick = el("input", "form-control form-control-sm");
        const stage = el("div", "bxt-stage");
        const canvas = el("canvas");
        const count = el("div", "bxt-count", "0 colonies");
        const buttons = el("div", "bxt-actions");
        const undo = el("button", "btn btn-sm btn-outline-secondary", "Undo");
        const clear = el("button", "btn btn-sm btn-outline-secondary", "Clear");
        const plate = input("Plated volume (mL)", {value: "0.1"});
        const exp = input("Dilution 10^-n, n =", {value: "6"});
        const out = el("div", "bxt-out");
        const insert = el("button", "btn btn-sm btn-outline-primary", "Insert in notes");
        const dots = [];
        let img = null;

        pick.type = "file";
        pick.accept = "image/*";
        undo.type = clear.type = insert.type = "button";
        stage.append(canvas);
        buttons.append(undo, clear, insert);
        root.append(
            el("p", "bxt-hint", "Load a plate photo and click each colony. Shift-click removes the nearest mark."),
            pick, stage, count,
            Object.assign(el("div", "bxt-grid"), {}),
            out, buttons
        );
        root.querySelector(".bxt-grid").append(plate.wrap, exp.wrap);

        function draw() {
            const ctx = canvas.getContext("2d");

            if (!img) return;

            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            ctx.lineWidth = 2;
            ctx.strokeStyle = "#ef4444";
            ctx.fillStyle = "#ef4444";
            ctx.font = "bold 11px sans-serif";
            dots.forEach((d, i) => {
                ctx.beginPath();
                ctx.arc(d[0], d[1], 6, 0, 2 * Math.PI);
                ctx.stroke();
                ctx.fillText(String(i + 1), d[0] + 7, d[1] - 7);
            });
        }

        function refresh() {
            const n = dots.length;
            const r = C.cfu(n, plate.input.value, exp.input.value);

            count.textContent = `${n} ${n === 1 ? "colony" : "colonies"}`;
            out.className = "bxt-out" + (r.error ? " is-error" : "");
            out.textContent = r.error || `${f(r.perMl)} CFU/mL`;
            if (r.note && !r.error) out.append(el("div", "bxt-warn", r.note));
            insert.hidden = Boolean(r.error);
            draw();
        }

        pick.addEventListener("change", () => {
            const file = pick.files && pick.files[0];

            if (!file) return;

            const url = URL.createObjectURL(file);
            const image = new Image();

            image.onload = () => {
                img = image;
                canvas.width = 520;
                canvas.height = Math.round((520 * image.height) / image.width);
                dots.length = 0;
                URL.revokeObjectURL(url);
                refresh();
            };
            image.src = url;
        });
        canvas.addEventListener("click", (e) => {
            if (!img) return;

            const rect = canvas.getBoundingClientRect();
            const x = ((e.clientX - rect.left) * canvas.width) / rect.width;
            const y = ((e.clientY - rect.top) * canvas.height) / rect.height;

            if (e.shiftKey) {
                let best = -1;
                let bd = 14 * 14;

                dots.forEach((d, i) => {
                    const dd = (d[0] - x) ** 2 + (d[1] - y) ** 2;

                    if (dd < bd) {
                        bd = dd;
                        best = i;
                    }
                });
                if (best >= 0) dots.splice(best, 1);
            } else dots.push([x, y]);

            refresh();
        });
        undo.addEventListener("click", () => { dots.pop(); refresh(); });
        clear.addEventListener("click", () => { dots.length = 0; refresh(); });
        [plate.input, exp.input].forEach((i) => i.addEventListener("input", refresh));
        insert.addEventListener("click", () => {
            const r = C.cfu(dots.length, plate.input.value, exp.input.value);

            if (!r.error) insertIntoNotes("Colony count", tableHtml(["Colonies", "Plated (mL)", "Dilution", "CFU/mL"], [[dots.length, plate.input.value, `10^-${exp.input.value}`, f(r.perMl)]]));
        });
        refresh();

        return root;
    }

    function buildTimers() {
        const root = el("div", "bxt-calc");
        const list = el("div", "bxt-timers");
        const name = input("Label", {placeholder: "e.g. Incubation"});
        const mins = input("Minutes", {value: "10"});
        const add = el("button", "btn btn-sm btn-primary", "Add timer");
        const timers = [];
        let audio = null;

        add.type = "button";
        root.append(el("p", "bxt-hint", "Timers keep running while you work in the entry. Closing the page stops them."), list);
        const grid = el("div", "bxt-grid");

        grid.append(name.wrap, mins.wrap);
        root.append(grid, add);

        function beep() {
            try {
                audio = audio || new (window.AudioContext || window.webkitAudioContext)();

                const o = audio.createOscillator();

                o.frequency.value = 880;
                o.connect(audio.destination);
                o.start();
                o.stop(audio.currentTime + 0.6);
            } catch (e) { /* no audio available */ }
        }

        const clock = (s) => {
            const a = Math.max(0, Math.round(s));

            return `${String(Math.floor(a / 3600)).padStart(2, "0")}:${String(Math.floor((a % 3600) / 60)).padStart(2, "0")}:${String(a % 60).padStart(2, "0")}`;
        };

        add.addEventListener("click", () => {
            const m = C.num(mins.input.value);

            if (!m || m <= 0) return;

            const t = {label: name.input.value.trim() || "Timer", total: m * 60, left: m * 60, running: false, done: false};
            const row = el("div", "bxt-timer");
            const title = el("span", "bxt-timer-name", t.label);
            const time = el("span", "bxt-timer-time", clock(t.left));
            const go = el("button", "btn btn-sm btn-outline-primary", "Start");
            const reset = el("button", "btn btn-sm btn-outline-secondary", "Reset");
            const rm = el("button", "btn btn-sm btn-link text-danger p-0", "×");

            go.type = reset.type = rm.type = "button";
            t.paint = () => {
                time.textContent = clock(t.left);
                row.classList.toggle("is-done", t.done);
                go.textContent = t.running ? "Pause" : "Start";
            };
            go.addEventListener("click", () => {
                if (t.done) return;

                t.running = !t.running;
                t.last = Date.now();
                t.paint();
            });
            reset.addEventListener("click", () => { t.left = t.total; t.running = false; t.done = false; t.paint(); });
            rm.addEventListener("click", () => { timers.splice(timers.indexOf(t), 1); row.remove(); });
            row.append(title, time, go, reset, rm);
            list.append(row);
            timers.push(t);
        });

        setInterval(() => {
            const now = Date.now();

            timers.forEach((t) => {
                if (!t.running) return;

                t.left -= (now - t.last) / 1000;
                t.last = now;

                if (t.left <= 0) {
                    t.left = 0;
                    t.running = false;
                    t.done = true;
                    beep();
                }

                t.paint();
            });
        }, 250);

        return root;
    }

    function buildPeriodic() {
        const root = el("div", "bxt-calc");
        const E = window.BiobankElnElements;

        if (!E) {
            root.append(el("p", "bxt-hint", "Periodic table data is not loaded."));

            return root;
        }

        const grid = el("div", "bxt-pt");
        const detail = el("div", "bxt-out", "Click an element.");
        const insertEl = el("button", "btn btn-sm btn-outline-primary", "Insert in notes");
        let current = null;

        insertEl.type = "button";
        insertEl.hidden = true;
        insertEl.addEventListener("click", () => current && insertIntoNotes(current.name, tableHtml(
            ["Symbol", "Atomic number", "Atomic mass (g/mol)", "Category"],
            [[current.symbol, current.z, current.radioactive ? `[${current.mass}]` : C.fmt(current.mass, 4), current.category]]
        )));

        E.list.forEach((e) => {
            const cell = el("button", `bxt-el cat-${e.category}`);

            cell.type = "button";
            cell.style.gridRow = String(e.row);
            cell.style.gridColumn = String(e.col);
            cell.title = `${e.name} · ${e.mass}`;
            cell.append(el("small", "", String(e.z)), el("b", "", e.symbol));
            cell.addEventListener("click", () => {
                current = e;
                detail.textContent = `${e.name} (${e.symbol}) · Z ${e.z} · ${e.radioactive ? `[${e.mass}]` : C.fmt(e.mass, 4)} g/mol · ${e.category}`;
                insertEl.hidden = false;
            });
            grid.append(cell);
        });

        const formula = input("Molar mass of a formula", {placeholder: "C6H12O6, Ca(OH)2, CuSO4·5H2O"});
        const mass = el("div", "bxt-out");
        const insertMass = el("button", "btn btn-sm btn-outline-primary", "Insert in notes");
        let last = null;

        insertMass.type = "button";
        insertMass.hidden = true;
        insertMass.addEventListener("click", () => last && insertIntoNotes("Molar mass", tableHtml(["Formula", "Molar mass (g/mol)"], [[formula.input.value.trim(), C.fmt(last, 4)]])));
        formula.input.addEventListener("input", () => {
            const r = E.molarMass(formula.input.value);

            last = null;
            insertMass.hidden = true;
            mass.className = "bxt-out" + (r.error && formula.input.value.trim() ? " is-error" : "");

            if (!formula.input.value.trim()) mass.textContent = "";
            else if (r.error) mass.textContent = r.error;
            else {
                last = r.mass;
                mass.textContent = `${C.fmt(r.mass, 4)} g/mol`;
                insertMass.hidden = false;
            }
        });

        const actions = el("div", "bxt-actions");

        actions.append(insertEl);

        const massActions = el("div", "bxt-actions");

        massActions.append(insertMass);
        root.append(grid, detail, actions, formula.wrap, mass, massActions);

        return root;
    }

    const TABS = [
        ["dilution", "Dilution", buildDilution],
        ["solution", "Molarity", buildSolution],
        ["recipe", "Buffer", buildRecipe],
        ["mix", "Master mix", buildMasterMix],
        ["colony", "Colonies", buildColony],
        ["timers", "Timers", buildTimers],
        ["periodic", "Periodic", buildPeriodic],
    ];

    let drawer = null;

    function build() {
        drawer = el("aside", "bxt-drawer");
        drawer.setAttribute("aria-label", "Lab tools");

        const head = el("div", "bxt-head");
        const close = el("button", "btn-close");
        const tabs = el("div", "bxt-tabs");
        const body = el("div", "bxt-body");
        const built = {};

        const minimize = el("button", "bxt-head-btn", "–");
        const widen = el("button", "bxt-head-btn", "⤢");
        const controls = el("div", "bxt-head-controls");

        close.type = "button";
        close.setAttribute("aria-label", "Close");
        close.addEventListener("click", () => drawer.classList.remove("is-open"));
        minimize.type = widen.type = "button";
        minimize.title = "Minimize to the title bar";
        minimize.addEventListener("click", () => {
            const min = drawer.classList.toggle("is-min");

            minimize.textContent = min ? "▢" : "–";
            minimize.title = min ? "Restore" : "Minimize to the title bar";
        });
        widen.title = "Make the panel larger";
        widen.addEventListener("click", () => {
            drawer.classList.toggle("is-wide");
            widen.classList.toggle("is-on", drawer.classList.contains("is-wide"));
        });
        controls.append(widen, minimize, close);
        head.append(el("strong", "", "Lab tools"), controls);

        function show(key) {
            tabs.querySelectorAll("button").forEach((b) => b.classList.toggle("is-active", b.dataset.key === key));
            body.querySelectorAll("[data-pane]").forEach((p) => { p.hidden = p.dataset.pane !== key; });

            if (!built[key]) {
                const pane = el("div");

                pane.dataset.pane = key;
                pane.append(TABS.find((t) => t[0] === key)[2]());
                body.append(pane);
                built[key] = pane;
            }

            built[key].hidden = false;
        }

        TABS.forEach(([key, label]) => {
            const b = el("button", "bxt-tab", label);

            b.type = "button";
            b.dataset.key = key;
            b.addEventListener("click", () => show(key));
            tabs.append(b);
        });

        drawer.append(head, tabs, body);
        document.body.append(drawer);
        show("dilution");
    }

    toggle.addEventListener("click", () => {
        if (!drawer) build();

        drawer.classList.toggle("is-open");
    });
})();
