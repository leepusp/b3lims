(() => {
    "use strict";

    const DIRECTORY_DATA_ID =
        "public-biobank-map-data";

    const DETAIL_DATA_ID =
        "public-biobank-detail-map-data";

    const DEFAULT_CENTER = [
        0,
        0,
    ];

    const DEFAULT_ZOOM = 2;


    function readJsonScript(
        id
    ) {
        const node =
            document.getElementById(
                id
            );

        if (!node) {
            return null;
        }

        try {
            return JSON.parse(
                node.textContent
            );
        } catch (error) {
            console.error(
                "Unable to parse public Biobank map data.",
                error
            );

            return null;
        }
    }


    function createMap(
        node
    ) {
        if (
            !node
            || typeof window.L === "undefined"
        ) {
            return null;
        }

        const map = window.L.map(
            node,
            {
                scrollWheelZoom: false,
                zoomControl: true,
            }
        );

        window.L.tileLayer(
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            {
                maxZoom: 19,
                attribution:
                    '&copy; OpenStreetMap contributors',
            }
        ).addTo(
            map
        );

        return map;
    }


    function validCoordinate(
        value
    ) {
        return (
            typeof value === "number"
            && Number.isFinite(value)
        );
    }


    function mappedRecord(
        record
    ) {
        return (
            record
            && validCoordinate(
                record.latitude
            )
            && validCoordinate(
                record.longitude
            )
        );
    }


    function markerStyle(
        active = false
    ) {
        if (active) {
            return {
                radius: 10,
                color: "#174f7e",
                weight: 4,
                opacity: 1,
                fillColor: "#eaf4fb",
                fillOpacity: 1,
            };
        }

        return {
            radius: 8,
            color: "#2675bd",
            weight: 3,
            opacity: 0.95,
            fillColor: "#ffffff",
            fillOpacity: 1,
        };
    }


    function fitRecords(
        map,
        records
    ) {
        const points = records
            .filter(
                mappedRecord
            )
            .map(
                (record) => [
                    record.latitude,
                    record.longitude,
                ]
            );

        if (!points.length) {
            map.setView(
                DEFAULT_CENTER,
                DEFAULT_ZOOM
            );

            return;
        }

        if (points.length === 1) {
            map.setView(
                points[0],
                13
            );

            return;
        }

        map.fitBounds(
            points,
            {
                padding: [
                    35,
                    35,
                ],
                maxZoom: 12,
            }
        );
    }


    function setTooltip(
        marker,
        record
    ) {
        const label =
            document.createElement(
                "span"
            );

        label.className =
            "public-biobank-marker-label";

        label.textContent =
            record.name || "Biobank";

        marker.bindTooltip(
            label,
            {
                direction: "top",
                offset: [
                    0,
                    -8,
                ],
            }
        );
    }


    function initializeDirectory() {
        const root =
            document.querySelector(
                "[data-public-biobank-directory]"
            );

        if (!root) {
            return;
        }

        const mapNode =
            root.querySelector(
                "[data-public-biobank-map]"
            );

        const records =
            readJsonScript(
                DIRECTORY_DATA_ID
            ) || [];

        const map =
            createMap(
                mapNode
            );

        if (!map) {
            if (mapNode) {
                mapNode.classList.add(
                    "public-biobank-map-fallback"
                );

                mapNode.textContent =
                    "The interactive map could not be loaded. "
                    + "The public Biobank directory remains available.";
            }

            return;
        }

        const cards = Array.from(
            root.querySelectorAll(
                "[data-public-biobank-card]"
            )
        );

        const search =
            root.querySelector(
                "[data-public-biobank-search]"
            );

        const noResults =
            root.querySelector(
                "[data-public-biobank-no-results]"
            );

        const markers =
            new Map();

        let selectedId = null;


        records.forEach(
            (record) => {
                if (
                    !mappedRecord(
                        record
                    )
                ) {
                    return;
                }

                const marker =
                    window.L.circleMarker(
                        [
                            record.latitude,
                            record.longitude,
                        ],
                        markerStyle(
                            false
                        )
                    );

                marker.addTo(
                    map
                );

                setTooltip(
                    marker,
                    record
                );

                markers.set(
                    String(record.id),
                    marker
                );

                marker.on(
                    "click",
                    () => {
                        activate(
                            record.id,
                            true
                        );
                    }
                );
            }
        );


        function activate(
            id,
            scrollCard = false
        ) {
            selectedId =
                String(id);

            cards.forEach(
                (card) => {
                    const active = (
                        card.dataset.biobankId
                        === selectedId
                    );

                    card.classList.toggle(
                        "is-active",
                        active
                    );

                    if (
                        active
                        && scrollCard
                    ) {
                        card.scrollIntoView(
                            {
                                block: "nearest",
                                behavior: "smooth",
                            }
                        );
                    }
                }
            );

            markers.forEach(
                (
                    marker,
                    markerId
                ) => {
                    marker.setStyle(
                        markerStyle(
                            markerId
                            === selectedId
                        )
                    );
                }
            );

            const marker =
                markers.get(
                    selectedId
                );

            if (marker) {
                map.flyTo(
                    marker.getLatLng(),
                    Math.max(
                        map.getZoom(),
                        13
                    ),
                    {
                        duration: 0.5,
                    }
                );
            }
        }


        function applySearch() {
            const query = (
                search
                    ? search.value
                    : ""
            )
                .trim()
                .toLocaleLowerCase();

            const visibleIds =
                new Set();

            cards.forEach(
                (card) => {
                    const haystack = (
                        card.dataset.biobankSearch
                        || ""
                    ).toLocaleLowerCase();

                    const visible = (
                        !query
                        || haystack.includes(
                            query
                        )
                    );

                    card.hidden =
                        !visible;

                    if (visible) {
                        visibleIds.add(
                            card.dataset.biobankId
                        );
                    }
                }
            );

            const visibleRecords =
                records.filter(
                    (record) => (
                        visibleIds.has(
                            String(record.id)
                        )
                    )
                );

            markers.forEach(
                (
                    marker,
                    markerId
                ) => {
                    if (
                        visibleIds.has(
                            markerId
                        )
                    ) {
                        if (
                            !map.hasLayer(
                                marker
                            )
                        ) {
                            marker.addTo(
                                map
                            );
                        }
                    } else if (
                        map.hasLayer(
                            marker
                        )
                    ) {
                        marker.removeFrom(
                            map
                        );
                    }
                }
            );

            if (noResults) {
                noResults.hidden =
                    visibleIds.size !== 0;
            }

            if (
                selectedId
                && !visibleIds.has(
                    selectedId
                )
            ) {
                selectedId = null;

                cards.forEach(
                    (card) => {
                        card.classList.remove(
                            "is-active"
                        );
                    }
                );

                markers.forEach(
                    (marker) => {
                        marker.setStyle(
                            markerStyle(
                                false
                            )
                        );
                    }
                );
            }

            fitRecords(
                map,
                visibleRecords
            );
        }


        cards.forEach(
            (card) => {
                const focusButton =
                    card.querySelector(
                        "[data-public-biobank-focus]"
                    );

                if (!focusButton) {
                    return;
                }

                focusButton.addEventListener(
                    "click",
                    () => {
                        activate(
                            card.dataset.biobankId
                        );
                    }
                );
            }
        );


        if (search) {
            search.addEventListener(
                "input",
                applySearch
            );
        }


        fitRecords(
            map,
            records
        );

        setTimeout(
            () => {
                map.invalidateSize();
            },
            0
        );
    }


    function initializeDetail() {
        const mapNode =
            document.querySelector(
                "[data-public-biobank-detail-map]"
            );

        if (!mapNode) {
            return;
        }

        const record =
            readJsonScript(
                DETAIL_DATA_ID
            );

        if (
            !record
            || !mappedRecord(
                record
            )
        ) {
            return;
        }

        const map =
            createMap(
                mapNode
            );

        if (!map) {
            mapNode.classList.add(
                "public-biobank-map-fallback"
            );

            mapNode.textContent =
                "The interactive map could not be loaded.";

            return;
        }

        const marker =
            window.L.circleMarker(
                [
                    record.latitude,
                    record.longitude,
                ],
                markerStyle(
                    true
                )
            );

        marker.addTo(
            map
        );

        setTooltip(
            marker,
            record
        );

        map.setView(
            [
                record.latitude,
                record.longitude,
            ],
            14
        );

        setTimeout(
            () => {
                map.invalidateSize();
            },
            0
        );
    }


    initializeDirectory();
    initializeDetail();
})();
