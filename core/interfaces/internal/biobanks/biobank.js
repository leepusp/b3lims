/* =========================================================
    BIOBANK PAGE JS - Enhanced Version
    Tags, Keywords, Smart Localization & Draggable Map
========================================================= */

function getCsrfToken() {
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value;
}

/* =========================================================
    TAG SELECTION (CHIPS)
========================================================= */
function toggleTagChip(chip) {
    const tagId = chip.dataset.tagId;
    const hiddenContainer = document.getElementById("tagHiddenInputs");
    if (!tagId || !hiddenContainer) return;

    // Toggle visual state usando classes do Bootstrap que usamos no HTML
    chip.classList.toggle("bg-primary");
    chip.classList.toggle("text-white");
    chip.classList.toggle("text-dark");

    const existing = hiddenContainer.querySelector(`input[value="${tagId}"]`);

    if (existing) {
        existing.remove();
    } else {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "tags";
        input.value = tagId;
        hiddenContainer.appendChild(input);
    }
}

function initTagSelector() {
    document.querySelectorAll(".selectable-tag").forEach(chip => {
        if (chip.dataset.bound === "1") return;
        chip.addEventListener("click", () => toggleTagChip(chip));
        chip.dataset.bound = "1";
    });
}

/* =========================================================
    KEYWORDS (LOCAL)
========================================================= */
function initKeywordSelector() {
    const form = document.getElementById("addKeywordForm");
    if (!form) return;

    form.addEventListener("submit", e => {
        e.preventDefault();
        const key = form.key.value.trim();
        const value = form.value.value.trim();

        if (!key || !value) return;

        const chipContainer = document.getElementById("keywordChipContainer");
        const hiddenContainer = document.getElementById("keywordHiddenInputs");

        const chip = document.createElement("span");
        chip.className = "badge bg-dark text-white m-1 p-2";
        chip.innerHTML = `${key} <i class="bi bi-arrow-right mx-1"></i> ${value}`;
        chipContainer.appendChild(chip);

        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "keyword_pairs";
        input.value = `${key}:::${value}`;
        hiddenContainer.appendChild(input);

        bootstrap.Modal.getInstance(document.getElementById("addKeywordModal"))?.hide();
        form.reset();
    });
}

/* =========================================================
    SMART LOCALIZATION (DRAGGABLE MAP)
========================================================= */
function initSmartLocation() {
    const mapEl = document.getElementById("map");
    const searchInput = document.querySelector("input[name='institution']");
    const latInput = document.querySelector("input[name='latitude']");
    const lngInput = document.querySelector("input[name='longitude']");
    const labelInput = document.querySelector("input[name='location_label']");

    if (!mapEl || !searchInput || typeof L === "undefined") return;

    // Inicializa em uma visão global ou coordenadas padrão do Brasil
    const map = L.map("map").setView([-15.78, -47.92], 4);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors"
    }).addTo(map);

    let marker = null;
    let debounce = null;

    function updateInputs(lat, lng, label) {
        latInput.value = lat.toFixed(6);
        lngInput.value = lng.toFixed(6);
        if (label) {
            labelInput.value = label;
        }
    }

    function createOrMoveMarker(lat, lng) {
        if (marker) {
            marker.setLatLng([lat, lng]);
        } else {
            // Torna o marcador arrastável (Draggable)
            marker = L.marker([lat, lng], { draggable: true }).addTo(map);
            
            // Evento disparado quando o usuário termina de arrastar o pino
            marker.on('dragend', function(event) {
                const position = marker.getLatLng();
                reverseGeocode(position.lat, position.lng);
            });
        }
    }

    function reverseGeocode(lat, lng) {
        updateInputs(lat, lng);
        fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`)
            .then(r => r.json())
            .then(data => {
                if (data.display_name) {
                    labelInput.value = data.display_name;
                    // Opcional: não sobrescrever o que o usuário digitou na pesquisa se ele só arrastou o pino
                }
            });
    }

    // Busca por texto (Instituição/Endereço)
    searchInput.addEventListener("input", () => {
        clearTimeout(debounce);
        debounce = setTimeout(() => {
            const query = searchInput.value.trim();
            if (query.length < 3) return;

            fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}`)
                .then(r => r.json())
                .then(data => {
                    if (!data.length) return;
                    const place = data[0];
                    const lat = parseFloat(place.lat);
                    const lon = parseFloat(place.lon);

                    map.setView([lat, lon], 16);
                    createOrMoveMarker(lat, lon);
                    updateInputs(lat, lon, place.display_name);
                });
        }, 800);
    });

    // Clique no mapa para definir local
    map.on("click", e => {
        createOrMoveMarker(e.latlng.lat, e.latlng.lng);
        reverseGeocode(e.latlng.lat, e.latlng.lng);
    });
}

/* =========================================================
    DELETE BIOBANK CONFIRMATION
========================================================= */
function initDeleteBiobankConfirm() {
    const modalEl = document.getElementById("confirmDeleteBiobankModal");
    if (!modalEl) return;

    const nameEl = document.getElementById("deleteBiobankName");
    const idInput = document.getElementById("deleteBiobankId");

    document.querySelectorAll(".js-delete-biobank").forEach(btn => {
        btn.addEventListener("click", () => {
            nameEl.textContent = btn.dataset.biobankName;
            idInput.value = btn.dataset.biobankId;
            new bootstrap.Modal(modalEl).show();
        });
    });
}

/* =========================================================
    INIT
========================================================= */
document.addEventListener("DOMContentLoaded", () => {
    initTagSelector();
    initKeywordSelector();
    initSmartLocation();
    initDeleteBiobankConfirm();
});