/*
 * B3 LIMS V8 — read-only spatial scene filter.
 *
 * Applies a saved physical hierarchy to the existing viewer.
 * Does not mutate Django data, sample assignments or the demo.
 */
(() => {
    "use strict";

    function scope(nodes, samples, projection) {
        if (
            !projection ||
            projection.read_only !== true ||
            !Array.isArray(projection.nodes) ||
            !Array.isArray(nodes) ||
            !Array.isArray(samples)
        ) {
            throw new Error("Invalid saved scene projection.");
        }

        const rootId = String(projection.scene_root_id);
        const projected = new Map();

        for (const node of projection.nodes) {
            const id = String(node.id);

            if (projected.has(id)) {
                throw new Error("Duplicate projected location.");
            }

            projected.set(id, node);
        }

        if (!projected.has(rootId)) {
            throw new Error("Scene root is missing.");
        }

        const selected = nodes.filter(node =>
            projected.has(String(node.id))
        );

        if (selected.length !== projected.size) {
            throw new Error(
                "Saved scene does not match the physical inventory."
            );
        }

        const seen = new Set();

        const scopedNodes = selected.map(node => {
            const id = String(node.id);

            if (seen.has(id)) {
                throw new Error("Duplicate physical location.");
            }

            seen.add(id);

            const meta = projected.get(id);

            if (id !== rootId &&
                !projected.has(String(node.parent))) {
                throw new Error(
                    "Saved scene contains an incomplete hierarchy."
                );
            }

            return {
                ...node,

                // The selected root becomes the top of this view.
                // The database parent is never changed.
                parent: id === rootId ? null : node.parent,

                // Metadata reserved for configurable geometries.
                geometryProfile: meta.geometry_profile || "generic"
            };
        });

        const scopedSamples = samples.filter(sample =>
            projected.has(String(sample.box))
        );

        return {
            nodes: scopedNodes,
            samples: scopedSamples,
            rootId,
            applied: true
        };
    }

    const api = Object.freeze({scope});

    if (typeof window !== "undefined") {
        window.B3StorageSceneFilterV8 = api;
    }

    if (typeof module !== "undefined" && module.exports) {
        module.exports = api;
    }
})();
