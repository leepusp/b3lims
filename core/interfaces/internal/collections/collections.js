{% block extra_js %}
<script>
/* =========================================================
   COLLECTIONS JS - FINAL "SUBMIT INTERCEPT" VERSION
   Unified Tag & Keyword Management
========================================================= */

function getCsrfToken() {
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value;
}

/* =========================================================
   TAGS SYSTEM (Unified Logic)
========================================================= */
function initTagSystem() {
    // 1. Lógica para Chips Existentes (Seleção/Deseleção)
    const tagChips = document.querySelectorAll(".selectable-tag");
    const hiddenContainer = document.getElementById("tagHiddenInputs");

    tagChips.forEach(chip => {
        if (chip.dataset.bound) return;
        chip.dataset.bound = "true";

        chip.addEventListener("click", function() {
            const tagId = this.dataset.tagId;

            // Toggle Visual
            this.classList.toggle("bg-white");
            this.classList.toggle("text-dark");
            this.classList.toggle("bg-primary");
            this.classList.toggle("text-white");
            this.classList.toggle("border-primary");

            // Toggle Input Hidden
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

    // 2. Lógica para CRIAR TAG (Interceptando o SUBMIT do Form)
    const addTagForm = document.getElementById("addTagForm");

    if (addTagForm) {
        // Clone para limpar listeners antigos e evitar duplicação
        const newForm = addTagForm.cloneNode(true);
        addTagForm.parentNode.replaceChild(newForm, addTagForm);

        newForm.addEventListener("submit", function(e) {
            e.preventDefault(); // <--- O SEGREDO: Impede o Enter de recarregar a página

            const fd = new FormData(this);
            const btn = this.querySelector("[type=submit]");
            const spinner = btn.querySelector(".spinner-border");
            const feedback = document.getElementById("tagErrorFeedback");

            // Validação simples
            const tagName = fd.get("name")?.toString().trim();
            if (!tagName) {
                if(feedback) { feedback.innerText = "Tag name is required."; feedback.style.display = "block"; }
                return;
            }

            // UI Loading
            if(spinner) spinner.classList.remove("d-none");
            btn.disabled = true;

            fetch("/ajax/add_tag/", {
                method: "POST",
                body: fd,
                headers: { "X-CSRFToken": getCsrfToken() }
            })
            .then(res => res.json())
            .then(data => {
                if (data.success || data.id) {
                    // Adiciona Chip Visual
                    const chipContainer = document.getElementById("tagChipContainer");
                    const chip = document.createElement("span");
                    chip.className = "badge rounded-pill border selectable-tag bg-primary text-white border-primary m-1 p-2";
                    chip.dataset.tagId = data.id;
                    chip.style.cursor = "pointer";
                    chip.innerText = data.name;
                    chipContainer.appendChild(chip);

                    // Adiciona Input Hidden
                    const hiddenContainer = document.getElementById("tagHiddenInputs");
                    const input = document.createElement("input");
                    input.type = "hidden";
                    input.name = "tags";
                    input.value = data.id;
                    hiddenContainer.appendChild(input);

                    // Reinicializa seletores para o novo chip funcionar
                    initTagSystem();

                    // Limpa e Fecha Modal
                    this.reset();
                    const modalEl = document.getElementById("addTagModal");
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                    else new bootstrap.Modal(modalEl).hide();

                    if(feedback) feedback.style.display = "none";
                } else {
                    if(feedback) {
                        feedback.innerText = data.error || "Error creating tag.";
                        feedback.style.display = "block";
                    }
                }
            })
            .catch(() => {
                if(feedback) {
                    feedback.innerText = "Server connection error.";
                    feedback.style.display = "block";
                }
            })
            .finally(() => {
                if(spinner) spinner.classList.add("d-none");
                btn.disabled = false;
            });
        });
    }
}

/* =========================================================
   KEYWORDS SYSTEM (Local Chips - Submit Intercept)
========================================================= */
function initKeywordSystem() {
    const addKeywordForm = document.getElementById("addKeywordForm");

    if (addKeywordForm) {
        const newForm = addKeywordForm.cloneNode(true);
        addKeywordForm.parentNode.replaceChild(newForm, addKeywordForm);

        newForm.addEventListener("submit", function(e) {
            e.preventDefault(); // <--- Impede o refresh

            const keyInput = document.getElementById("keywordKey");
            const valInput = document.getElementById("keywordValue");
            const feedback = document.getElementById("keywordErrorFeedback");

            const key = keyInput?.value.trim();
            const val = valInput?.value.trim();

            if (!key || !val) {
                if(feedback) { feedback.innerText = "Both Key and Value are required."; feedback.style.display = "block"; }
                return;
            }

            // Cria Chip Visual
            const chipContainer = document.getElementById("keywordChipContainer");
            const hiddenContainer = document.getElementById("keywordHiddenInputs");
            const pairValue = `${key}:::${val}`;

            const chip = document.createElement("span");
            chip.className = "badge bg-light text-dark border p-2 m-1 d-inline-flex align-items-center";
            chip.innerHTML = `<strong>${key}</strong>: ${val} <i class="bi bi-x ms-2 text-danger" style="cursor:pointer;"></i>`;

            // Cria Input Hidden
            const hidden = document.createElement("input");
            hidden.type = "hidden";
            hidden.name = "keyword_pairs";
            hidden.value = pairValue;

            // Lógica de Remover
            chip.querySelector(".bi-x").onclick = function() {
                chip.remove();
                hidden.remove();
            };

            chipContainer.appendChild(chip);
            hiddenContainer.appendChild(hidden);

            // Limpa e Fecha
            this.reset();
            if(feedback) feedback.style.display = "none";

            const modalEl = document.getElementById("addKeywordModal");
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
            else new bootstrap.Modal(modalEl).hide();
        });
    }
}

/* =========================================================
   INIT
========================================================= */
document.addEventListener("DOMContentLoaded", () => {
    initTagSystem();
    initKeywordSystem();
});
</script>
{% endblock %}