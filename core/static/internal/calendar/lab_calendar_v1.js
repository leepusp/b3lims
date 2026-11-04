(function () {
    "use strict";
    const root = document.getElementById("lab-calendar");
    if (!root) return;
    const urls = {
        events: root.dataset.eventsUrl, resources: root.dataset.resourcesUrl, create: root.dataset.createUrl,
        move: (id) => root.dataset.moveUrl.replace(/0\/move\/$/, id + "/move/"),
        cancel: (id) => root.dataset.cancelUrl.replace(/0\/cancel\/$/, id + "/cancel/"),
        exportView: root.dataset.exportUrl,
    };
    const state = {resources: [], hidden: new Set()};
    const $ = (id) => document.getElementById(id);

    function csrf() {
        const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        if (m) return decodeURIComponent(m[1]);
        const input = document.querySelector("input[name=csrfmiddlewaretoken]");
        return input ? input.value : "";
    }
    function post(url, payload) {
        return fetch(url, {
            method: "POST", credentials: "same-origin",
            headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
            body: JSON.stringify(payload || {}),
        }).then((r) => r.json().catch(() => ({status: "error", message: "Unexpected reply."})).then((d) => { d.ok = r.ok; return d; }));
    }
    function esc(s) { const d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }
    function toast(message, kind) {
        const el = document.createElement("div");
        el.className = "alert alert-" + (kind || "danger") + " shadow-sm py-2 mb-2";
        el.textContent = message; $("lc-toast").appendChild(el);
        setTimeout(() => el.remove(), 6000);
    }
    function localValue(date) {
        const p = (n) => String(n).padStart(2, "0");
        return date.getFullYear() + "-" + p(date.getMonth() + 1) + "-" + p(date.getDate()) + "T" + p(date.getHours()) + ":" + p(date.getMinutes());
    }
    // Bookings are always requested; each custom layer's own checkbox filters them.
    function layers() { return ["bookings"].concat(Array.from(document.querySelectorAll(".lc-layer:checked")).map((c) => c.value)).join(","); }
    function resourceIds() {
        // An empty filter means "all"; once any box is unticked we send the ones left.
        if (!state.hidden.size) return "";
        const shown = state.resources.filter((r) => !state.hidden.has(r.id)).map((r) => r.id);
        return shown.length ? shown.join(",") : "0";
    }

    const modal = new bootstrap.Modal($("lc-modal"));
    const detail = new bootstrap.Modal($("lc-detail"));

    const calendar = new FullCalendar.Calendar($("calendar"), {
        initialView: "dayGridMonth", firstDay: 1, slotMinTime: "06:00:00", slotMaxTime: "22:00:00", scrollTime: "08:00:00", allDaySlot: true, allDayText: "Lab", dayMaxEvents: 4, moreLinkText: (n) => "+" + n + " more", nowIndicator: true, height: "auto",
        headerToolbar: {left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek,timeGridDay,listWeek"},
        buttonText: {today: "Today", month: "Month", week: "Week", day: "Day", list: "Agenda"},
        editable: true, eventStartEditable: true, eventDurationEditable: true, selectable: true, selectMirror: true,
        events: (info, ok, fail) => {
            const q = new URLSearchParams({start: info.startStr, end: info.endStr, layers: layers(), resources: resourceIds()});
            fetch(urls.events + "?" + q, {credentials: "same-origin"}).then((r) => r.json()).then(ok).catch(fail);
        },
        select: (info) => openForm(info.start, info.allDay ? new Date(info.start.getTime() + 3600e3) : info.end),
        eventClick: (info) => {
            const kind = info.event.extendedProps.kind;
            if (kind === "step") return;  // has a URL, FullCalendar follows it
            info.jsEvent.preventDefault(); openDetail(info.event);
        },
        eventDrop: (info) => moveBooking(info), eventResize: (info) => moveBooking(info),
        eventAllow: (drop, ev) => ev.extendedProps.kind === "booking",
    });
    calendar.render();

    function moveBooking(info) {
        const ev = info.event;
        const end = ev.end || new Date(ev.start.getTime() + 3600e3);
        post(urls.move(ev.extendedProps.booking_id), {start: ev.start.toISOString(), end: end.toISOString()}).then((d) => {
            if (d.ok) { toast("Booking updated.", "success"); return; }
            info.revert(); toast(d.message || "That change is not allowed.");
        });
    }

    function openForm(start, end) {
        $("lc-errors").innerHTML = "";
        $("lc-start").value = localValue(start); $("lc-end").value = localValue(end);
        $("lc-title").value = ""; $("lc-note").value = ""; $("lc-repeat").value = ""; $("lc-repeat-box").hidden = true; resetRepeat(start);
        updateNoteHint(); modal.show();
    }
    function bookable() { return state.resources.filter((r) => r.can_book); }
    function updateNoteHint() {
        const r = state.resources.find((x) => String(x.id) === $("lc-resource").value);
        $("lc-note-hint").textContent = r && r.requires_note ? "(required for this layer)" : "";
    }
    $("lc-resource").addEventListener("change", updateNoteHint);
    let weekdaysTouched = false;
    function followStartWeekday(start) {
        if (weekdaysTouched || isNaN(start)) return;
        const weekday = (start.getDay() + 6) % 7;  // Monday = 0
        document.querySelectorAll(".lc-wd").forEach((c) => { c.checked = Number(c.value) === weekday; c.parentElement.classList.toggle("active", c.checked); });
    }
    $("lc-start").addEventListener("change", () => followStartWeekday(new Date($("lc-start").value)));
    function resetRepeat(start) {
        weekdaysTouched = false;
        $("lc-interval").value = 1; $("lc-count").value = 4; $("lc-until").value = ""; $("lc-ends-count").checked = true;
        followStartWeekday(start);
    }
    document.querySelectorAll(".lc-wd").forEach((c) => c.addEventListener("change", () => { weekdaysTouched = true; c.parentElement.classList.toggle("active", c.checked); }));
    $("lc-repeat").addEventListener("change", () => {
        const kind = $("lc-repeat").value;
        $("lc-repeat-box").hidden = !kind;
        $("lc-weekdays").hidden = kind !== "weekly";
        $("lc-interval-unit").textContent = kind === "weekly" ? "week(s)" : "day(s)";
    });
    $("lc-until").addEventListener("focus", () => { $("lc-ends-until").checked = true; });
    $("lc-count").addEventListener("focus", () => { $("lc-ends-count").checked = true; });
    function recurrence() {
        const kind = $("lc-repeat").value;
        if (!kind) return null;
        const rule = {frequency: kind, interval: Number($("lc-interval").value) || 1};
        if (kind === "weekly") rule.weekdays = Array.from(document.querySelectorAll(".lc-wd:checked")).map((c) => Number(c.value));
        if ($("lc-ends-until").checked) rule.until = $("lc-until").value; else rule.count = Number($("lc-count").value);
        return rule;
    }
    $("lc-new").addEventListener("click", () => {
        if (!bookable().length) return toast("There is no layer you can book yet. Use Manage to create one.", "warning");
        const s = new Date(); s.setMinutes(0, 0, 0); s.setHours(s.getHours() + 1);
        openForm(s, new Date(s.getTime() + 3600e3));
    });

    $("lc-form").addEventListener("submit", (e) => {
        e.preventDefault();
        const payload = {
            resource: Number($("lc-resource").value), title: $("lc-title").value, note: $("lc-note").value,
            start: new Date($("lc-start").value).toISOString(), end: new Date($("lc-end").value).toISOString(), entry: $("lc-entry").value || null,
        };
        const rule = recurrence();
        if (rule) payload.recurrence = rule;
        post(urls.create, payload).then((d) => {
            if (d.ok) { modal.hide(); calendar.refetchEvents(); toast(d.created > 1 ? d.created + " bookings created." : "Booking created.", "success"); return; }
            const list = (d.violations || []).map((v) => v.message);
            $("lc-errors").innerHTML = (list.length ? list : [d.message || "Could not book."]).map((m) => "<li>" + esc(m) + "</li>").join("");
        });
    });

    function openDetail(ev) {
        const p = ev.extendedProps, fmt = {dateStyle: "medium", timeStyle: "short"};
        $("lc-detail-title").textContent = ev.title;
        const when = new Intl.DateTimeFormat(undefined, fmt);
        let html = "";
        if (p.kind === "booking") {
            html += "<p class='mb-1'><b>" + esc(p.resource) + "</b> · " + esc(p.who) + "</p>";
            html += "<p class='mb-1'>" + esc(when.format(ev.start)) + " → " + esc(when.format(ev.end)) + "</p>";
            if (p.note) html += "<p class='mb-1 text-muted'>" + esc(p.note) + "</p>";
            if (p.series) html += "<p class='mb-1 small text-muted'><i class='bi bi-arrow-repeat'></i> Part of a recurring series</p>";
            if (p.entry) html += "<p class='mb-0'><i class='bi bi-journal-bookmark'></i> <a href='" + esc(p.entry.url) + "'>" + esc(p.entry.title) + "</a></p>";
        } else if (p.kind === "sample_group") {
            html += "<p class='mb-2 text-muted'>" + esc(new Intl.DateTimeFormat(undefined, {dateStyle: "full"}).format(ev.start)) + "</p>";
            html += "<div class='d-flex flex-wrap gap-1' style='max-height:260px;overflow:auto'>" + p.sample_ids.map((x) => "<span class='badge text-bg-light border'>" + esc(x) + "</span>").join("") + "</div>";
            if (p.more) html += "<p class='small text-muted mt-2 mb-0'>and " + p.more + " more.</p>";
        } else {
            html += "<p class='mb-1'>" + esc(when.format(ev.start)) + "</p>" + (p.who ? "<p class='mb-0 text-muted'>" + esc(p.who) + "</p>" : "");
        }
        $("lc-detail-body").innerHTML = html;
        const actions = $("lc-detail-actions"); actions.innerHTML = "";
        if (p.kind === "booking") {
            const google = document.createElement("a");
            google.className = "btn btn-sm btn-outline-primary"; google.target = "_blank"; google.rel = "noopener";
            google.href = p.google_url; google.innerHTML = "<i class='bi bi-google'></i> Add to Google Calendar";
            const file = document.createElement("a");
            file.className = "btn btn-sm btn-outline-secondary"; file.href = p.ics_url;
            file.innerHTML = "<i class='bi bi-download'></i> .ics";
            actions.appendChild(google); actions.appendChild(file);
        }
        if (p.kind === "booking" && p.can_edit) {
            const one = button("Cancel booking", "btn-outline-danger", () => cancel(p.booking_id, false));
            actions.appendChild(one);
            if (p.series) actions.appendChild(button("Cancel this and the next ones", "btn-outline-danger", () => cancel(p.booking_id, true)));
        }
        actions.appendChild(button("Close", "btn-light", () => detail.hide()));
        detail.show();
    }
    function button(label, cls, fn) {
        const b = document.createElement("button"); b.type = "button"; b.className = "btn btn-sm " + cls; b.textContent = label;
        b.addEventListener("click", fn); return b;
    }
    function cancel(id, series) {
        post(urls.cancel(id), {whole_series: series}).then((d) => {
            if (d.ok) { detail.hide(); calendar.refetchEvents(); toast("Cancelled.", "success"); } else toast(d.message || "Could not cancel.");
        });
    }

    $("lc-export").addEventListener("click", (e) => {
        const view = calendar.view;
        const q = new URLSearchParams({start: view.activeStart.toISOString(), end: view.activeEnd.toISOString(), layers: layers(), resources: resourceIds()});
        e.currentTarget.href = urls.exportView + "?" + q;
    });

    fetch(urls.resources, {credentials: "same-origin"}).then((r) => r.json()).then((d) => {
        state.resources = d.resources;
        const list = $("lc-resources");
        list.innerHTML = d.resources.length ? "" : "No layers to book yet.";
        const builtin = $("lc-builtin");
        d.builtin.forEach((b) => {
            const label = document.createElement("label"); label.className = "lc-check"; label.title = b.description;
            label.innerHTML = "<input type='checkbox' class='lc-layer' value='" + esc(b.key) + "' checked><span class='lc-dot' style='background:" + esc(b.color) + "'></span><span>" + esc(b.label) + "</span>";
            label.querySelector("input").addEventListener("change", () => calendar.refetchEvents());
            builtin.appendChild(label);
        });
        d.resources.forEach((r) => {
            const label = document.createElement("label"); label.className = "lc-check";
            label.title = r.description || "";
            label.innerHTML = "<input type='checkbox' checked><span class='lc-dot' style='background:" + esc(r.color) + "'></span><span>" + esc(r.name) + "</span>";
            label.querySelector("input").addEventListener("change", (e) => {
                if (e.target.checked) state.hidden.delete(r.id); else state.hidden.add(r.id);
                calendar.refetchEvents();
            });
            list.appendChild(label);
        });
        $("lc-resource").innerHTML = bookable().map((r) => "<option value='" + r.id + "'>" + esc(r.name) + "</option>").join("");
        calendar.refetchEvents();
        $("lc-entry").innerHTML = "<option value=''>None</option>" + d.entries.map((e) => "<option value='" + e.id + "'>" + esc(e.title) + "</option>").join("");
    });
})();
