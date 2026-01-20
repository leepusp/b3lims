/* =========================================================
   BIOBANK PAGE JS - "Submit Event" Version (Sample Style)
   Tags, Keywords, Smart Localization
========================================================= */

function getCsrfToken() {
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value;
}

/* =========================================================
   SMART LOCALIZATION (DRAGGABLE MAP)
   Mantida igual pois já estava correta
========================================================= */
function initSmartLocation() {
    const mapEl = document.getElementById("map");
    const institutionInput = document.getElementById("id_institution");
    const latInput = document.getElementById("id_latitude");
    const lngInput = document.getElementById("id_longitude");
    const labelInput = document.getElementById("id_location_label");

    if (!mapEl || !institutionInput || typeof L === "undefined") return;

    const map = L.map("map").setView([-15.78, -47.92], 4);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors"
    }).addTo(map);

    let marker = null;
    let debounce = null;

    function updateInputs(lat, lng, address) {
        if (latInput) latInput.value = lat.toFixed(6);
        if (lngInput) lngInput.value = lng.toFixed(6);

        if (address) {
            if (labelInput) labelInput.value = address;
            if (institutionInput && !institutionInput.value) institutionInput.value = address.split(",")[0];
        }
    }

    function createOrMoveMarker(lat, lng, address = null) {
        if (marker) {
            marker.setLatLng([lat, lng]);
        } else {
            marker = L.marker([lat, lng], { draggable: true }).addTo(map);
            marker.on('dragend', function(event) {
                const position = marker.getLatLng();
                reverseGeocode(position.lat, position.lng);
            });
        }
        if (address) updateInputs(lat, lng, address);
    }

    function reverseGeocode(lat, lng) {
        if (labelInput) labelInput.value = "Searching address...";

        fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`)
            .then(r => r.json())
            .then(data => {
                if (data.display_name) {
                    updateInputs(lat, lng, data.display_name);
                } else {
                    if (labelInput) labelInput.value = "Address not found";
                }
            })
            .catch(err => {
                console.error("Geocode error:", err);
                if (labelInput) labelInput.value = "Error fetching address";
            });
    }

    institutionInput.addEventListener("input", () => {
        clearTimeout(debounce);
        debounce = setTimeout(() => {
            const query = institutionInput.value.trim();
            if (query.length < 3) return;

            fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}`)
                .then(r => r.json())
                .then(data => {
                    if (!data.length) return;
                    const place = data[0];
                    const lat = parseFloat(place.lat);
                    const lon = parseFloat(place.lon);
                    map.setView([lat, lon], 16);
                    createOrMoveMarker(lat, lon, place.display_name);
                });
        }, 500);
    });

    map.on("click", e => {
        const { lat, lng } = e.latlng;
        createOrMoveMarker(lat, lng);
        reverseGeocode(lat, lng);
    });
}

/* =========================================================
   TAGS LOGIC (FORM SUBMIT INTERCEPTION)
========================================================= */
function initTagSystem() {
    // 1. Lógica para selecionar Tags já existentes na tela
    const tagChips = document.querySelectorAll(".selectable-tag");
    const hiddenContainer = document.getElementById("tagHiddenInputs");

    tagChips.forEach(chip => {
        if (chip.dataset.bound) return;
        chip.dataset.bound = "true";

        chip.addEventListener("click", function() {
            const tagId = this.dataset.tagId;

            // Toggle visual
            this.classList.toggle("bg-white");
            this.classList.toggle("text-dark");
            this.classList.toggle("bg-primary");
            this.classList.toggle("text-white");

            // Gerencia input hidden
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

    // 2. Lógica para SALVAR NOVA TAG via AJAX (Escutando o Form)
    const addTagForm = document.getElementById("addTagForm");

    if (addTagForm) {
        // Remove listener antigo substituindo o elemento por um clone
        const newForm = addTagForm.cloneNode(true);
        addTagForm.parentNode.replaceChild(newForm, addTagForm);

        newForm.addEventListener("submit", function(e) {
            e.preventDefault(); // <--- O SEGREDO: Impede o refresh da página

            const feedback = document.getElementById("tagErrorFeedback");
            const btnSubmit = this.querySelector("[type=submit]");
            const spinner = btnSubmit.querySelector(".spinner-border");

            // Coleta dados via FormData (igual ao sample.js)
            const fd = new FormData(this);
            const tagName = fd.get("name")?.toString().trim();

            if (!tagName) {
                if(feedback) { feedback.innerText = "Tag name is required."; feedback.style.display = "block"; }
                return;
            }

            // UI Loading
            if(spinner) spinner.classList.remove("d-none");
            btnSubmit.disabled = true;

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
                    const input = document.createElement("input");
                    input.type = "hidden";
                    input.name = "tags";
                    input.value = data.id;
                    hiddenContainer.appendChild(input);

                    // Reinicializa seletores
                    initTagSystem();

                    // Limpa form e fecha modal
                    this.reset();
                    const modalEl = document.getElementById("addTagModal");
                    const modalInstance = bootstrap.Modal.getInstance(modalEl);
                    if (modalInstance) modalInstance.hide();
                    else new bootstrap.Modal(modalEl).hide();

                    if(feedback) feedback.style.display = "none";

                } else {
                    if(feedback) { feedback.innerText = data.error || "Error creating tag."; feedback.style.display = "block"; }
                }
            })
            .catch(() => {
                if(feedback) { feedback.innerText = "Server connection error."; feedback.style.display = "block"; }
            })
            .finally(() => {
                if(spinner) spinner.classList.add("d-none");
                btnSubmit.disabled = false;
            });
        });
    }
}

/* =========================================================
   KEYWORDS LOGIC (FORM SUBMIT INTERCEPTION)
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

            // Cria Chip
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

            // Remove ao clicar no X
            chip.querySelector(".bi-x").onclick = function() {
                chip.remove();
                hidden.remove();
            };

            chipContainer.appendChild(chip);
            hiddenContainer.appendChild(hidden);

            // Limpa form e fecha modal
            this.reset();
            if(feedback) feedback.style.display = "none";

            const modalEl = document.getElementById("addKeywordModal");
            const modalInstance = bootstrap.Modal.getInstance(modalEl);
            if (modalInstance) modalInstance.hide();
            else new bootstrap.Modal(modalEl).hide();
        });
    }
}

/* =========================================================
   INIT
========================================================= */
document.addEventListener("DOMContentLoaded", () => {
    initSmartLocation();
    initTagSystem();
    initKeywordSystem();
});