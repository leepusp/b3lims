/* =========================================================
   COLLECTION & SAMPLE SHARED JS
   Padronizado para lidar com Tags (ManyToMany) e Keywords (Key:::Value)
========================================================= */

function getCsrfToken() {
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value;
}

/**
 * Gerencia a seleção visual dos chips de Tags existentes
 */
function initTagSelector() {
    const tagChips = document.querySelectorAll(".selectable-tag");
    const hiddenContainer = document.getElementById("tagHiddenInputs");

    if (!hiddenContainer) return;

    tagChips.forEach(chip => {
        if (chip.dataset.bound === "1") return;

        chip.addEventListener("click", function() {
            const tagId = this.dataset.tagId;
            
            // Toggle Visual (Troca badge white/dark por primary/white)
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

/**
 * Lógica AJAX para criar uma Tag nova no Modal e já selecioná-la
 */
function initAddTagModal() {
    const form = document.getElementById("addTagForm");
    if (!form) return;

    form.addEventListener("submit", e => {
        e.preventDefault();
        const fd = new FormData(form);

        fetch("/ajax/add_tag/", {
            method: "POST",
            body: fd,
            headers: { "X-CSRFToken": getCsrfToken() }
        })
        .then(res => res.json())
        .then(data => {
            if (!data.success) {
                alert(data.error || "Error creating tag");
                return;
            }

            const chipContainer = document.getElementById("tagChipContainer");
            const hiddenContainer = document.getElementById("tagHiddenInputs");

            // Criar novo chip visual já selecionado (Padrão Bootstrap)
            const chip = document.createElement("span");
            chip.className = "badge rounded-pill border p-2 m-1 selectable-tag bg-primary text-white border-primary";
            chip.dataset.tagId = data.id;
            chip.style.cursor = "pointer";
            chip.innerText = data.name;

            chipContainer.appendChild(chip);

            // Adicionar input oculto
            const input = document.createElement("input");
            input.type = "hidden";
            input.name = "tags";
            input.value = data.id;
            input.id = `input-tag-${data.id}`;
            hiddenContainer.appendChild(input);

            // Re-inicializa para o novo chip poder ser desmarcado
            initTagSelector();

            // Fechar Modal
            const modalEl = document.getElementById("addTagModal");
            bootstrap.Modal.getInstance(modalEl)?.hide();
            form.reset();
        })
        .catch(() => alert("Unexpected error while creating tag"));
    });
}

/**
 * Lógica Local para Keywords (Chave ::: Valor)
 */
function initKeywordSelector() {
    const form = document.getElementById("addKeywordForm");
    if (!form) return;

    form.addEventListener("submit", e => {
        e.preventDefault();

        // O seu form usa IDs kw_key e kw_value ou os names. 
        // Ajustado para capturar pelos nomes/ids padrão do modal:
        const keyInput = document.getElementById("kw_key") || form.key;
        const valInput = document.getElementById("kw_value") || form.value;

        const key = keyInput.value.trim();
        const value = valInput.value.trim();

        if (!key || !value) {
            alert("Both key and value are required.");
            return;
        }

        const chipContainer = document.getElementById("keywordChipContainer");
        const hiddenContainer = document.getElementById("keywordHiddenInputs");

        const pairValue = `${key}:::${value}`;
        const timestamp = Date.now();

        // Chip Visual (Bootstrap Badge)
        const chip = document.createElement("span");
        chip.className = "badge bg-light text-dark border p-2 m-1 d-inline-flex align-items-center";
        chip.style.cursor = "pointer";
        chip.innerHTML = `${key}: ${value} <i class="bi bi-x ms-2 text-danger"></i>`;

        // Input Oculto
        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "keyword_pairs";
        hidden.value = pairValue;
        hidden.id = `kw-input-${timestamp}`;

        chip.onclick = () => {
            chip.remove();
            hidden.remove();
        };

        chipContainer.appendChild(chip);
        hiddenContainer.appendChild(hidden);

        // Fechar Modal
        const modalEl = document.getElementById("addKeywordModal");
        bootstrap.Modal.getInstance(modalEl)?.hide();
        
        keyInput.value = "";
        valInput.value = "";
    });
}

document.addEventListener("DOMContentLoaded", () => {
    initTagSelector();
    initAddTagModal();
    initKeywordSelector();
});