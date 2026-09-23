(function (global) {
    "use strict";

    const DEFAULT_TILE_URL =
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

    const DEFAULT_TILE_ATTRIBUTION =
        "&copy; OpenStreetMap contributors";

    const LOCAL_ATTRIBUTION =
        "Natural Earth";

    const ERROR_THRESHOLD = 4;
    const STARTUP_TIMEOUT_MS = 5000;

    function requireLeaflet() {
        if (!global.L) {
            throw new Error(
                "B3Map requires local Leaflet."
            );
        }
    }

    function ensureFallbackPane(map) {
        const paneName = "b3-local-basemap";

        if (!map.getPane(paneName)) {
            const pane = map.createPane(
                paneName
            );

            pane.style.zIndex = "150";
            pane.style.pointerEvents = "none";
        }

        return paneName;
    }

    function addLocalBasemap(map) {
        requireLeaflet();

        if (
            !global.B3_WORLD_COUNTRIES
            || global.B3_WORLD_COUNTRIES.type
                !== "FeatureCollection"
        ) {
            throw new Error(
                "B3Map local world dataset is unavailable."
            );
        }

        const pane = ensureFallbackPane(map);

        const layer = global.L.geoJSON(
            global.B3_WORLD_COUNTRIES,
            {
                pane: pane,

                style: function () {
                    return {
                        color: "#94a3b8",
                        weight: 0.8,
                        opacity: 1,
                        fillColor: "#f1f5f9",
                        fillOpacity: 1,
                    };
                },

                interactive: false,
            }
        ).addTo(map);

        if (
            map.attributionControl
            && typeof map.attributionControl.addAttribution
                === "function"
        ) {
            map.attributionControl.addAttribution(
                LOCAL_ATTRIBUTION
            );
        }

        return layer;
    }

    function statusControl(map) {
        const control = global.L.control({
            position: "bottomleft",
        });

        control.onAdd = function () {
            const node = global.L.DomUtil.create(
                "div",
                "b3-map-basemap-status"
            );

            node.hidden = true;

            return node;
        };

        control.addTo(map);

        return control.getContainer();
    }

    function showLocalStatus(
        node,
        message
    ) {
        node.textContent = message;
        node.hidden = false;
    }

    function addResilientBasemap(
        map,
        options
    ) {
        requireLeaflet();

        const config = options || {};

        const localLayer =
            addLocalBasemap(map);

        const status =
            statusControl(map);

        /*
         * Remote raster tiles are opt-in.
         *
         * A remote provider can return a block/error image that
         * still fires Leaflet's tileload event. Therefore remote
         * tiles must never be required for the default map.
         */
        if (
            config.remote !== true
            || (
                global.navigator
                && global.navigator.onLine === false
            )
        ) {
            showLocalStatus(
                status,
                "Using local geographic basemap."
            );

            return {
                localLayer: localLayer,
                tileLayer: null,
                mode: "local",
            };
        }

        let failures = 0;
        let loaded = 0;
        let consecutiveFailures = 0;
        let failedOver = false;
        let fallbackTimer = null;

        const tileLayer = global.L.tileLayer(
            config.tileUrl || DEFAULT_TILE_URL,
            {
                maxZoom:
                    config.maxZoom === undefined
                        ? 19
                        : config.maxZoom,

                noWrap:
                    config.noWrap === true,

                bounds:
                    config.bounds
                    || (
                        config.noWrap === true
                            ? [
                                [-85.05112878, -180],
                                [85.05112878, 180],
                            ]
                            : undefined
                    ),

                attribution:
                    config.attribution
                    || DEFAULT_TILE_ATTRIBUTION,
            }
        );

        function failOver(reason) {
            if (failedOver) {
                return;
            }

            failedOver = true;

            if (fallbackTimer !== null) {
                global.clearTimeout(
                    fallbackTimer
                );

                fallbackTimer = null;
            }

            if (map.hasLayer(tileLayer)) {
                map.removeLayer(tileLayer);
            }

            showLocalStatus(
                status,
                "Detailed basemap unavailable — "
                + "using local geographic map."
            );

            map.fire(
                "b3:basemapfallback",
                {
                    reason: reason,
                    failures: failures,
                    loaded: loaded,
                }
            );
        }

        tileLayer.on(
            "tileload",
            function () {
                loaded += 1;
                consecutiveFailures = 0;

                /*
                 * At least one tile proves that the remote
                 * provider is currently responding.
                 */
                if (fallbackTimer !== null) {
                    global.clearTimeout(
                        fallbackTimer
                    );

                    fallbackTimer = null;
                }
            }
        );

        tileLayer.on(
            "tileerror",
            function () {
                failures += 1;
                consecutiveFailures += 1;

                if (
                    consecutiveFailures
                        >= ERROR_THRESHOLD
                    || (
                        failures
                            >= ERROR_THRESHOLD
                        && failures > loaded
                    )
                ) {
                    failOver(
                        "tileerror"
                    );
                }
            }
        );

        tileLayer.addTo(map);

        const timeoutMs =
            Number.isFinite(config.timeoutMs)
                ? config.timeoutMs
                : STARTUP_TIMEOUT_MS;

        fallbackTimer = global.setTimeout(
            function () {
                if (
                    !failedOver
                    && loaded === 0
                ) {
                    failOver(
                        "startup-timeout"
                    );
                }
            },
            timeoutMs
        );

        return {
            localLayer: localLayer,
            tileLayer: tileLayer,

            get mode() {
                return failedOver
                    ? "local"
                    : "remote";
            },

            failOver: failOver,
        };
    }

    global.B3Map = Object.freeze({
        addLocalBasemap:
            addLocalBasemap,

        addResilientBasemap:
            addResilientBasemap,
    });
})(window);
