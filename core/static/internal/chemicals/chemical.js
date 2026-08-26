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

document.addEventListener("DOMContentLoaded", () => {
    const metadataRoot = document.querySelector("[data-chemical-metadata]");
    if (!metadataRoot) return;

    const tagList = metadataRoot.querySelector("[data-chemical-tag-list]");
    const tagInputs = metadataRoot.querySelector("[data-chemical-tag-inputs]");
    const keywordList = metadataRoot.querySelector(
        "[data-chemical-keyword-list]"
    );

    const syncTagInputs = () => {
        tagInputs.replaceChildren();

        metadataRoot
            .querySelectorAll("[data-chemical-tag].selected")
            .forEach((button) => {
                const input = document.createElement("input");
                input.type = "hidden";
                input.name = "tags";
                input.value = button.dataset.tagId;
                tagInputs.appendChild(input);
            });
    };

    const bindTagButton = (button) => {
        if (button.dataset.metadataBound === "true") return;
        button.dataset.metadataBound = "true";

        button.addEventListener("click", () => {
            button.classList.toggle("selected");
            button.classList.toggle("btn-primary");
            button.classList.toggle("btn-outline-secondary");
            syncTagInputs();
        });
    };

    metadataRoot
        .querySelectorAll("[data-chemical-tag]")
        .forEach(bindTagButton);

    const tagForm = document.getElementById("addTagForm");

    if (tagForm) {
        tagForm.addEventListener("submit", async (event) => {
            event.preventDefault();

            const feedback = document.getElementById("tagErrorFeedback");
            const submitButton = document.getElementById(
                "btnSaveTagAJAX"
            );

            feedback.style.display = "none";
            submitButton.disabled = true;

            try {
                const response = await fetch(
                    tagForm.dataset.createUrl,
                    {
                        method: "POST",
                        body: new FormData(tagForm),
                        credentials: "same-origin",
                        headers: {
                            "X-Requested-With": "XMLHttpRequest",
                        },
                    }
                );

                const data = await response.json();

                if (!response.ok || !data.success) {
                    throw new Error(
                        data.error || "The tag could not be created."
                    );
                }

                let button = tagList.querySelector(
                    `[data-chemical-tag][data-tag-id="${data.id}"]`
                );

                if (!button) {
                    button = document.createElement("button");
                    button.type = "button";
                    button.className = (
                        "btn btn-sm rounded-pill mb-1 " +
                        "chemical-tag-option btn-primary selected"
                    );
                    button.dataset.chemicalTag = "";
                    button.dataset.tagId = String(data.id);
                    button.textContent = data.name;
                    tagList.querySelector("[data-empty-tags]")?.remove();
                    tagList.appendChild(button);
                    bindTagButton(button);
                } else if (!button.classList.contains("selected")) {
                    button.classList.add("selected", "btn-primary");
                    button.classList.remove("btn-outline-secondary");
                }

                syncTagInputs();
                tagForm.reset();

                const modalElement = document.getElementById(
                    "addTagModal"
                );
                const modal = window.bootstrap?.Modal.getInstance(
                    modalElement
                );
                modal?.hide();
            } catch (error) {
                feedback.textContent = error.message;
                feedback.style.display = "block";
            } finally {
                submitButton.disabled = false;
            }
        });
    }

    const bindKeywordRemove = (button) => {
        if (button.dataset.metadataBound === "true") return;
        button.dataset.metadataBound = "true";

        button.addEventListener("click", () => {
            button.closest("[data-chemical-keyword]")?.remove();

            if (
                !keywordList.querySelector(
                    "[data-chemical-keyword]"
                )
            ) {
                const empty = document.createElement("span");
                empty.className = "text-muted small";
                empty.dataset.emptyKeywords = "";
                empty.textContent = "No keywords assigned.";
                keywordList.appendChild(empty);
            }
        });
    };

    metadataRoot
        .querySelectorAll("[data-remove-chemical-keyword]")
        .forEach(bindKeywordRemove);

    const keywordForm = document.getElementById("addKeywordForm");

    if (keywordForm) {
        keywordForm.addEventListener("submit", (event) => {
            event.preventDefault();

            const keyInput = document.getElementById("keywordKey");
            const valueInput = document.getElementById("keywordValue");
            const feedback = document.getElementById(
                "keywordErrorFeedback"
            );

            const key = keyInput.value.trim().replace(/\s+/g, " ");
            const value = valueInput.value
                .trim()
                .replace(/\s+/g, " ");

            if (!key || !value) {
                feedback.textContent = (
                    "Both keyword name and value are required."
                );
                feedback.style.display = "block";
                return;
            }

            feedback.style.display = "none";

            const duplicate = Array.from(
                keywordList.querySelectorAll(
                    "[data-chemical-keyword]"
                )
            ).some((item) => (
                item.dataset.keyword.toLocaleLowerCase()
                    === key.toLocaleLowerCase()
                && item.dataset.value.toLocaleLowerCase()
                    === value.toLocaleLowerCase()
            ));

            if (duplicate) {
                feedback.textContent = (
                    "This keyword and value are already assigned."
                );
                feedback.style.display = "block";
                return;
            }

            keywordList.querySelector(
                "[data-empty-keywords]"
            )?.remove();

            const chip = document.createElement("span");
            chip.className = (
                "badge text-bg-light border text-dark p-2 " +
                "d-flex align-items-center gap-2"
            );
            chip.dataset.chemicalKeyword = "";
            chip.dataset.keyword = key;
            chip.dataset.value = value;

            const label = document.createElement("span");
            label.textContent = `${key}: ${value}`;

            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "btn-close";
            remove.style.fontSize = ".55rem";
            remove.setAttribute("aria-label", "Remove keyword");
            remove.dataset.removeChemicalKeyword = "";

            const hidden = document.createElement("input");
            hidden.type = "hidden";
            hidden.name = "keyword_pairs";
            hidden.value = `${key}:::${value}`;

            chip.append(label, remove, hidden);
            keywordList.appendChild(chip);
            bindKeywordRemove(remove);

            keywordForm.reset();

            const modalElement = document.getElementById(
                "addKeywordModal"
            );
            const modal = window.bootstrap?.Modal.getInstance(
                modalElement
            );
            modal?.hide();
        });
    }
});
