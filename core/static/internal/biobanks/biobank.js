/* =========================================================
   BIOBANK PAGE JS - "Submit Event" Version (Sample Style)
   Tags, Keywords, Smart Localization & Tooltips
========================================================= */

function getCsrfToken() {
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value;
}

/* =========================================================
   SMART LOCALIZATION (DRAGGABLE MAP)
========================================================= */
function initSmartLocation() {
    const mapEl = document.getElementById("map");
    const latInput = document.getElementById("id_latitude");
    const lngInput = document.getElementById("id_longitude");
    const labelInput = document.getElementById("id_location_label");

    if (!mapEl || typeof L === "undefined") return;

    // Inicia no Centro do Brasil
    const map = L.map("map").setView([-15.78, -47.92], 4);
window.biobankMap = map;

    window.B3Map.addResilientBasemap(
        map
    );

    let marker = null;

    function setLocationStatus(
        message,
        className = "text-muted"
    ) {
        const statusLabel =
            document.getElementById(
                "searchStatus"
            );

        if (!statusLabel) {
            return;
        }

        statusLabel.textContent = message;
        statusLabel.className =
            `form-text small text-end ${className}`;
    }

    function parseGeocodingResponse(response) {
        if (!response.ok) {
            throw new Error(
                `Geocoding HTTP ${response.status}`
            );
        }

        return response.json();
    }

    // Atualiza os inputs do formulário
    function updateInputs(lat, lng, address) {
        if (latInput) latInput.value = lat.toFixed(6);
        if (lngInput) lngInput.value = lng.toFixed(6);

        if (address) {
            // Update the text only when the user is not focused on the address input.
            if (document.activeElement !== labelInput && labelInput) {
                labelInput.value = address;
            }
        }
    }

    // Geocodificação Reversa (Pegar endereço pela coordenada)
    function reverseGeocode(lat, lng) {
        fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`)
            .then(parseGeocodingResponse)
            .then(data => {
                if (data.display_name) {
                    updateInputs(lat, lng, data.display_name);
                    const statusLabel = document.getElementById('searchStatus');
                    if (statusLabel) {
                        statusLabel.textContent = "Location found!";
                        statusLabel.className = "form-text small text-end text-success fw-bold";
                    }
                }
            })
            .catch(err => {
                console.warn(
                    "Reverse geocoding unavailable:",
                    err
                );

                setLocationStatus(
                    "Coordinates saved. Address lookup is temporarily unavailable.",
                    "text-warning"
                );
            });
    }

    // Ação: Clicar no mapa
    map.on("click", e => {
        const { lat, lng } = e.latlng;

        updateInputs(
            lat,
            lng,
            null
        );

        if (marker) {
            marker.setLatLng([lat, lng]);
        } else {
            marker = L.marker([lat, lng], { draggable: true }).addTo(map);
            marker.on('dragend', function(event) {
                const position = marker.getLatLng();

                updateInputs(
                    position.lat,
                    position.lng,
                    null
                );

                reverseGeocode(
                    position.lat,
                    position.lng
                );
            });
        }
        reverseGeocode(lat, lng);
    });

    /*
     * The public Nominatim service is intentionally not used
     * for client-side address autocomplete.
     *
     * The location label remains manually editable.
     * Reverse geocoding is only triggered by explicit map
     * interactions such as click or marker drag.
     */
}

/* =========================================================
   TAGS LOGIC (FORM SUBMIT INTERCEPTION)
========================================================= */
function initTagSystem() {
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

    const addTagForm = document.getElementById("addTagForm");

    if (addTagForm) {
        const newForm = addTagForm.cloneNode(true);
        addTagForm.parentNode.replaceChild(newForm, addTagForm);

        newForm.addEventListener("submit", function(e) {
            e.preventDefault();
            const feedback = document.getElementById("tagErrorFeedback");
            const btnSubmit = this.querySelector("[type=submit]");
            const spinner = btnSubmit.querySelector(".spinner-border");

            const fd = new FormData(this);
            const tagName = fd.get("name")?.toString().trim();

            if (!tagName) {
                if(feedback) { feedback.innerText = "Tag name is required."; feedback.style.display = "block"; }
                return;
            }

            if(spinner) spinner.classList.remove("d-none");
            btnSubmit.disabled = true;

            fetch(newForm.dataset.createUrl, {
                method: "POST",
                body: fd,
                headers: { "X-CSRFToken": getCsrfToken() }
            })
            .then(res => res.json())
            .then(data => {
                if (data.success || data.id) {
                    const chipContainer = document.getElementById("tagChipContainer");
                    const chip = document.createElement("span");
                    chip.className = "badge rounded-pill border selectable-tag bg-primary text-white border-primary m-1 p-2";
                    chip.dataset.tagId = data.id;
                    chip.style.cursor = "pointer";
                    chip.innerText = data.name;
                    chipContainer.appendChild(chip);

                    const input = document.createElement("input");
                    input.type = "hidden";
                    input.name = "tags";
                    input.value = data.id;
                    hiddenContainer.appendChild(input);

                    initTagSystem();
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
            e.preventDefault();
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

            chipContainer.appendChild(chip);
            hiddenContainer.appendChild(hidden);

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

    // Inicia os Tooltips do Bootstrap (Os Guias de UX)
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));

    // Previne envio acidental com Enter (exceto em Textareas e Botões)
    const biobankForm = document.getElementById("biobankForm");
    if (biobankForm) {
        biobankForm.addEventListener("keydown", function(event) {
            if (event.key === "Enter") {
                if (event.target.tagName !== "TEXTAREA" && event.target.tagName !== "BUTTON") {
                    event.preventDefault();
                }
            }
        });
    }
});
