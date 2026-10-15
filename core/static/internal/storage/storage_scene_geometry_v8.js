/*
 * B3 LIMS V8 — generic spatial geometry planner.
 *
 * Pure data transformation.
 * Physical identity is never inferred from geometry.
 * Empty positions and equipment capacities are never invented.
 */
(() => {
    "use strict";

    const profiles = new Set([
        "space",
        "cabinet",
        "shelves",
        "rack",
        "grid",
        "generic"
    ]);

    function profile(node) {
        const value = String(
            node.geometryProfile || "generic"
        ).toLowerCase();

        return profiles.has(value) ? value : "generic";
    }

    function plan(nodes, selected = null, limit = 12) {
        if (!Array.isArray(nodes)) {
            throw new Error("Invalid scene nodes.");
        }

        if (!nodes.length) {
            return null;
        }

        if (
            !Number.isInteger(limit) ||
            limit < 1 ||
            limit > 100
        ) {
            throw new Error("Invalid scene display limit.");
        }

        const map = new Map();

        for (const node of nodes) {
            const id = String(node.id);

            if (map.has(id)) {
                throw new Error("Duplicate scene node.");
            }

            map.set(id, node);
        }

        const roots = nodes.filter(node =>
            node.parent == null ||
            !map.has(String(node.parent))
        );

        if (roots.length !== 1) {
            throw new Error(
                "The scene must have exactly one root."
            );
        }

        const root = roots[0];
        const id = selected == null
            ? String(root.id)
            : String(selected);

        const node = map.get(id);

        if (!node) {
            throw new Error(
                "Selected location is outside this scene."
            );
        }

        const descendants = nodes
            .filter(item =>
                String(item.parent) === id
            )
            .sort((a, b) =>
                Number(a.rank || 0) -
                Number(b.rank || 0) ||
                String(a.name).localeCompare(
                    String(b.name),
                    undefined,
                    {numeric: true}
                )
            );

        return {
            rootId: String(root.id),
            node,
            profile: profile(node),
            children: descendants.slice(0, limit).map(
                child => ({
                    node: child,
                    profile: profile(child)
                })
            ),
            totalChildren: descendants.length,
            hiddenChildren: Math.max(
                0,
                descendants.length - limit
            ),
            schematic: true,
            capacityKnown: false
        };
    }

    const api = Object.freeze({
        plan,
        profile
    });

    if (typeof window !== "undefined") {
        window.B3StorageSceneGeometryV8 = api;
    }

    if (
        typeof module !== "undefined" &&
        module.exports
    ) {
        module.exports = api;
    }
})();
