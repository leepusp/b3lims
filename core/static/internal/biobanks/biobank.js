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

    const searchButton = document.getElementById(
        "locationSearchButton"
    );

    const searchResults = document.getElementById(
        "locationSearchResults"
    );

    if (
        !mapEl
        || !labelInput
        || typeof L === "undefined"
        || !window.B3Map
    ) {
        return;
    }

    const searchUrl =
        labelInput.dataset.geocodeSearchUrl;

    const reverseUrl =
        labelInput.dataset.geocodeReverseUrl;

    const map = L.map("map").setView(
        [-15.78, -47.92],
        4
    );

    window.biobankMap = map;

    window.B3Map.addResilientBasemap(
        map
    );

    let marker = null;
    let searchController = null;
    let reverseController = null;

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

        statusLabel.textContent =
            message;

        statusLabel.className =
            `form-text small text-end ${className}`;
    }

    function updateInputs(
        lat,
        lng,
        address,
        forceAddress = false
    ) {
        if (latInput) {
            latInput.value =
                Number(lat).toFixed(6);
        }

        if (lngInput) {
            lngInput.value =
                Number(lng).toFixed(6);
        }

        if (
            address
            && labelInput
            && (
                forceAddress
                || document.activeElement
                    !== labelInput
            )
        ) {
            labelInput.value =
                String(address).slice(
                    0,
                    255
                );
        }
    }

    function clearCoordinates() {
        if (latInput) {
            latInput.value = "";
        }

        if (lngInput) {
            lngInput.value = "";
        }
    }

    function clearSearchResults() {
        if (!searchResults) {
            return;
        }

        searchResults.replaceChildren();

        searchResults.classList.add(
            "d-none"
        );
    }

    async function fetchJson(
        url,
        controller
    ) {
        const response = await fetch(
            url,
            {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "Accept":
                        "application/json",
                },
                signal:
                    controller
                        ? controller.signal
                        : undefined,
            }
        );

        let payload = {};

        try {
            payload =
                await response.json();

        } catch (error) {
            throw new Error(
                `Invalid geocoding response `
                + `(${response.status})`
            );
        }

        if (!response.ok) {
            throw new Error(
                payload.error
                || (
                    "Geocoding HTTP "
                    + response.status
                )
            );
        }

        return payload;
    }

    function buildEndpoint(
        base,
        params
    ) {
        const url = new URL(
            base,
            window.location.origin
        );

        Object.entries(
            params
        ).forEach(
            ([key, value]) => {
                url.searchParams.set(
                    key,
                    value
                );
            }
        );

        return url.toString();
    }

    function placeMarker(
        lat,
        lng
    ) {
        if (marker) {
            marker.setLatLng(
                [lat, lng]
            );

            return marker;
        }

        marker = L.marker(
            [lat, lng],
            {
                draggable: true,
            }
        ).addTo(map);

        marker.on(
            "dragend",
            function () {
                const position =
                    marker.getLatLng();

                updateInputs(
                    position.lat,
                    position.lng,
                    null
                );

                reverseGeocode(
                    position.lat,
                    position.lng
                );
            }
        );

        return marker;
    }

    function removeMarker() {
        if (!marker) {
            return;
        }

        map.removeLayer(
            marker
        );

        marker = null;
    }

    async function reverseGeocode(
        lat,
        lng
    ) {
        if (!reverseUrl) {
            setLocationStatus(
                "Coordinates saved. "
                + "Address lookup is unavailable.",
                "text-warning"
            );

            return;
        }

        if (reverseController) {
            reverseController.abort();
        }

        reverseController =
            new AbortController();

        setLocationStatus(
            "Looking up address..."
        );

        try {
            const payload =
                await fetchJson(
                    buildEndpoint(
                        reverseUrl,
                        {
                            lat:
                                Number(lat)
                                    .toFixed(7),
                            lon:
                                Number(lng)
                                    .toFixed(7),
                        }
                    ),
                    reverseController
                );

            if (
                !payload.result
                || !payload.result.label
            ) {
                setLocationStatus(
                    "Coordinates saved. "
                    + "No address was found.",
                    "text-warning"
                );

                return;
            }

            updateInputs(
                lat,
                lng,
                payload.result.label,
                true
            );

            setLocationStatus(
                "Location found!",
                "text-success fw-bold"
            );

        } catch (error) {
            if (
                error.name
                === "AbortError"
            ) {
                return;
            }

            console.warn(
                "Reverse geocoding unavailable:",
                error
            );

            setLocationStatus(
                "Coordinates saved. "
                + "Address lookup is "
                + "temporarily unavailable.",
                "text-warning"
            );
        }
    }

    function locationSubtitle(
        result
    ) {
        const address =
            result.address || {};

        const locality =
            address.city
            || address.town
            || address.village
            || address.municipality
            || "";

        const values = [
            locality,
            address.state || "",
            address.country || "",
        ].filter(
            Boolean
        );

        return [
            ...new Set(values)
        ].join(" · ");
    }

    function selectSearchResult(
        result
    ) {
        const lat =
            Number.parseFloat(
                result.lat
            );

        const lng =
            Number.parseFloat(
                result.lon
            );

        if (
            !Number.isFinite(lat)
            || !Number.isFinite(lng)
        ) {
            setLocationStatus(
                "The selected result "
                + "has invalid coordinates.",
                "text-danger"
            );

            return;
        }

        updateInputs(
            lat,
            lng,
            result.label
                || result.display_name,
            true
        );

        placeMarker(
            lat,
            lng
        );

        map.flyTo(
            [lat, lng],
            16
        );

        clearSearchResults();

        setLocationStatus(
            "Location found!",
            "text-success fw-bold"
        );
    }

    function renderSearchResults(
        results
    ) {
        clearSearchResults();

        if (
            !searchResults
            || !results.length
        ) {
            return;
        }

        results.forEach(
            result => {
                const button =
                    document.createElement(
                        "button"
                    );

                button.type = "button";

                button.className =
                    "list-group-item "
                    + "list-group-item-action";

                const title =
                    document.createElement(
                        "div"
                    );

                title.className =
                    "fw-semibold small";

                title.textContent =
                    result.display_name
                    || result.label
                    || "Location";

                button.appendChild(
                    title
                );

                const subtitle =
                    locationSubtitle(
                        result
                    );

                if (subtitle) {
                    const meta =
                        document.createElement(
                            "div"
                        );

                    meta.className =
                        "text-muted small mt-1";

                    meta.textContent =
                        subtitle;

                    button.appendChild(
                        meta
                    );
                }

                button.addEventListener(
                    "click",
                    () => {
                        selectSearchResult(
                            result
                        );
                    }
                );

                searchResults.appendChild(
                    button
                );
            }
        );

        searchResults.classList.remove(
            "d-none"
        );
    }

    async function searchAddress() {
        const query =
            labelInput.value.trim();

        clearSearchResults();

        if (query.length < 3) {
            setLocationStatus(
                "Enter at least "
                + "3 characters.",
                "text-warning"
            );

            return;
        }

        if (!searchUrl) {
            setLocationStatus(
                "Address search is "
                + "unavailable.",
                "text-warning"
            );

            return;
        }

        if (searchController) {
            searchController.abort();
        }

        searchController =
            new AbortController();

        if (searchButton) {
            searchButton.disabled =
                true;
        }

        setLocationStatus(
            "Searching..."
        );

        try {
            const payload =
                await fetchJson(
                    buildEndpoint(
                        searchUrl,
                        {
                            q: query,
                        }
                    ),
                    searchController
                );

            const results =
                Array.isArray(
                    payload.results
                )
                    ? payload.results
                    : [];

            if (!results.length) {
                setLocationStatus(
                    "Location not found.",
                    "text-danger"
                );

                return;
            }

            if (
                results.length === 1
            ) {
                selectSearchResult(
                    results[0]
                );

                return;
            }

            renderSearchResults(
                results
            );

            setLocationStatus(
                `${results.length} locations found. `
                + "Select one.",
                "text-primary fw-bold"
            );

        } catch (error) {
            if (
                error.name
                === "AbortError"
            ) {
                return;
            }

            console.warn(
                "Address search unavailable:",
                error
            );

            setLocationStatus(
                error.message
                || (
                    "Address search is "
                    + "temporarily unavailable."
                ),
                "text-warning"
            );

        } finally {
            if (searchButton) {
                searchButton.disabled =
                    false;
            }
        }
    }

    map.on(
        "click",
        event => {
            const {
                lat,
                lng,
            } = event.latlng;

            clearSearchResults();

            updateInputs(
                lat,
                lng,
                null
            );

            placeMarker(
                lat,
                lng
            );

            reverseGeocode(
                lat,
                lng
            );
        }
    );

    labelInput.addEventListener(
        "input",
        function () {
            clearSearchResults();

            /*
             * Once the user edits the textual
             * location manually, previously
             * selected coordinates must not
             * silently remain associated with
             * a different address.
             */
            clearCoordinates();
            removeMarker();

            setLocationStatus(
                "Press Enter or click "
                + "search to locate this "
                + "address."
            );
        }
    );

    labelInput.addEventListener(
        "keydown",
        function (event) {
            if (
                event.key !== "Enter"
            ) {
                return;
            }

            event.preventDefault();

            searchAddress();
        }
    );

    if (searchButton) {
        searchButton.addEventListener(
            "click",
            searchAddress
        );
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
