//* =========================================================
   SAMPLES PAGE JS
   ELN Integration, File Uploads, Tags & Keywords (Unified)
========================================================= */

function getCsrfToken() {
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value;
}

document.addEventListener("DOMContentLoaded", () => {

    /* =========================================================
       1. ELN / SCIENTIFIC NOTES INTEGRATION
       Syncs Quill editor content to hidden input on MAIN form submit
    ========================================================= */
    const mainSampleForm = document.getElementById("mainSampleForm");

    if (mainSampleForm) {
        mainSampleForm.addEventListener("submit", function() {
            // Se existir um editor Quill na página, salva o HTML
            const quillEditor = document.querySelector('#eln-editor .ql-editor');
            const notesInput = document.getElementById("scientific_notes_input");

            if (quillEditor && notesInput) {
                notesInput.value = quillEditor.innerHTML;
            }
        });
    }

    /* =========================================================
       2. FILE UPLOADS (Dynamic Rows)
    ========================================================= */
    let fileIndex = 0;
    const addFileBtn = document.getElementById("addFileBtn");
    const fileContainer = document.getElementById("fileContainer");

    if (addFileBtn && fileContainer) {
        addFileBtn.addEventListener("click", () => {
            const wrapper = document.createElement("div");
            wrapper.className = "card bg-light p-3 mb-2 border-dashed";

            // IDs únicos para evitar conflitos de nome
            wrapper.innerHTML = `
                <div class="row g-2 align-items-center">
                    <div class="col-md-5">
                        <input type="file" name="file" class="form-control form-control-sm" required>
                    </div>
                    <div class="col-md-3">
                        <input type="text" name="file_type_${fileIndex}" class="form-control form-control-sm" placeholder="Type (e.g. Protocol)">
                    </div>
                    <div class="col-md-3">
                        <input type="text" name="file_description_${fileIndex}" class="form-control form-control-sm" placeholder="Description">
                    </div>
                    <div class="col-md-1 text-end">
                        <button type="button" class="btn btn-sm btn-outline-danger remove-file-btn"><i class="bi bi-trash"></i></button>
                    </div>
                </div>
            `;

            // Lógica de remoção da linha
            wrapper.querySelector(".remove-file-btn").addEventListener("click", () => wrapper.remove());

            fileContainer.appendChild(wrapper);
            fileIndex++;
        });
    }

    /* =========================================================
       3. TAG SYSTEM (AJAX & Selection) - Reused Logic
    ========================================================= */
    function initTagSystem() {
        // Seleção de Chips
        const tagChips = document.querySelectorAll(".selectable-tag");
        const hiddenContainer = document.getElementById("tagHiddenInputs");

        tagChips.forEach(chip => {
            if (chip.dataset.bound) return;
            chip.dataset.bound = "true";

            chip.addEventListener("click", function() {
                const tagId = this.dataset.tagId;

                this.classList.toggle("bg-white");
                this.classList.toggle("text-dark");
                this.classList.toggle("bg-primary");
                this.classList.toggle("text-white");
                this.classList.toggle("border-primary");

                const existingInput = hiddenContainer.querySelector(`input[value="${tagId}"]`);
                if (existingInput) {
                    existingInput.remove();
                } else {
                    const input = document.createElement("input");
                    input.type = "hidden";
                    input.name = "tags";
                    input.value = tagId;
                    hiddenContainer.appendChild(input);
                }
            });
        });

        // Criação AJAX (Clique no botão do Modal)
        const btnSaveTag = document.getElementById("btnSaveTagAJAX");
        if (btnSaveTag) {
            const newBtn = btnSaveTag.cloneNode(true);
            btnSaveTag.parentNode.replaceChild(newBtn, btnSaveTag);

            newBtn.addEventListener("click", function() {
                const nameInput = document.getElementById("tagNameInput");
                const feedback = document.getElementById("tagErrorFeedback");
                const tagName = nameInput?.value.trim();

                if (!tagName) {
                    if(feedback) { feedback.innerText = "Tag name is required."; feedback.style.display = "block"; }
                    return;
                }

                // UI Loading
                const spinner = this.querySelector(".spinner-border");
                if(spinner) spinner.classList.remove("d-none");
                this.disabled = true;

                const fd = new FormData();
                fd.append("name", tagName);

                fetch("/ajax/add_tag/", {
                    method: "POST",
                    body: fd,
                    headers: { "X-CSRFToken": getCsrfToken() }
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success || data.id) {
                        // Update UI
                        const chipContainer = document.getElementById("tagChipContainer");
                        const chip = document.createElement("span");
                        chip.className = "badge rounded-pill border selectable-tag bg-primary text-white border-primary m-1 p-2";
                        chip.dataset.tagId = data.id;
                        chip.style.cursor = "pointer";
                        chip.innerText = data.name;
                        chipContainer?.appendChild(chip);

                        const input = document.createElement("input");
                        input.type = "hidden";
                        input.name = "tags";
                        input.value = data.id;
                        hiddenContainer?.appendChild(input);

                        initTagSystem(); // Rebind

                        nameInput.value = "";
                        const modalEl = document.getElementById("addTagModal");
                        bootstrap.Modal.getInstance(modalEl)?.hide();
                    } else {
                        if(feedback) { feedback.innerText = data.error || "Error creating tag."; feedback.style.display = "block"; }
                    }
                })
                .catch(() => {
                    if(feedback) { feedback.innerText = "Server connection error."; feedback.style.display = "block"; }
                })
                .finally(() => {
                    if(spinner) spinner.classList.add("d-none");
                    newBtn.disabled = false;
                });
            });
        }
    }

    /* =========================================================
       4. KEYWORD SYSTEM (Local Logic)
    ========================================================= */
    function initKeywordSystem() {
        const btnSaveKw = document.getElementById("btnSaveKeywordAJAX");

        if (btnSaveKw) {
            const newBtn = btnSaveKw.cloneNode(true);
            btnSaveKw.parentNode.replaceChild(newBtn, btnSaveKw);

            newBtn.addEventListener("click", function() {
                const keyInput = document.getElementById("keywordKey");
                const valInput = document.getElementById("keywordValue");
                const feedback = document.getElementById("keywordErrorFeedback");

                const key = keyInput?.value.trim();
                const val = valInput?.value.trim();

                if (!key || !val) {
                    if(feedback) { feedback.innerText = "Both Key and Value are required."; feedback.style.display = "block"; }
                    return;
                }

                const chipContainer = document.getElementById("keywordChipContainer");
                const hiddenContainer = document.getElementById("keywordHiddenInputs");
                const pairValue = `${key}:::${val}`;

                const chip = document.createElement("span");
                chip.className = "badge bg-light text-dark border p-2 m-1 d-inline-flex align-items-center";
                chip.innerHTML = `<strong>${key}</strong>: ${val} <i class="bi bi-x ms-2 text-danger" style="cursor:pointer;"></i>`;

                const hidden = document.createElement("input");
                hidden.type = "hidden";
                hidden.name = "keyword_pairs";
                hidden.value = pairValue;

                chip.querySelector(".bi-x").onclick = function() {
                    chip.remove();
                    hidden.remove();
                };

                chipContainer?.appendChild(chip);
                hiddenContainer?.appendChild(hidden);

                keyInput.value = "";
                valInput.value = "";
                if(feedback) feedback.style.display = "none";

                const modalEl = document.getElementById("addKeywordModal");
                bootstrap.Modal.getInstance(modalEl)?.hide();
            });
        }
    }

    // Initialize Systems
    initTagSystem();
    initKeywordSystem();
});