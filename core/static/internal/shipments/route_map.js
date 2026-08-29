(() => {
    "use strict";

    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener(
                "DOMContentLoaded",
                callback,
                { once: true }
            );
            return;
        }

        callback();
    }

    function textElement(tag, className, text) {
        const node = document.createElement(tag);

        if (className) {
            node.className = className;
        }

        node.textContent = text || "";

        return node;
    }

    function normalized(value) {
        return String(value || "")
            .trim()
            .toLowerCase();
    }

    function formatDate(value) {
        if (!value) {
            return "Not recorded";
        }

        const parsed = new Date(value);

        if (Number.isNaN(parsed.getTime())) {
            return String(value);
        }

        return new Intl.DateTimeFormat(
            undefined,
            {
                year: "numeric",
                month: "short",
                day: "2-digit",
                hour: (
                    String(value).includes("T")
                        ? "2-digit"
                        : undefined
                ),
                minute: (
                    String(value).includes("T")
                        ? "2-digit"
                        : undefined
                ),
            }
        ).format(parsed);
    }

    function endpointCoordinates(endpoint) {
        if (
            !endpoint
            || endpoint.latitude === null
            || endpoint.longitude === null
            || endpoint.latitude === undefined
            || endpoint.longitude === undefined
        ) {
            return null;
        }

        const latitude = Number(
            endpoint.latitude
        );

        const longitude = Number(
            endpoint.longitude
        );

        if (
            !Number.isFinite(latitude)
            || !Number.isFinite(longitude)
        ) {
            return null;
        }

        return [
            latitude,
            longitude,
        ];
    }

    ready(() => {
        const root = document.querySelector(
            "[data-shipment-route-map]"
        );

        const dataNode = document.getElementById(
            "shipment-route-map-data"
        );

        if (!root || !dataNode) {
            return;
        }

        let payload;

        try {
            payload = JSON.parse(
                dataNode.textContent
            );
        } catch (error) {
            console.error(
                "Unable to parse Shipment route map data.",
                error
            );
            return;
        }

        const routes = Array.isArray(
            payload.routes
        )
            ? payload.routes
            : [];

        const listNode = root.querySelector(
            "[data-route-list]"
        );

        const listCountNode = root.querySelector(
            "[data-route-list-count]"
        );

        const paginationNode =
            document.createElement("div");

        paginationNode.className =
            "shipment-route-pagination";

        paginationNode.dataset.routePagination = "";

        listNode.insertAdjacentElement(
            "afterend",
            paginationNode
        );

        const visibleCountNode = root.querySelector(
            "[data-route-visible-count]"
        );

        const selectedNode = root.querySelector(
            "[data-route-selected]"
        );

        const mapEmptyNode = root.querySelector(
            "[data-route-map-empty]"
        );

        const filterNodes = {};

        root.querySelectorAll(
            "[data-route-filter]"
        ).forEach((node) => {
            filterNodes[
                node.dataset.routeFilter
            ] = node;
        });

        const resetButton = root.querySelector(
            "[data-route-reset]"
        );

        function uniqueOptions(accessor) {
            const values = new Map();

            routes.forEach((route) => {
                const pair = accessor(route);

                if (!pair) {
                    return;
                }

                const value = String(
                    pair.value || ""
                ).trim();

                const label = String(
                    pair.label || value
                ).trim();

                if (!value) {
                    return;
                }

                if (!values.has(value)) {
                    values.set(
                        value,
                        label
                    );
                }
            });

            return Array.from(
                values.entries()
            )
                .map(
                    ([value, label]) => ({
                        value,
                        label,
                    })
                )
                .sort(
                    (a, b) => (
                        a.label.localeCompare(
                            b.label
                        )
                    )
                );
        }

        function populateSelect(
            name,
            accessor
        ) {
            const node = filterNodes[name];

            if (!node) {
                return;
            }

            const options = uniqueOptions(
                accessor
            );

            options.forEach((item) => {
                const option =
                    document.createElement(
                        "option"
                    );

                option.value = item.value;
                option.textContent =
                    item.label;

                node.appendChild(option);
            });
        }

        populateSelect(
            "status",
            (route) => route.status
        );

        populateSelect(
            "flow",
            (route) => route.flow_type
        );

        populateSelect(
            "carrier",
            (route) => ({
                value:
                    route.carrier_name,
                label:
                    route.carrier_name,
            })
        );

        populateSelect(
            "origin",
            (route) => ({
                value:
                    route.origin?.name,
                label:
                    route.origin?.name,
            })
        );

        populateSelect(
            "destination",
            (route) => ({
                value:
                    route.destination?.name,
                label:
                    route.destination?.name,
            })
        );

        populateSelect(
            "temperature",
            (route) => ({
                value:
                    route.temperature_condition,
                label:
                    route.temperature_condition,
            })
        );

        let map = null;
        let routeLayer = null;

        if (
            window.L
            && document.getElementById(
                "shipment-route-map"
            )
        ) {
            map = window.L.map(
                "shipment-route-map",
                {
                    zoomControl: true,
                    scrollWheelZoom: true,
                }
            ).setView(
                [-14.235, -51.9253],
                4
            );

            window.L.tileLayer(
                "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                {
                    maxZoom: 19,
                    attribution:
                        "&copy; OpenStreetMap contributors",
                }
            ).addTo(map);

            routeLayer =
                window.L.layerGroup()
                    .addTo(map);

            window.setTimeout(
                () => {
                    map.invalidateSize();
                },
                80
            );
        }

        let selectedId = (
            routes.length
                ? routes[0].id
                : null
        );


        // SHIPMENT ROUTE PAGINATION V1
        const pageSize = 5;
        let currentPage = 1;

        function filterValue(name) {
            const node =
                filterNodes[name];

            if (!node) {
                return "";
            }

            return String(
                node.value || ""
            ).trim();
        }

        function filteredRoutes() {
            const search = normalized(
                filterValue("search")
            );

            const status =
                filterValue("status");

            const flow =
                filterValue("flow");

            const carrier =
                filterValue("carrier");

            const origin =
                filterValue("origin");

            const destination =
                filterValue("destination");

            const temperature =
                filterValue(
                    "temperature"
                );

            const mapping =
                filterValue("mapping");

            return routes.filter(
                (route) => {
                    if (
                        search
                        && !normalized(
                            route.search_text
                        ).includes(search)
                    ) {
                        return false;
                    }

                    if (
                        status
                        && route.status?.value
                            !== status
                    ) {
                        return false;
                    }

                    if (
                        flow
                        && route.flow_type?.value
                            !== flow
                    ) {
                        return false;
                    }

                    if (
                        carrier
                        && route.carrier_name
                            !== carrier
                    ) {
                        return false;
                    }

                    if (
                        origin
                        && route.origin?.name
                            !== origin
                    ) {
                        return false;
                    }

                    if (
                        destination
                        && route.destination?.name
                            !== destination
                    ) {
                        return false;
                    }

                    if (
                        temperature
                        && route.temperature_condition
                            !== temperature
                    ) {
                        return false;
                    }

                    if (
                        mapping
                        && route.mapping_status
                            !== mapping
                    ) {
                        return false;
                    }

                    return true;
                }
            );
        }

        function routeById(id) {
            return routes.find(
                (route) => (
                    String(route.id)
                    === String(id)
                )
            ) || null;
        }

        function mappingLabel(value) {
            if (value === "mapped") {
                return "Mapped";
            }

            if (value === "partial") {
                return "Partial";
            }

            return "Unmapped";
        }

        function appendChip(
            parent,
            text,
            mappingStatus
        ) {
            if (!text) {
                return;
            }

            const chip = textElement(
                "span",
                "shipment-route-chip",
                text
            );

            if (mappingStatus) {
                chip.dataset.mapping =
                    mappingStatus;
            }

            parent.appendChild(chip);
        }

        function renderPagination(
            filtered,
            start,
            end
        ) {
            paginationNode.replaceChildren();

            if (
                !filtered.length
                || filtered.length <= pageSize
            ) {
                paginationNode.hidden = true;
                return;
            }

            paginationNode.hidden = false;

            const pageCount = Math.ceil(
                filtered.length / pageSize
            );

            const summary = textElement(
                "span",
                "shipment-route-pagination-summary",
                `${start + 1}\u2013${end} of ${filtered.length}`
            );

            const controls =
                document.createElement("div");

            controls.className =
                "shipment-route-pagination-controls";

            function goToPage(page) {
                const target = Math.min(
                    pageCount,
                    Math.max(1, page)
                );

                currentPage = target;

                const firstIndex =
                    (currentPage - 1) * pageSize;

                if (filtered[firstIndex]) {
                    selectedId =
                        filtered[firstIndex].id;
                }

                render();
            }

            function addButton(
                label,
                page,
                options = {}
            ) {
                const button =
                    document.createElement(
                        "button"
                    );

                button.type = "button";
                button.className =
                    "shipment-route-pagination-button";

                button.textContent = label;

                if (options.current) {
                    button.classList.add(
                        "is-current"
                    );

                    button.setAttribute(
                        "aria-current",
                        "page"
                    );
                }

                button.disabled =
                    Boolean(options.disabled);

                button.addEventListener(
                    "click",
                    () => {
                        if (!button.disabled) {
                            goToPage(page);
                        }
                    }
                );

                controls.appendChild(button);
            }

            function addEllipsis() {
                controls.appendChild(
                    textElement(
                        "span",
                        "shipment-route-pagination-ellipsis",
                        "\u2026"
                    )
                );
            }

            addButton(
                "\u2039",
                currentPage - 1,
                {
                    disabled:
                        currentPage <= 1,
                }
            );

            const pageNumbers = [];

            if (pageCount <= 7) {
                for (
                    let page = 1;
                    page <= pageCount;
                    page += 1
                ) {
                    pageNumbers.push(page);
                }
            } else {
                const candidates = new Set([
                    1,
                    pageCount,
                    currentPage - 1,
                    currentPage,
                    currentPage + 1,
                ]);

                Array.from(candidates)
                    .filter(
                        (page) => (
                            page >= 1
                            && page <= pageCount
                        )
                    )
                    .sort((a, b) => a - b)
                    .forEach(
                        (page) => {
                            pageNumbers.push(page);
                        }
                    );
            }

            let previousPage = null;

            pageNumbers.forEach((page) => {
                if (
                    previousPage !== null
                    && page - previousPage > 1
                ) {
                    addEllipsis();
                }

                addButton(
                    String(page),
                    page,
                    {
                        current:
                            page === currentPage,
                    }
                );

                previousPage = page;
            });

            addButton(
                "\u203a",
                currentPage + 1,
                {
                    disabled:
                        currentPage >= pageCount,
                }
            );

            paginationNode.appendChild(
                summary
            );

            paginationNode.appendChild(
                controls
            );
        }


        function renderList(filtered) {
            listNode.replaceChildren();

            const pageCount = Math.max(
                1,
                Math.ceil(
                    filtered.length / pageSize
                )
            );

            currentPage = Math.min(
                currentPage,
                pageCount
            );

            const start =
                (currentPage - 1) * pageSize;

            const end = Math.min(
                start + pageSize,
                filtered.length
            );

            const pageRoutes =
                filtered.slice(
                    start,
                    end
                );

            if (listCountNode) {
                listCountNode.textContent = (
                    filtered.length
                        ? `${start + 1}–${end} of ${filtered.length}`
                        : "0 of 0"
                );
            }

            if (visibleCountNode) {
                visibleCountNode.textContent =
                    String(filtered.length);
            }

            renderPagination(
                filtered,
                start,
                end
            );

            if (!filtered.length) {
                listNode.appendChild(
                    textElement(
                        "div",
                        "shipment-route-list-empty",
                        "No Shipments match the active filters."
                    )
                );
                return;
            }

            pageRoutes.forEach((route) => {
                const button =
                    document.createElement(
                        "button"
                    );

                button.type = "button";
                button.className =
                    "shipment-route-card";

                if (
                    String(route.id)
                    === String(selectedId)
                ) {
                    button.classList.add(
                        "is-selected"
                    );
                }

                button.dataset.routeId =
                    String(route.id);

                const top =
                    document.createElement(
                        "div"
                    );

                top.className =
                    "shipment-route-card-top";

                top.appendChild(
                    textElement(
                        "div",
                        "shipment-route-code",
                        route.shipment_code
                    )
                );

                const status =
                    textElement(
                        "span",
                        "shipment-route-chip",
                        route.status?.label
                            || route.status?.value
                            || "Unknown"
                    );

                top.appendChild(status);
                button.appendChild(top);

                const path =
                    document.createElement(
                        "div"
                    );

                path.className =
                    "shipment-route-card-path";

                path.appendChild(
                    textElement(
                        "span",
                        "",
                        route.origin?.name
                            || "Unassigned"
                    )
                );

                const arrow =
                    document.createElement(
                        "i"
                    );

                arrow.className =
                    "bi bi-arrow-right";

                path.appendChild(arrow);

                path.appendChild(
                    textElement(
                        "span",
                        "",
                        route.destination?.name
                            || "Unassigned"
                    )
                );

                button.appendChild(path);

                const meta =
                    document.createElement(
                        "div"
                    );

                meta.className =
                    "shipment-route-card-meta";

                appendChip(
                    meta,
                    mappingLabel(
                        route.mapping_status
                    ),
                    route.mapping_status
                );

                appendChip(
                    meta,
                    route.carrier_name
                        || "Carrier not assigned"
                );

                if (
                    route.item_count !== undefined
                ) {
                    appendChip(
                        meta,
                        `${route.item_count} item${
                            route.item_count === 1
                                ? ""
                                : "s"
                        }`
                    );
                }

                button.appendChild(meta);

                button.addEventListener(
                    "click",
                    () => {
                        selectRoute(
                            route.id,
                            true
                        );
                    }
                );

                listNode.appendChild(
                    button
                );
            });
        }

        function tooltipNode(route) {
            const wrapper =
                document.createElement(
                    "div"
                );

            wrapper.appendChild(
                textElement(
                    "div",
                    "",
                    route.shipment_code
                )
            );

            wrapper.appendChild(
                textElement(
                    "div",
                    "",
                    `${route.origin?.name || "Origin"} → ${
                        route.destination?.name
                        || "Destination"
                    }`
                )
            );

            return wrapper;
        }

        function addEndpointMarker(
            route,
            endpoint,
            role,
            selected
        ) {
            if (!map || !routeLayer) {
                return null;
            }

            const coordinates =
                endpointCoordinates(
                    endpoint
                );

            if (!coordinates) {
                return null;
            }

            const marker =
                window.L.circleMarker(
                    coordinates,
                    {
                        radius:
                            selected
                                ? 7
                                : 5,
                        color:
                            role === "origin"
                                ? "#0f766e"
                                : "#7c3aed",
                        weight: 2,
                        fillColor:
                            role === "origin"
                                ? "#14b8a6"
                                : "#8b5cf6",
                        fillOpacity: 0.92,
                    }
                ).addTo(routeLayer);

            const tooltip =
                document.createElement(
                    "div"
                );

            tooltip.appendChild(
                textElement(
                    "strong",
                    "",
                    role === "origin"
                        ? "Origin"
                        : "Destination"
                )
            );

            tooltip.appendChild(
                textElement(
                    "div",
                    "",
                    endpoint.name
                        || "Unassigned"
                )
            );

            marker.bindTooltip(
                tooltip,
                {
                    direction: "top",
                }
            );

            marker.on(
                "click",
                () => {
                    selectRoute(
                        route.id,
                        true
                    );
                }
            );

            return coordinates;
        }

        function renderMap(filtered) {
            if (!map || !routeLayer) {
                if (mapEmptyNode) {
                    mapEmptyNode.hidden = false;
                    mapEmptyNode.textContent =
                        "Leaflet could not be loaded. Shipment records remain available in the list.";
                }
                return;
            }

            routeLayer.clearLayers();

            const allCoordinates = [];

            filtered.forEach((route) => {
                const selected = (
                    String(route.id)
                    === String(selectedId)
                );

                const origin =
                    endpointCoordinates(
                        route.origin
                    );

                const destination =
                    endpointCoordinates(
                        route.destination
                    );

                if (
                    origin
                    && destination
                ) {
                    const line =
                        window.L.polyline(
                            [
                                origin,
                                destination,
                            ],
                            {
                                color:
                                    selected
                                        ? "#7c3aed"
                                        : "#2563eb",
                                weight:
                                    selected
                                        ? 5
                                        : 3,
                                opacity:
                                    selected
                                        ? 0.95
                                        : 0.58,
                                dashArray:
                                    selected
                                        ? null
                                        : "7 6",
                            }
                        ).addTo(
                            routeLayer
                        );

                    line.bindTooltip(
                        tooltipNode(route),
                        {
                            sticky: true,
                        }
                    );

                    line.on(
                        "click",
                        () => {
                            selectRoute(
                                route.id,
                                true
                            );
                        }
                    );
                }

                const originPoint =
                    addEndpointMarker(
                        route,
                        route.origin,
                        "origin",
                        selected
                    );

                const destinationPoint =
                    addEndpointMarker(
                        route,
                        route.destination,
                        "destination",
                        selected
                    );

                if (originPoint) {
                    allCoordinates.push(
                        originPoint
                    );
                }

                if (destinationPoint) {
                    allCoordinates.push(
                        destinationPoint
                    );
                }
            });

            if (mapEmptyNode) {
                if (
                    filtered.length
                    && !allCoordinates.length
                ) {
                    mapEmptyNode.hidden = false;
                    mapEmptyNode.textContent =
                        "The filtered Shipments do not have registered Biobank coordinates.";
                } else if (
                    !filtered.length
                ) {
                    mapEmptyNode.hidden = false;
                    mapEmptyNode.textContent =
                        "No Shipments match the active filters.";
                } else {
                    mapEmptyNode.hidden = true;
                }
            }

            if (allCoordinates.length > 1) {
                map.fitBounds(
                    window.L.latLngBounds(
                        allCoordinates
                    ),
                    {
                        padding: [40, 40],
                        maxZoom: 7,
                    }
                );
            } else if (
                allCoordinates.length === 1
            ) {
                map.setView(
                    allCoordinates[0],
                    6
                );
            }
        }

        function summaryItem(
            key,
            value
        ) {
            const wrapper =
                document.createElement(
                    "div"
                );

            wrapper.className =
                "shipment-route-summary-item";

            wrapper.appendChild(
                textElement(
                    "div",
                    "shipment-route-summary-key",
                    key
                )
            );

            wrapper.appendChild(
                textElement(
                    "div",
                    "shipment-route-summary-value",
                    value || "Not recorded"
                )
            );

            return wrapper;
        }

        function manifestDescription(item) {
            const parts = [];

            if (item.material_name) {
                parts.push(
                    item.material_name
                );
            }

            if (item.sample_type) {
                parts.push(
                    item.sample_type
                );
            }

            if (item.quantity) {
                parts.push(
                    `${item.quantity}${
                        item.quantity_unit
                            ? ` ${item.quantity_unit}`
                            : ""
                    }`
                );
            }

            if (item.container_count) {
                parts.push(
                    `${item.container_count} container${
                        Number(item.container_count) === 1
                            ? ""
                            : "s"
                    }`
                );
            }

            if (item.storage_condition) {
                parts.push(
                    item.storage_condition
                );
            }

            return parts.join(" · ");
        }

        function renderSelected(route) {
            selectedNode.replaceChildren();

            if (!route) {
                selectedNode.appendChild(
                    textElement(
                        "div",
                        "shipment-route-selected-empty",
                        "Select a Shipment to inspect its route, manifest and custody timeline."
                    )
                );
                return;
            }

            const header =
                document.createElement(
                    "div"
                );

            header.className =
                "shipment-route-selected-header";

            const heading =
                document.createElement(
                    "div"
                );

            const title =
                document.createElement(
                    "h3"
                );

            title.className =
                "shipment-route-selected-title";

            const link =
                document.createElement(
                    "a"
                );

            link.href =
                route.detail_url || "#";

            link.textContent =
                route.shipment_code;

            title.appendChild(link);
            heading.appendChild(title);

            heading.appendChild(
                textElement(
                    "div",
                    "shipment-route-selected-subtitle",
                    `${route.origin?.name || "Unassigned"} → ${
                        route.destination?.name
                        || "Unassigned"
                    }`
                )
            );

            header.appendChild(
                heading
            );

            header.appendChild(
                textElement(
                    "span",
                    "shipment-route-status",
                    route.status?.label
                        || route.status?.value
                        || "Unknown"
                )
            );

            selectedNode.appendChild(
                header
            );

            const summary =
                document.createElement(
                    "div"
                );

            summary.className =
                "shipment-route-selected-summary";

            summary.appendChild(
                summaryItem(
                    "Route coverage",
                    mappingLabel(
                        route.mapping_status
                    )
                )
            );

            summary.appendChild(
                summaryItem(
                    "Carrier",
                    route.carrier_name
                        || "Not assigned"
                )
            );

            summary.appendChild(
                summaryItem(
                    "Tracking",
                    route.tracking_code
                        || "Not recorded"
                )
            );

            summary.appendChild(
                summaryItem(
                    "Temperature",
                    route.temperature_condition
                        || "Not recorded"
                )
            );

            summary.appendChild(
                summaryItem(
                    "Flow",
                    route.flow_type?.label
                        || route.flow_type?.value
                )
            );

            summary.appendChild(
                summaryItem(
                    "Dispatched",
                    formatDate(
                        route.dates?.dispatched_at
                        || route.dates?.expected_dispatch_date
                    )
                )
            );

            summary.appendChild(
                summaryItem(
                    "Expected arrival",
                    formatDate(
                        route.dates?.expected_arrival_date
                    )
                )
            );

            summary.appendChild(
                summaryItem(
                    "Received",
                    formatDate(
                        route.dates?.received_at
                    )
                )
            );

            selectedNode.appendChild(
                summary
            );

            const grid =
                document.createElement(
                    "div"
                );

            grid.className =
                "shipment-route-selected-grid";

            const timelineSection =
                document.createElement(
                    "section"
                );

            timelineSection.className =
                "shipment-route-selected-section";

            const timelineTitle =
                document.createElement(
                    "div"
                );

            timelineTitle.className =
                "shipment-route-section-title";

            timelineTitle.appendChild(
                textElement(
                    "span",
                    "",
                    "Custody timeline"
                )
            );

            timelineTitle.appendChild(
                textElement(
                    "span",
                    "shipment-route-section-count",
                    `${route.events?.length || 0} events`
                )
            );

            timelineSection.appendChild(
                timelineTitle
            );

            const timeline =
                document.createElement(
                    "div"
                );

            timeline.className =
                "shipment-route-timeline";

            const events =
                Array.isArray(
                    route.events
                )
                    ? route.events
                    : [];

            if (!events.length) {
                timeline.appendChild(
                    textElement(
                        "div",
                        "shipment-route-inline-empty",
                        "No custody events recorded."
                    )
                );
            } else {
                events.forEach(
                    (event) => {
                        const row =
                            document.createElement(
                                "div"
                            );

                        row.className =
                            "shipment-route-event";

                        const rail =
                            document.createElement(
                                "div"
                            );

                        rail.className =
                            "shipment-route-event-rail";

                        rail.appendChild(
                            document.createElement(
                                "span"
                            )
                        );

                        rail.firstChild.className =
                            "shipment-route-event-dot";

                        row.appendChild(
                            rail
                        );

                        const content =
                            document.createElement(
                                "div"
                            );

                        content.appendChild(
                            textElement(
                                "div",
                                "shipment-route-event-title",
                                event.label
                                    || event.event_type
                                    || "Event"
                            )
                        );

                        content.appendChild(
                            textElement(
                                "div",
                                "shipment-route-event-meta",
                                `${event.actor || "System"} · ${
                                    formatDate(
                                        event.created_at
                                    )
                                }`
                            )
                        );

                        if (event.notes) {
                            content.appendChild(
                                textElement(
                                    "div",
                                    "shipment-route-event-note",
                                    event.notes
                                )
                            );
                        }

                        row.appendChild(
                            content
                        );

                        timeline.appendChild(
                            row
                        );
                    }
                );
            }

            timelineSection.appendChild(
                timeline
            );

            const manifestSection =
                document.createElement(
                    "section"
                );

            manifestSection.className =
                "shipment-route-selected-section";

            const manifestTitle =
                document.createElement(
                    "div"
                );

            manifestTitle.className =
                "shipment-route-section-title";

            manifestTitle.appendChild(
                textElement(
                    "span",
                    "",
                    "Shipment manifest"
                )
            );

            manifestTitle.appendChild(
                textElement(
                    "span",
                    "shipment-route-section-count",
                    `${route.item_count || 0} items`
                )
            );

            manifestSection.appendChild(
                manifestTitle
            );

            const manifest =
                document.createElement(
                    "div"
                );

            manifest.className =
                "shipment-route-manifest";

            const items =
                Array.isArray(
                    route.items
                )
                    ? route.items
                    : [];

            if (!items.length) {
                manifest.appendChild(
                    textElement(
                        "div",
                        "shipment-route-inline-empty",
                        "No Shipment items recorded."
                    )
                );
            } else {
                items.forEach(
                    (item) => {
                        const row =
                            document.createElement(
                                "div"
                            );

                        row.className =
                            "shipment-route-manifest-item";

                        row.appendChild(
                            textElement(
                                "div",
                                "shipment-route-manifest-id",
                                item.sample_id
                                    || "Unidentified item"
                            )
                        );

                        const description =
                            manifestDescription(
                                item
                            );

                        if (description) {
                            row.appendChild(
                                textElement(
                                    "div",
                                    "shipment-route-manifest-meta",
                                    description
                                )
                            );
                        }

                        manifest.appendChild(
                            row
                        );
                    }
                );
            }

            manifestSection.appendChild(
                manifest
            );

            grid.appendChild(
                timelineSection
            );

            grid.appendChild(
                manifestSection
            );

            selectedNode.appendChild(
                grid
            );
        }

        function focusRoute(route) {
            if (!map || !route) {
                return;
            }

            const points = [
                endpointCoordinates(
                    route.origin
                ),
                endpointCoordinates(
                    route.destination
                ),
            ].filter(Boolean);

            if (points.length > 1) {
                map.fitBounds(
                    window.L.latLngBounds(
                        points
                    ),
                    {
                        padding: [70, 70],
                        maxZoom: 7,
                    }
                );
            } else if (
                points.length === 1
            ) {
                map.setView(
                    points[0],
                    7
                );
            }
        }

        function render() {
            const filtered =
                filteredRoutes();

            if (
                filtered.length
                && !filtered.some(
                    (route) => (
                        String(route.id)
                        === String(selectedId)
                    )
                )
            ) {
                selectedId =
                    filtered[0].id;
            }

            if (!filtered.length) {
                selectedId = null;
            }

            renderList(filtered);
            renderMap(filtered);
            renderSelected(
                routeById(
                    selectedId
                )
            );
        }

        function selectRoute(
            id,
            focus
        ) {
            const filtered =
                filteredRoutes();

            const routeIndex =
                filtered.findIndex(
                    (route) => (
                        String(route.id)
                        === String(id)
                    )
                );

            if (routeIndex >= 0) {
                currentPage =
                    Math.floor(
                        routeIndex / pageSize
                    ) + 1;
            }

            selectedId = id;
            render();

            if (focus) {
                focusRoute(
                    routeById(id)
                );
            }
        }

        Object.values(
            filterNodes
        ).forEach((node) => {
            const eventName = (
                node.type === "search"
                    ? "input"
                    : "change"
            );

            node.addEventListener(
                eventName,
                () => {
                    currentPage = 1;
                    render();
                }
            );
        });

        if (resetButton) {
            resetButton.addEventListener(
                "click",
                () => {
                    Object.values(
                        filterNodes
                    ).forEach((node) => {
                        node.value = "";
                    });

                    currentPage = 1;

                    selectedId = (
                        routes.length
                            ? routes[0].id
                            : null
                    );

                    render();
                }
            );
        }

        render();
    });
})();
