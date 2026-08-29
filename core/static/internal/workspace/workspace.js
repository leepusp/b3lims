(() => {
    "use strict";

    const tooltip = document.createElement("div");

    tooltip.className = "workspace-chart-tooltip";
    tooltip.setAttribute("role", "status");
    tooltip.setAttribute("aria-live", "polite");

    document.body.appendChild(tooltip);


    const positionTooltip = (event, element) => {
        let x;
        let y;

        if (event && event.clientX && event.clientY) {
            x = event.clientX + 14;
            y = event.clientY + 14;
        } else {
            const rect = element.getBoundingClientRect();

            x = rect.left + rect.width / 2;
            y = rect.top - 8;
        }

        tooltip.style.left = `${x}px`;
        tooltip.style.top = `${y}px`;
    };


    const showTooltip = (
        element,
        event,
        extra = "",
    ) => {
        const label =
            element.dataset.chartLabel || "";

        const total =
            element.dataset.chartTotal || "0";

        const percent =
            element.dataset.chartPercent;

        const details = percent
            ? `${total} Samples · ${percent}%`
            : `${total} Samples`;

        const title =
            document.createElement("strong");

        const detail =
            document.createElement("span");

        title.textContent = label;
        detail.textContent = details + extra;

        tooltip.replaceChildren(
            title,
            detail,
        );

        positionTooltip(event, element);

        tooltip.classList.add("is-visible");
    };


    const hideTooltip = () => {
        tooltip.classList.remove("is-visible");
    };


    const bindDonut = () => {
        const donut =
            document.querySelector(".workspace-donut");

        const legend =
            document.querySelector(".workspace-chart-legend");

        if (!donut || !legend) {
            return;
        }

        const segments = [
            ...donut.querySelectorAll(
                ".workspace-donut-segment"
            ),
        ];

        const rows = [
            ...legend.querySelectorAll(
                ".workspace-legend-row"
            ),
        ];


        const clear = () => {
            donut.classList.remove("is-interacting");
            legend.classList.remove("is-interacting");

            segments.forEach(
                (node) => node.classList.remove("is-active")
            );

            rows.forEach(
                (node) => node.classList.remove("is-active")
            );

            hideTooltip();
        };


        const activate = (
            index,
            source,
            event,
        ) => {
            donut.classList.add("is-interacting");
            legend.classList.add("is-interacting");

            segments.forEach((node) => {
                node.classList.toggle(
                    "is-active",
                    node.dataset.chartIndex === index,
                );
            });

            rows.forEach((node) => {
                node.classList.toggle(
                    "is-active",
                    node.dataset.chartIndex === index,
                );
            });

            const segment = segments.find(
                (node) => node.dataset.chartIndex === index
            );

            if (segment) {
                showTooltip(
                    segment,
                    event,
                );
            } else {
                showTooltip(
                    source,
                    event,
                );
            }
        };


        [...segments, ...rows].forEach((node) => {
            const index =
                node.dataset.chartIndex;

            node.addEventListener(
                "mouseenter",
                (event) => activate(
                    index,
                    node,
                    event,
                ),
            );

            node.addEventListener(
                "focus",
                (event) => activate(
                    index,
                    node,
                    event,
                ),
            );

            node.addEventListener(
                "mousemove",
                (event) => {
                    if (
                        tooltip.classList.contains(
                            "is-visible"
                        )
                    ) {
                        positionTooltip(
                            event,
                            node,
                        );
                    }
                },
            );

            node.addEventListener(
                "mouseleave",
                clear,
            );

            node.addEventListener(
                "blur",
                clear,
            );

            node.addEventListener(
                "keydown",
                (event) => {
                    if (
                        event.key === "Escape"
                    ) {
                        node.blur();
                        clear();
                    }
                },
            );
        });
    };


    const bindBars = () => {
        const chart =
            document.querySelector(
                ".workspace-bar-chart"
            );

        if (!chart) {
            return;
        }

        const bars = [
            ...chart.querySelectorAll(
                ".workspace-bar-column"
            ),
        ];

        const denominator = Number(
            chart.dataset.chartDenominator || 0
        );

        if (denominator > 0) {
            bars.forEach((node) => {
                const total = Number(
                    node.dataset.chartTotal || 0
                );

                const percent =
                    (total / denominator) * 100;

                node.dataset.chartPercent =
                    percent
                        .toFixed(1)
                        .replace(/\.0$/, "");
            });
        }


        const clear = () => {
            chart.classList.remove(
                "is-interacting"
            );

            bars.forEach(
                (node) => node.classList.remove(
                    "is-active"
                )
            );

            hideTooltip();
        };


        const activate = (
            node,
            event,
        ) => {
            chart.classList.add(
                "is-interacting"
            );

            bars.forEach((candidate) => {
                candidate.classList.toggle(
                    "is-active",
                    candidate === node,
                );
            });

            showTooltip(
                node,
                event,
            );
        };


        bars.forEach((node) => {
            node.addEventListener(
                "mouseenter",
                (event) => activate(
                    node,
                    event,
                ),
            );

            node.addEventListener(
                "focus",
                (event) => activate(
                    node,
                    event,
                ),
            );

            node.addEventListener(
                "mousemove",
                (event) => positionTooltip(
                    event,
                    node,
                ),
            );

            node.addEventListener(
                "mouseleave",
                clear,
            );

            node.addEventListener(
                "blur",
                clear,
            );

            node.addEventListener(
                "keydown",
                (event) => {
                    if (
                        event.key === "Escape"
                    ) {
                        node.blur();
                        clear();
                    }
                },
            );
        });
    };


    const initialize = () => {
        bindDonut();
        bindBars();
    };


    if (
        document.readyState === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            initialize,
            { once: true },
        );
    } else {
        initialize();
    }
})();
