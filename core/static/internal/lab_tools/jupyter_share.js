(function () {
    "use strict";

    const modalEl = document.getElementById("jp-share");

    if (!modalEl) return;

    const $ = (id) => document.getElementById(id);
    const csrf = () => (document.querySelector("input[name=csrfmiddlewaretoken]") || {}).value || "";
    let current = null;
    let timer = null;

    function esc(text) {
        const div = document.createElement("div");

        div.textContent = text == null ? "" : String(text);

        return div.innerHTML;
    }

    function showError(message) {
        $("jp-share-error").textContent = message || "";
        $("jp-share-error").hidden = !message;
    }

    async function call(payload) {
        showError("");

        const response = await fetch(modalEl.dataset.urlTemplate.replace("/0/", "/" + current + "/"), {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-CSRFToken": csrf()},
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));

        if (!response.ok || data.status !== "success") {
            showError(data.message || "Could not save.");

            return null;
        }

        return data;
    }

    function render(data) {
        if (!data || data.visibility === undefined) return;

        $("jp-share-visibility").value = data.visibility;
        $("jp-share-list").innerHTML = data.grants.length ? data.grants.map((g) => "<li class='d-flex justify-content-between border-bottom py-1'><span>"
            + esc(g.name) + " <span class='text-muted'>" + esc(g.detail) + "</span></span><button type='button' class='btn btn-sm btn-link text-danger p-0' data-remove='" + g.id + "'>Remove</button></li>").join("")
            : "<li class='text-muted'>Nobody yet.</li>";
        $("jp-share-list").querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", async () => render(await call({action: "remove", grant_id: Number(b.dataset.remove)}))));
    }

    document.querySelectorAll("[data-share]").forEach((button) => button.addEventListener("click", async () => {
        current = button.dataset.share;
        $("jp-share-title").textContent = "Share: " + button.dataset.title;
        $("jp-share-q").value = "";
        $("jp-share-results").innerHTML = "";
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
        render(await call({action: "get"}));
    }));

    $("jp-share-visibility").addEventListener("change", async () => render(await call({action: "set_visibility", visibility: $("jp-share-visibility").value})));

    $("jp-share-q").addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(async () => {
            const data = await call({action: "search", q: $("jp-share-q").value});

            if (!data) return;

            $("jp-share-results").innerHTML = data.results.map((r, i) => "<button type='button' class='list-group-item list-group-item-action py-1 small' data-i='" + i + "'>" + esc(r.name) + " <span class='text-muted'>" + esc(r.detail) + "</span></button>").join("");
            $("jp-share-results").querySelectorAll("[data-i]").forEach((b) => b.addEventListener("click", async () => {
                const r = data.results[Number(b.dataset.i)];
                const saved = await call({action: "add", kind: r.kind, principal_id: r.principal_id});

                if (saved) {
                    $("jp-share-q").value = "";
                    $("jp-share-results").innerHTML = "";
                    render(saved);
                }
            }));
        }, 250);
    });
})();
