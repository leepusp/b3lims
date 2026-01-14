/* ===============================================================
    SAMPLES PAGE JS
    Gerenciamento de Tags, Keywords e Upload de Arquivos Múltiplos
=============================================================== */

document.addEventListener("DOMContentLoaded", () => {

    /* ===============================================================
        TAGS (Seleção de Chips Existentes)
    =============================================================== */
    function initTagSelector() {
        const tagChips = document.querySelectorAll(".selectable-tag");
        const hiddenContainer = document.getElementById("tagHiddenInputs");

        tagChips.forEach(chip => {
            if (chip.dataset.bound === "1") return;

            chip.addEventListener("click", function() {
                const tagId = this.dataset.tagId;
                
                // Toggle Visual (Bootstrap Badges)
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
                    input.id = `input-tag-${tagId}`;
                    hiddenContainer.appendChild(input);
                }
            });
            chip.dataset.bound = "1";
        });
    }

    /* ===============================================================
        ADD TAG (Criação via AJAX no Modal)
    =============================================================== */
    const addTagForm = document.getElementById("addTagForm");
    if (addTagForm) {
        addTagForm.addEventListener("submit", function (e) {
            e.preventDefault();
            const fd = new FormData(this);

            fetch("/ajax/add_tag/", {
                method: "POST",
                body: fd,
                headers: {
                    "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")?.value
                }
            })
            .then(r => r.json())
            .then(data => {
                if (!data.success) {
                    alert(data.error || "Failed to create tag.");
                    return;
                }

                // Cria o chip visual já selecionado
                const chip = document.createElement("span");
                chip.className = "badge rounded-pill border selectable-tag bg-primary text-white border-primary m-1 p-2";
                chip.dataset.tagId = data.id;
                chip.innerText = data.name;
                chip.style.cursor = "pointer";

                document.getElementById("tagChipContainer")?.appendChild(chip);

                // Adiciona o input oculto para o formulário principal
                const hidden = document.createElement("input");
                hidden.type = "hidden";
                hidden.name = "tags";
                hidden.value = data.id;
                hidden.id = `input-tag-${data.id}`;
                document.getElementById("tagHiddenInputs")?.appendChild(hidden);

                // Re-inicializa os eventos para o novo chip
                initTagSelector();

                bootstrap.Modal.getInstance(document.getElementById("addTagModal"))?.hide();
                this.reset();
            })
            .catch(err => alert("Error while creating tag."));
        });
    }

    /* ===============================================================
        KEYWORDS (Local Meta-data)
    =============================================================== */
    const addKeywordForm = document.getElementById("addKeywordForm");
    if (addKeywordForm) {
        addKeywordForm.addEventListener("submit", function (e) {
            e.preventDefault();
            // Suporte para IDs kw_key/kw_value do modal
            const keyInput = document.getElementById("kw_key") || this.key;
            const valInput = document.getElementById("kw_value") || this.value;

            const key = keyInput.value.trim();
            const val = valInput.value.trim();

            if (!key || !val) {
                alert("Both fields are required.");
                return;
            }

            const timestamp = Date.now();
            const chip = document.createElement("span");
            chip.className = "badge bg-light text-dark border p-2 m-1 d-inline-flex align-items-center";
            chip.style.cursor = "pointer";
            chip.innerHTML = `${key}: ${val} <i class="bi bi-x ms-2 text-danger"></i>`;

            const hidden = document.createElement("input");
            hidden.type = "hidden";
            hidden.name = "keyword_pairs";
            hidden.value = `${key}:::${val}`;
            hidden.id = `kw-input-${timestamp}`;

            chip.onclick = () => {
                chip.remove();
                hidden.remove();
            };

            document.getElementById("keywordChipContainer")?.appendChild(chip);
            document.getElementById("keywordHiddenInputs")?.appendChild(hidden);

            bootstrap.Modal.getInstance(document.getElementById("addKeywordModal"))?.hide();
            this.reset();
        });
    }

    /* ===============================================================
        FILE UPLOADS (Dynamic Rows)
    =============================================================== */
    let fileIndex = 0;
    const addFileBtn = document.getElementById("addFileBtn");
    const fileContainer = document.getElementById("fileContainer");

    if (addFileBtn && fileContainer) {
        addFileBtn.addEventListener("click", () => {
            const wrapper = document.createElement("div");
            wrapper.className = "card bg-light p-3 mb-2 border-dashed";

            wrapper.innerHTML = `
                <div class="row g-2">
                    <div class="col-md-5">
                        <input type="file" name="file" class="form-control form-control-sm" required>
                    </div>
                    <div class="col-md-3">
                        <input type="text" name="file_type_${fileIndex}" class="form-control form-control-sm" placeholder="Type (e.g. FASTA)">
                    </div>
                    <div class="col-md-3">
                        <input type="text" name="file_description_${fileIndex}" class="form-control form-control-sm" placeholder="Description">
                    </div>
                    <div class="col-md-1 text-end">
                        <button type="button" class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button>
                    </div>
                </div>
            `;

            wrapper.querySelector("button").addEventListener("click", () => wrapper.remove());
            fileContainer.appendChild(wrapper);
            fileIndex++;
        });
    }

    // Inicialização
    initTagSelector();
});