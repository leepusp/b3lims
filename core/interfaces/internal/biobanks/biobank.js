/* =========================================================

   BIOBANK PAGE JS - "Submit Event" Version (Sample Style)

   Tags, Keywords, Smart Localization

========================================================= */



function getCsrfToken() {

    return document.querySelector("[name=csrfmiddlewaretoken]")?.value;

}



/* =========================================================

   SMART LOCALIZATION (DRAGGABLE MAP)

========================================================= */

function initSmartLocation() {

    const mapEl = document.getElementById("map");

    const institutionInput = document.getElementById("id_institution");

    const latInput = document.getElementById("id_latitude");

    const lngInput = document.getElementById("id_longitude");

    const labelInput = document.getElementById("id_location_label");



    if (!mapEl || typeof L === "undefined") return;



    // Inicia no Centro do Brasil

    const map = L.map("map").setView([-15.78, -47.92], 4);



    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {

        attribution: "© OpenStreetMap contributors"

    }).addTo(map);



    let marker = null;

    let debounceTimer = null; // Timer para a caixa de pesquisa (Debounce)



    // Atualiza os inputs do formulário

    function updateInputs(lat, lng, address) {

        if (latInput) latInput.value = lat.toFixed(6);

        if (lngInput) lngInput.value = lng.toFixed(6);



        if (address) {

            // Só atualiza o texto se o usuário NÃO estiver com o cursor na caixa de endereço

            if (document.activeElement !== labelInput && labelInput) {

                labelInput.value = address;

            }

            if (institutionInput && !institutionInput.value) {

                institutionInput.value = address.split(",")[0];

            }

        }

    }



    // Geocodificação Reversa (Pegar endereço pela coordenada)

    function reverseGeocode(lat, lng) {

        fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`)

            .then(r => r.json())

            .then(data => {

                if (data.display_name) {

                    updateInputs(lat, lng, data.display_name);

                }

            })

            .catch(err => console.error("Geocode error:", err));

    }



    // Ação: Clicar no mapa

    map.on("click", e => {

        const { lat, lng } = e.latlng;

        if (marker) {

            marker.setLatLng([lat, lng]);

        } else {

            marker = L.marker([lat, lng], { draggable: true }).addTo(map);

            // Atualizar ao arrastar o pino

            marker.on('dragend', function(event) {

                const position = marker.getLatLng();

                reverseGeocode(position.lat, position.lng);

            });

        }

        reverseGeocode(lat, lng);

    });



    // --- Escutar a digitação no campo ADDRESS ---

    if (labelInput) {

        labelInput.addEventListener("input", function() {

            clearTimeout(debounceTimer);

            const query = this.value.trim();



            if (query.length > 4) {

                debounceTimer = setTimeout(() => {

                    fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}`)

                        .then(r => r.json())

                        .then(data => {

                            if (data && data.length > 0) {

                                const lat = parseFloat(data[0].lat);

                                const lon = parseFloat(data[0].lon);



                                // Move o mapa suavemente

                                map.flyTo([lat, lon], 16);



                                if (marker) {

                                    marker.setLatLng([lat, lon]);

                                } else {

                                    marker = L.marker([lat, lon], { draggable: true }).addTo(map);

                                    marker.on('dragend', function(event) {

                                        const position = marker.getLatLng();

                                        reverseGeocode(position.lat, position.lng);

                                    });

                                }



                                // Salva as coordenadas no formulário oculto

                                updateInputs(lat, lon, null);

                            }

                        })

                        .catch(err => console.error("Erro ao buscar endereço:", err));

                }, 1000); // Aguarda 1 segundo após o término da digitação

            }

        });

    }

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



            fetch("/ajax/add_tag/", {

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

});
