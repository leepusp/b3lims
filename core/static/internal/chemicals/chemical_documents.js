document.addEventListener("DOMContentLoaded", () => {
    const root = document.querySelector("[data-chemical-documents]");
    if (!root) return;

    const list = root.querySelector("[data-document-list]");
    const template = root.querySelector("[data-document-template]");
    const totalInput = root.querySelector("[data-document-total]");
    const addButton = root.querySelector("[data-add-document]");
    const maximumDocuments = 10;

    const updatePrimaryState = (row) => {
        const typeInput = row.querySelector("[data-document-type]");
        const primaryInput = row.querySelector("[data-document-primary]");
        if (!typeInput || !primaryInput) return;

        const isSds = typeInput.value === "sds";
        primaryInput.disabled = !isSds;
        if (!isSds) primaryInput.checked = false;
    };

    const refresh = () => {
        list.querySelectorAll("[data-document-form]").forEach(updatePrimaryState);
        addButton.disabled = (
            list.querySelectorAll("[data-document-form]").length
            >= maximumDocuments
        );
    };

    addButton.addEventListener("click", () => {
        if (list.querySelectorAll("[data-document-form]").length >= maximumDocuments) return;

        const index = Number.parseInt(totalInput.value, 10);
        const wrapper = document.createElement("div");
        wrapper.innerHTML = template.innerHTML
            .replaceAll("__prefix__", String(index))
            .trim();
        list.appendChild(wrapper.firstElementChild);
        totalInput.value = String(index + 1);
        refresh();
    });

    list.addEventListener("click", (event) => {
        const button = event.target.closest("[data-remove-document]");
        if (!button) return;
        button.closest("[data-document-form]").remove();
        refresh();
    });

    list.addEventListener("change", (event) => {
        const row = event.target.closest("[data-document-form]");
        if (!row) return;

        if (event.target.matches("[data-document-type]")) {
            updatePrimaryState(row);
        }

        if (event.target.matches("[data-document-primary]") && event.target.checked) {
            list.querySelectorAll("[data-document-primary]").forEach((input) => {
                if (input !== event.target) input.checked = false;
            });
        }
    });

    refresh();
});
