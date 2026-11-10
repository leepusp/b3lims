(function () {
    "use strict";

    const box = document.getElementById("bx-trace");
    const stateNode = document.getElementById("bx-state");

    if (!box || !stateNode) return;

    const page = JSON.parse(stateNode.textContent);
    const url = page.urls && page.urls.trace;
    const csrf = () => {
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);

        return match ? decodeURIComponent(match[1]) : (window.csrfToken || "");
    };
    let trace = null;
    let error = "";

    function esc(text) {
        const div = document.createElement("div");

        div.textContent = text == null ? "" : String(text);

        return div.innerHTML;
    }

    async function call(payload) {
        error = "";

        const response = await fetch(url, {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));

        if (!response.ok || data.status !== "success") {
            error = data.message || "Could not save.";
            render();

            return null;
        }

        trace = data.trace;
        render();

        return data;
    }

    function badge() {
        const el = document.getElementById("bx-count-record");

        if (el && trace) el.textContent = trace.locked ? "Signed" : trace.deviations.length ? String(trace.deviations.length) : "";
    }

    function signatureRow(s) {
        const state = s.superseded_at ? "<span class='badge text-bg-secondary'>Voided " + esc(s.superseded_at) + "</span>"
            : s.intact ? "<span class='badge text-bg-success'>Intact</span>" : "<span class='badge text-bg-danger'>Changed after signing</span>";

        return "<li class='border-bottom py-2'><div><b>" + esc(s.signer) + "</b> &middot; " + esc(s.meaning_label) + " " + state + "</div>"
            + "<div class='small text-muted'>" + esc(s.at) + " &middot; <code>" + esc(s.sha256.slice(0, 12)) + "</code></div>"
            + (s.comment ? "<div class='small'>" + esc(s.comment) + "</div>" : "")
            + (s.superseded_reason ? "<div class='small text-muted'>Amended by " + esc(s.superseded_by) + ": " + esc(s.superseded_reason) + "</div>" : "") + "</li>";
    }

    function deviationRow(d) {
        const cls = d.impact === "major" ? "danger" : d.impact === "minor" ? "warning" : "secondary";

        return "<li class='border-bottom py-2'><div><span class='badge text-bg-" + cls + "'>" + esc(d.impact_label) + "</span> "
            + (d.step ? "<span class='text-muted'>" + esc(d.step) + "</span> " : "") + (d.resolved ? "<span class='badge text-bg-success'>Resolved</span>" : "") + "</div>"
            + "<div>" + esc(d.description) + "</div><div class='small text-muted'>" + esc(d.by) + " &middot; " + esc(d.at) + "</div>"
            + (d.resolved ? "<div class='small'>Resolution: " + esc(d.resolution) + " <span class='text-muted'>(" + esc(d.resolved_by) + ", " + esc(d.resolved_at) + ")</span></div>"
                : trace.can_record ? "<button type='button' class='btn btn-sm btn-link p-0' data-resolve='" + d.id + "'>Mark as resolved</button>" : "") + "</li>";
    }

    function render() {
        if (!trace) return;

        badge();

        const buttons = [];

        if (trace.can_sign_author) buttons.push("<button type='button' class='btn btn-sm btn-primary' data-sign='author'>Sign and lock</button>");
        if (trace.can_sign_witness) buttons.push("<button type='button' class='btn btn-sm btn-outline-primary' data-sign='witness'>Sign as witness</button>");
        if (trace.can_sign_reviewer) buttons.push("<button type='button' class='btn btn-sm btn-outline-primary' data-sign='reviewer'>Sign as reviewer</button>");
        if (trace.can_amend) buttons.push("<button type='button' class='btn btn-sm btn-outline-danger' data-amend='1'>Amend (unlock)</button>");

        box.innerHTML = (error ? "<div class='alert alert-danger py-1 small'>" + esc(error) + "</div>" : "")
            + "<div class='mb-3'><h3 class='h6'>Signatures</h3>"
            + "<div class='small text-muted mb-2'>" + (trace.locked ? "This entry is signed and locked. To change it the author has to amend it, with a reason; the signatures are kept as history."
                : "Signing records who stands behind this page and locks it, so what was signed cannot change silently.") + "</div>"
            + (buttons.length ? "<div class='d-flex flex-wrap gap-2 mb-2'>" + buttons.join("") + "</div>" : "")
            + "<div id='bx-trace-form' hidden class='border rounded p-2 mb-2'></div>"
            + (trace.signatures.length ? "<ul class='list-unstyled mb-0'>" + trace.signatures.map(signatureRow).join("") + "</ul>" : "<div class='text-muted small'>No signatures yet.</div>") + "</div>"
            + "<div><h3 class='h6'>Deviations</h3><div class='small text-muted mb-2'>What went differently from the plan. They can be added after signing.</div>"
            + (trace.can_record ? "<button type='button' class='btn btn-sm btn-outline-secondary mb-2' data-deviation='1'>Record a deviation</button>" : "")
            + (trace.deviations.length ? "<ul class='list-unstyled mb-0'>" + trace.deviations.map(deviationRow).join("") + "</ul>" : "<div class='text-muted small'>None recorded.</div>") + "</div>";

        box.querySelectorAll("[data-sign]").forEach((b) => b.addEventListener("click", () => form("sign", b.dataset.sign)));
        box.querySelectorAll("[data-amend]").forEach((b) => b.addEventListener("click", () => form("amend")));
        box.querySelectorAll("[data-deviation]").forEach((b) => b.addEventListener("click", () => form("deviation")));
        box.querySelectorAll("[data-resolve]").forEach((b) => b.addEventListener("click", () => form("resolve", b.dataset.resolve)));
    }

    function form(kind, extra) {
        const holder = document.getElementById("bx-trace-form");
        const field = (label, id, tag) => "<label class='form-label small mb-1' for='" + id + "'>" + label + "</label>" + tag;
        const text = (id, rows) => "<textarea class='form-control form-control-sm mb-2' id='" + id + "' rows='" + (rows || 2) + "' maxlength='3000'></textarea>";
        let html = "";
        let submit = null;

        if (kind === "sign") {
            html = field("Comment (optional)", "tr-comment", "<input class='form-control form-control-sm mb-2' id='tr-comment' maxlength='500'>");
            submit = () => call({action: "sign", meaning: extra, comment: document.getElementById("tr-comment").value});
        } else if (kind === "amend") {
            html = field("Why does this signed entry need to change? (required)", "tr-reason", text("tr-reason"))
                + "<div class='small text-muted mb-2'>All signatures are voided and kept as history; the signed text is saved as a revision.</div>";
            submit = () => call({action: "amend", reason: document.getElementById("tr-reason").value});
        } else if (kind === "deviation") {
            html = field("Step or part affected (optional)", "tr-step", "<input class='form-control form-control-sm mb-2' id='tr-step' maxlength='500'>")
                + field("What differed from the plan", "tr-desc", text("tr-desc", 3))
                + field("Impact", "tr-impact", "<select class='form-select form-select-sm mb-2' id='tr-impact'><option value='none'>No impact</option><option value='minor' selected>Minor</option><option value='major'>Major</option></select>");
            submit = () => call({action: "add_deviation", step: document.getElementById("tr-step").value, description: document.getElementById("tr-desc").value, impact: document.getElementById("tr-impact").value});
        } else {
            html = field("How was it resolved?", "tr-res", text("tr-res"));
            submit = () => call({action: "resolve_deviation", id: Number(extra), resolution: document.getElementById("tr-res").value});
        }

        holder.hidden = false;
        holder.innerHTML = html + "<button type='button' class='btn btn-sm btn-primary' id='tr-go'>Confirm</button> <button type='button' class='btn btn-sm btn-light' id='tr-cancel'>Cancel</button>";
        document.getElementById("tr-go").addEventListener("click", submit);
        document.getElementById("tr-cancel").addEventListener("click", () => { holder.hidden = true; });
    }

    if (url) call({action: "state"});
})();
