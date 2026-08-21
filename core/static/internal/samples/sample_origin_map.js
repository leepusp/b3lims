(() => {
    "use strict";

    const DEFAULT_CENTER = [0, 0];
    const DEFAULT_ZOOM = 2;

    function numberOrNull(value) {
        if (
            value === null
            || value === undefined
            || String(value).trim() === ""
        ) {
            return null;
        }

        const parsed = Number(value);

        return Number.isFinite(parsed)
            ? parsed
            : null;
    }

    function coordinatePairIsValid(lat, lng) {
        return (
            lat !== null
            && lng !== null
            && lat >= -90
            && lat <= 90
            && lng >= -180
            && lng <= 180
        );
    }

    function addBaseLayer(
        map,
        options = {}
    ) {
        const noWrap =
            options.noWrap === true;

        return L.tileLayer(
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            {
                maxZoom: 19,
                noWrap,
                bounds: noWrap
                    ? [
                        [-85.05112878, -180],
                        [85.05112878, 180],
                    ]
                    : undefined,
                attribution: "&copy; OpenStreetMap contributors",
            }
        ).addTo(map);
    }

    function updateCoordinateStatus(
        statusElement,
        lat,
        lng
    ) {
        if (!statusElement) {
            return;
        }

        if (
            coordinatePairIsValid(
                lat,
                lng
            )
        ) {
            statusElement.textContent =
                `${lat.toFixed(6)}, ${lng.toFixed(6)}`;

            statusElement.classList.add(
                "has-coordinates"
            );

            return;
        }

        statusElement.textContent =
            "No collection coordinates selected.";

        statusElement.classList.remove(
            "has-coordinates"
        );
    }

    function initializeEditableMap(container) {
        if (
            !container
            || container.dataset.mapInitialized === "true"
        ) {
            return;
        }

        const editor = container.closest(
            "[data-sample-origin-editor]"
        );

        if (!editor) {
            return;
        }

        const latInput = editor.querySelector(
            '[name="origin-latitude"]'
        );

        const lngInput = editor.querySelector(
            '[name="origin-longitude"]'
        );

        if (
            !latInput
            || !lngInput
        ) {
            return;
        }

        const statusElement = editor.querySelector(
            "[data-origin-coordinate-status]"
        );

        const clearButton = editor.querySelector(
            "[data-origin-clear-coordinates]"
        );

        let lat = numberOrNull(
            latInput.value
        );

        let lng = numberOrNull(
            lngInput.value
        );

        const hasInitialCoordinates =
            coordinatePairIsValid(
                lat,
                lng
            );

        const map = L.map(
            container,
            {
                worldCopyJump: true,
            }
        );

        addBaseLayer(map);

        map.setView(
            hasInitialCoordinates
                ? [lat, lng]
                : DEFAULT_CENTER,
            hasInitialCoordinates
                ? 8
                : DEFAULT_ZOOM
        );

        let marker = null;

        function ensureMarker(
            newLat,
            newLng,
            options = {}
        ) {
            if (
                !coordinatePairIsValid(
                    newLat,
                    newLng
                )
            ) {
                if (marker) {
                    map.removeLayer(
                        marker
                    );
                    marker = null;
                }

                updateCoordinateStatus(
                    statusElement,
                    null,
                    null
                );

                return;
            }

            if (!marker) {
                marker = L.marker(
                    [
                        newLat,
                        newLng,
                    ],
                    {
                        draggable: true,
                    }
                ).addTo(map);

                marker.on(
                    "dragend",
                    () => {
                        const position =
                            marker.getLatLng();

                        latInput.value =
                            position.lat.toFixed(6);

                        lngInput.value =
                            position.lng.toFixed(6);

                        updateCoordinateStatus(
                            statusElement,
                            position.lat,
                            position.lng
                        );
                    }
                );
            } else {
                marker.setLatLng(
                    [
                        newLat,
                        newLng,
                    ]
                );
            }

            if (options.center) {
                map.setView(
                    [
                        newLat,
                        newLng,
                    ],
                    options.zoom || map.getZoom()
                );
            }

            updateCoordinateStatus(
                statusElement,
                newLat,
                newLng
            );
        }

        function syncFromInputs(
            center = false
        ) {
            lat = numberOrNull(
                latInput.value
            );

            lng = numberOrNull(
                lngInput.value
            );

            ensureMarker(
                lat,
                lng,
                {
                    center,
                    zoom: 8,
                }
            );
        }

        map.on(
            "click",
            (event) => {
                latInput.value =
                    event.latlng.lat.toFixed(6);

                lngInput.value =
                    event.latlng.lng.toFixed(6);

                syncFromInputs(
                    false
                );
            }
        );

        latInput.addEventListener(
            "change",
            () => syncFromInputs(true)
        );

        lngInput.addEventListener(
            "change",
            () => syncFromInputs(true)
        );

        if (clearButton) {
            clearButton.addEventListener(
                "click",
                () => {
                    latInput.value = "";
                    lngInput.value = "";

                    syncFromInputs(
                        false
                    );

                    map.setView(
                        DEFAULT_CENTER,
                        DEFAULT_ZOOM
                    );
                }
            );
        }

        if (hasInitialCoordinates) {
            ensureMarker(
                lat,
                lng,
                {
                    center: false,
                }
            );
        } else {
            updateCoordinateStatus(
                statusElement,
                null,
                null
            );
        }

        container.dataset.mapInitialized =
            "true";

        setTimeout(
            () => {
                map.invalidateSize();
            },
            0
        );
    }

    function initializeReadonlyMap(container) {
        if (
            !container
            || container.dataset.mapInitialized === "true"
        ) {
            return;
        }

        const lat = numberOrNull(
            container.dataset.latitude
        );

        const lng = numberOrNull(
            container.dataset.longitude
        );

        if (
            !coordinatePairIsValid(
                lat,
                lng
            )
        ) {
            return;
        }

        const map = L.map(
            container,
            {
                worldCopyJump: true,
                scrollWheelZoom: false,
            }
        ).setView(
            [
                lat,
                lng,
            ],
            8
        );

        addBaseLayer(map);

        L.marker(
            [
                lat,
                lng,
            ]
        ).addTo(map);

        container.dataset.mapInitialized =
            "true";

        setTimeout(
            () => {
                map.invalidateSize();
            },
            0
        );
    }

    function popupHasValue(value) {
        return !(
            value === null
            || value === undefined
            || String(value).trim() === ""
        );
    }

    function popupText(
        parent,
        className,
        value
    ) {
        const element =
            document.createElement("div");

        element.className =
            className;

        element.textContent =
            String(value);

        parent.appendChild(
            element
        );

        return element;
    }

    function addPopupField(
        section,
        label,
        value
    ) {
        if (!popupHasValue(value)) {
            return;
        }

        const row =
            document.createElement("div");

        row.className =
            "sample-origin-popup-field";

        popupText(
            row,
            "sample-origin-popup-field-label",
            label
        );

        popupText(
            row,
            "sample-origin-popup-field-value",
            value
        );

        section.appendChild(
            row
        );
    }

    function addPopupSection(
        body,
        title,
        fields
    ) {
        const populated =
            fields.filter(
                ([, value]) => (
                    popupHasValue(value)
                )
            );

        if (!populated.length) {
            return;
        }

        const section =
            document.createElement("div");

        section.className =
            "sample-origin-popup-section";

        popupText(
            section,
            "sample-origin-popup-section-title",
            title
        );

        populated.forEach(
            ([label, value]) => {
                addPopupField(
                    section,
                    label,
                    value
                );
            }
        );

        body.appendChild(
            section
        );
    }

    function makePopup(point) {
        const root =
            document.createElement("div");

        root.className =
            "sample-origin-popup-card";

        const header =
            document.createElement("div");

        header.className =
            "sample-origin-popup-header";

        popupText(
            header,
            "sample-origin-popup-organism",
            point.organism_name
                || "Unspecified organism"
        );

        popupText(
            header,
            "sample-origin-popup-sample-id",
            point.sample_id
                || "Sample"
        );

        const badges =
            document.createElement("div");

        badges.className =
            "sample-origin-popup-badges";

        [
            point.sample_type,
            point.status_label,
        ].forEach(
            (value) => {
                if (!popupHasValue(value)) {
                    return;
                }

                popupText(
                    badges,
                    "sample-origin-popup-badge",
                    value
                );
            }
        );

        if (badges.childElementCount) {
            header.appendChild(
                badges
            );
        }

        root.appendChild(
            header
        );

        const body =
            document.createElement("div");

        body.className =
            "sample-origin-popup-body";

        const lat =
            numberOrNull(
                point.latitude
            );

        const lng =
            numberOrNull(
                point.longitude
            );

        const coordinates =
            coordinatePairIsValid(
                lat,
                lng
            )
                ? (
                    `${lat.toFixed(6)}, `
                    + `${lng.toFixed(6)}`
                )
                : "";

        const depth =
            popupHasValue(
                point.depth_m
            )
                ? `${point.depth_m} m`
                : "";

        const elevation =
            popupHasValue(
                point.elevation_m
            )
                ? `${point.elevation_m} m`
                : "";

        addPopupSection(
            body,
            "Collection",
            [
                [
                    "Site",
                    point.collection_site_name,
                ],
                [
                    "Location",
                    point.geo_loc_name,
                ],
                [
                    "Country / Ocean",
                    point.country_or_ocean,
                ],
                [
                    "Collection date",
                    point.collection_date,
                ],
                [
                    "Coordinates",
                    coordinates,
                ],
                [
                    "Depth",
                    depth,
                ],
                [
                    "Elevation",
                    elevation,
                ],
            ]
        );

        addPopupSection(
            body,
            "Environment",
            [
                [
                    "Habitat",
                    point.habitat,
                ],
                [
                    "Medium",
                    point.environmental_medium,
                ],
                [
                    "Broad scale",
                    point.env_broad_scale,
                ],
                [
                    "Local scale",
                    point.env_local_scale,
                ],
            ]
        );

        addPopupSection(
            body,
            "Governance",
            [
                [
                    "Biobank",
                    point.biobank,
                ],
                [
                    "Research Group",
                    point.research_group,
                ],
                [
                    "Owner",
                    point.owner,
                ],
            ]
        );

        root.appendChild(
            body
        );

        if (point.detail_url) {
            const actions =
                document.createElement("div");

            actions.className =
                "sample-origin-popup-actions";

            const link =
                document.createElement("a");

            link.className =
                "sample-origin-popup-link";

            link.href =
                point.detail_url;

            link.textContent =
                "View Sample";

            actions.appendChild(
                link
            );

            root.appendChild(
                actions
            );
        }

        return root;
    }

    function initializeDashboardMap(container) {
        if (
            !container
            || container.dataset.mapInitialized === "true"
        ) {
            return;
        }

        const scriptId =
            container.dataset.pointsScript;

        if (!scriptId) {
            return;
        }

        const dataElement =
            document.getElementById(
                scriptId
            );

        if (!dataElement) {
            return;
        }

        let points = [];

        try {
            points = JSON.parse(
                dataElement.textContent
            );
        } catch (_error) {
            return;
        }

        const worldBounds = [
            [-85, -180],
            [85, 180],
        ];

        const worldViewBounds = [
            [-68, -175],
            [78, 175],
        ];

        const map = L.map(
            container,
            {
                worldCopyJump: false,
                zoomSnap: 0.25,
                maxBounds: worldBounds,
                maxBoundsViscosity: 0.85,
            }
        );

        addBaseLayer(
            map,
            {
                noWrap: true,
            }
        );

        map.fitBounds(
            worldViewBounds,
            {
                padding: [
                    8,
                    8,
                ],
                animate: false,
            }
        );

        const markerLayer =
            L.layerGroup().addTo(
                map
            );

        const typeFilter =
            document.getElementById(
                "sample-origin-filter-type"
            );

        const statusFilter =
            document.getElementById(
                "sample-origin-filter-status"
            );

        const biobankFilter =
            document.getElementById(
                "sample-origin-filter-biobank"
            );

        const groupFilter =
            document.getElementById(
                "sample-origin-filter-group"
            );

        const locationFilter =
            document.getElementById(
                "sample-origin-filter-location"
            );

        const environmentFilter =
            document.getElementById(
                "sample-origin-filter-environment"
            );

        const searchFilter =
            document.getElementById(
                "sample-origin-filter-search"
            );

        const habitatFilter =
            document.getElementById(
                "sample-origin-filter-habitat"
            );

        const broadScaleFilter =
            document.getElementById(
                "sample-origin-filter-broad-scale"
            );

        const localScaleFilter =
            document.getElementById(
                "sample-origin-filter-local-scale"
            );

        const siteFilter =
            document.getElementById(
                "sample-origin-filter-site"
            );

        const resetFilterButton =
            document.getElementById(
                "sample-origin-filter-reset"
            );

        const summaryElement =
            document.getElementById(
                "sample-origin-map-summary"
            );

        function selectedValue(element) {
            return element
                ? element.value
                : "";
        }

        function matches(
            point,
            key,
            value
        ) {
            if (!value) {
                return true;
            }

            return String(
                point[key] || ""
            ) === value;
        }

        function normalizeSearch(value) {
            return String(
                value || ""
            )
                .trim()
                .toLocaleLowerCase();
        }

        function searchMatches(
            point,
            value
        ) {
            const query =
                normalizeSearch(
                    value
                );

            if (!query) {
                return true;
            }

            return [
                point.sample_id,
                point.organism_name,
                point.sample_type,
                point.collection_site_name,
                point.geo_loc_name,
                point.country_or_ocean,
                point.environmental_medium,
                point.habitat,
                point.env_broad_scale,
                point.env_local_scale,
                point.biobank,
                point.research_group,
                point.owner,
            ].some(
                (candidate) => (
                    normalizeSearch(
                        candidate
                    ).includes(
                        query
                    )
                )
            );
        }

        let emptyOverlay = null;

        function updateEmptyOverlay(
            mappedCount
        ) {
            if (mappedCount > 0) {
                if (emptyOverlay) {
                    emptyOverlay.remove();
                    emptyOverlay = null;
                }

                return;
            }

            if (!emptyOverlay) {
                emptyOverlay =
                    document.createElement("div");

                emptyOverlay.className =
                    "sample-origin-map-empty-overlay";

                const card =
                    document.createElement("div");

                card.className =
                    "sample-origin-map-empty-card";

                const icon =
                    document.createElement("div");

                icon.className =
                    "sample-origin-map-empty-icon";

                const iconGlyph =
                    document.createElement("i");

                iconGlyph.className =
                    "bi bi-geo-alt";

                icon.appendChild(
                    iconGlyph
                );

                const copy =
                    document.createElement("div");

                const title =
                    document.createElement("div");

                title.className =
                    "sample-origin-map-empty-title";

                const detail =
                    document.createElement("div");

                detail.className =
                    "sample-origin-map-empty-text";

                copy.appendChild(
                    title
                );

                copy.appendChild(
                    detail
                );

                card.appendChild(
                    icon
                );

                card.appendChild(
                    copy
                );

                emptyOverlay.appendChild(
                    card
                );

                container.appendChild(
                    emptyOverlay
                );
            }

            const title =
                emptyOverlay.querySelector(
                    ".sample-origin-map-empty-title"
                );

            const detail =
                emptyOverlay.querySelector(
                    ".sample-origin-map-empty-text"
                );

            if (points.length) {
                title.textContent =
                    "No mapped Samples match the current filters.";

                detail.textContent =
                    "Reset or adjust the filters to display available geographic origins.";
            } else {
                title.textContent =
                    "No visible Samples currently have complete latitude / longitude origin data.";

                detail.textContent =
                    "The map will populate automatically as origin metadata is added.";
            }
        }

        function render() {
            markerLayer.clearLayers();

            const filtered =
                points.filter(
                    (point) => (
                        matches(
                            point,
                            "sample_type",
                            selectedValue(
                                typeFilter
                            )
                        )
                        && matches(
                            point,
                            "status",
                            selectedValue(
                                statusFilter
                            )
                        )
                        && matches(
                            point,
                            "biobank",
                            selectedValue(
                                biobankFilter
                            )
                        )
                        && matches(
                            point,
                            "research_group",
                            selectedValue(
                                groupFilter
                            )
                        )
                        && matches(
                            point,
                            "country_or_ocean",
                            selectedValue(
                                locationFilter
                            )
                        )
                        && matches(
                            point,
                            "environmental_medium",
                            selectedValue(
                                environmentFilter
                            )
                        )
                        && matches(
                            point,
                            "habitat",
                            selectedValue(
                                habitatFilter
                            )
                        )
                        && matches(
                            point,
                            "env_broad_scale",
                            selectedValue(
                                broadScaleFilter
                            )
                        )
                        && matches(
                            point,
                            "env_local_scale",
                            selectedValue(
                                localScaleFilter
                            )
                        )
                        && matches(
                            point,
                            "collection_site_name",
                            selectedValue(
                                siteFilter
                            )
                        )
                        && searchMatches(
                            point,
                            searchFilter
                                ? searchFilter.value
                                : ""
                        )
                    )
                );

            const coordinates = [];

            filtered.forEach(
                (point) => {
                    const lat =
                        numberOrNull(
                            point.latitude
                        );

                    const lng =
                        numberOrNull(
                            point.longitude
                        );

                    if (
                        !coordinatePairIsValid(
                            lat,
                            lng
                        )
                    ) {
                        return;
                    }

                    const icon =
                        L.divIcon(
                            {
                                className:
                                    "sample-origin-marker-icon",
                                html:
                                    '<span class="sample-origin-marker-dot"></span>',
                                iconSize: [
                                    22,
                                    22,
                                ],
                                iconAnchor: [
                                    11,
                                    11,
                                ],
                                popupAnchor: [
                                    0,
                                    -12,
                                ],
                            }
                        );

                    const marker =
                        L.marker(
                            [
                                lat,
                                lng,
                            ],
                            {
                                icon,
                                keyboard: true,
                                title:
                                    point.organism_name
                                    || point.sample_id
                                    || "Sample",
                            }
                        );

                    marker.bindPopup(
                        makePopup(
                            point
                        ),
                        {
                            className:
                                "sample-origin-leaflet-popup",
                            minWidth: 320,
                            maxWidth: 340,
                            autoPan: true,
                            autoPanPadding: [
                                24,
                                24,
                            ],
                        }
                    );

                    marker.addTo(
                        markerLayer
                    );

                    coordinates.push(
                        [
                            lat,
                            lng,
                        ]
                    );
                }
            );

            updateEmptyOverlay(
                coordinates.length
            );

            if (summaryElement) {
                summaryElement.textContent =
                    (
                        `${coordinates.length} mapped Sample`
                        + (
                            coordinates.length === 1
                                ? ""
                                : "s"
                        )
                        + ` of ${points.length} with coordinates`
                    );
            }

            if (coordinates.length === 1) {
                map.setView(
                    coordinates[0],
                    8
                );
            } else if (
                coordinates.length > 1
            ) {
                map.fitBounds(
                    L.latLngBounds(
                        coordinates
                    ),
                    {
                        padding: [
                            30,
                            30,
                        ],
                        maxZoom: 8,
                    }
                );
            } else {
                map.fitBounds(
                    worldViewBounds,
                    {
                        padding: [
                            8,
                            8,
                        ],
                        animate: false,
                    }
                );
            }
        }

        [
            typeFilter,
            statusFilter,
            biobankFilter,
            groupFilter,
            locationFilter,
            environmentFilter,
            habitatFilter,
            broadScaleFilter,
            localScaleFilter,
            siteFilter,
        ].forEach(
            (element) => {
                if (element) {
                    element.addEventListener(
                        "change",
                        render
                    );
                }
            }
        );

        if (searchFilter) {
            searchFilter.addEventListener(
                "input",
                render
            );
        }

        if (resetFilterButton) {
            resetFilterButton.addEventListener(
                "click",
                () => {
                    [
                        typeFilter,
                        statusFilter,
                        biobankFilter,
                        groupFilter,
                        locationFilter,
                        environmentFilter,
                        habitatFilter,
                        broadScaleFilter,
                        localScaleFilter,
                        siteFilter,
                    ].forEach(
                        (element) => {
                            if (element) {
                                element.value = "";
                            }
                        }
                    );

                    if (searchFilter) {
                        searchFilter.value = "";
                    }

                    render();
                }
            );
        }

        render();

        container.dataset.mapInitialized =
            "true";

        setTimeout(
            () => {
                map.invalidateSize();
            },
            0
        );
    }

    function initializeAll() {
        if (typeof L === "undefined") {
            return;
        }

        document
            .querySelectorAll(
                "[data-sample-origin-map]"
            )
            .forEach(
                initializeEditableMap
            );

        document
            .querySelectorAll(
                "[data-sample-origin-readonly-map]"
            )
            .forEach(
                initializeReadonlyMap
            );

        document
            .querySelectorAll(
                "[data-sample-origin-dashboard]"
            )
            .forEach(
                initializeDashboardMap
            );
    }

    if (
        document.readyState === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            initializeAll
        );
    } else {
        initializeAll();
    }
})();
