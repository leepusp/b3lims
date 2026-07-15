document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-storage-builder]").forEach((builder) => {
        const hidden = builder.querySelector("[data-storage-value]");
        const container = builder.querySelector("[data-storage-levels]");
        const input = builder.querySelector("[data-storage-input]");
        if (!hidden || !container || !input) return;

        let levels = String(hidden.value || "")
            .replace(/[;,]/g, ">")
            .split(">")
            .map((value) => value.trim())
            .filter(Boolean);

        const render = () => {
            container.querySelectorAll("[data-storage-level]").forEach((node) => node.remove());
            levels.forEach((level, index) => {
                const wrapper = document.createElement("span");
                wrapper.className = "chemical-storage-level badge bg-primary";
                wrapper.dataset.storageLevel = "";

                const label = document.createElement("span");
                label.textContent = level;
                wrapper.appendChild(label);

                const remove = document.createElement("button");
                remove.type = "button";
                remove.setAttribute("aria-label", `Remove ${level}`);
                remove.innerHTML = '<i class="bi bi-x-circle-fill"></i>';
                remove.addEventListener("click", () => {
                    levels.splice(index, 1);
                    render();
                });
                wrapper.appendChild(remove);
                container.insertBefore(wrapper, input);
            });
            hidden.value = levels.join(" > ");
        };

        const addLevel = () => {
            const value = input.value.trim().replace(/[>,;]+$/, "").trim();
            if (!value) return;
            levels.push(value);
            input.value = "";
            render();
        };

        input.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === ",") {
                event.preventDefault();
                addLevel();
            } else if (event.key === "Backspace" && !input.value && levels.length) {
                levels.pop();
                render();
            }
        });
        input.addEventListener("blur", addLevel);
        builder.addEventListener("click", () => input.focus());
        render();
    });
});
