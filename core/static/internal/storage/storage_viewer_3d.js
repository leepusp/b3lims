/* B3 LIMS Storage Cutaway v3 — read-only; demo is never sent to Django. */
(() => {
    "use strict";

    const $ = id => document.getElementById(id);
    const source = $("storage-explorer-data");
    const canvas = $("storage-3d-canvas");
    if (!source || !canvas) return;

    const status = $("storage-3d-status");
    const listing = $("storage-3d-objects");
    const crumbs = $("storage-3d-breadcrumbs");
    const selectionText = $("storage-3d-selection");
    const exampleNotice = $("storage-3d-example-notice");
    const realButton = $("storage-3d-real");
    const demoButton = $("storage-3d-example");
    const backButton = $("storage-3d-back");
    const homeButton = $("storage-3d-home");
    const spinButton = $("storage-3d-spin");
    const ghostButton = $("storage-3d-ghost");
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;

    function parseLocation(node) {
        return {
            id: node.dataset.locationId,
            parent: node.dataset.parentId || null,
            name: node.dataset.locationName || "Unnamed location",
            kind: (node.dataset.locationKind || node.dataset.locationType || "").toLowerCase(),
            type: node.dataset.locationType || "Location",
            path: node.dataset.locationPath || node.dataset.locationName || "",
            rank: Number(node.dataset.locationRank || 0),
            active: node.dataset.locationActive !== "0"
        };
    }

    const live = {
        nodes: Array.from(source.content.querySelectorAll("[data-location-id]"), parseLocation),
        samples: Array.from(source.content.querySelectorAll("[data-assignment-location]"), element => ({
            box: element.dataset.assignmentLocation,
            code: element.dataset.assignmentSample || "Sample",
            position: element.dataset.assignmentPosition || "",
            status: element.dataset.assignmentStatus || "active"
        }))
    };
    const demo = {
        nodes: [
            ["demo-room", null, "Example Laboratory", "room"],
            ["demo-freezer", "demo-room", "Freezer 02 · −80 °C (example)", "freezer"],
            ["demo-rack-a", "demo-freezer", "Rack A", "rack"],
            ["demo-rack-b", "demo-freezer", "Rack B", "rack"],
            ["demo-box-1", "demo-rack-a", "Plasma Box A1", "box"],
            ["demo-box-2", "demo-rack-a", "PBMC Box A2", "box"],
            ["demo-box-3", "demo-rack-b", "DNA Box B1", "box"]
        ].map(([id, parent, name, kind], rank) => ({id, parent, name, kind, type: kind, path: name, rank, active: true})),
        samples: [
            {box: "demo-box-1", code: "EX-PLA-001", position: "A01", status: "active"},
            {box: "demo-box-1", code: "EX-PLA-002", position: "B03", status: "active"},
            {box: "demo-box-1", code: "EX-PLA-003", position: "H09", status: "active"},
            {box: "demo-box-2", code: "EX-PBM-004", position: "C04", status: "active"},
            {box: "demo-box-3", code: "EX-DNA-005", position: "D05", status: "active"}
        ]
    };

    // Historical locations are projected only from authorized Samples.
    // They are visual, not registered infrastructure or movement targets.
    const historicalData = $("storage-legacy-projection");

    if (historicalData) {
        try {
            const projection = JSON.parse(
                historicalData.textContent || "{}"
            );

            if (
                Array.isArray(projection.nodes)
                && Array.isArray(projection.samples)
            ) {
                live.nodes.push(...projection.nodes);
                live.samples.push(...projection.samples);
            }
        } catch (error) {
            console.error(
                "Unable to read historical storage projection",
                error
            );
        }
    }

    let mode = "live";
    let selected = null;
    let model, map, children;
    let THREE, renderer, scene, camera, world, raycaster;
    let pickables = [], animations = [], frame = 0;
    let yaw = 0.72, pitch = 1.03, distance = 9.0, wantedDistance = 9.0;
    let cameraTarget, wantedTarget, spinning = false, ghost = true;
    let pointer = null;

    const semantic = kind => {
        if (/room|sala/.test(kind)) return "room";
        if (/freezer|fridge|refrigerator|equipment|equipamento|cabinet/.test(kind)) return "equipment";
        if (/rack|shelf|basket|gaveta|drawer|prateleira|cesto/.test(kind)) return "rack";
        if (/box|caixa|container|vialbox/.test(kind)) return "box";
        return "other";
    };

    function loadModel() {
        model = mode === "demo" ? demo : live;
        map = new Map(model.nodes.map(node => [node.id, node]));
        children = new Map();
        for (const node of model.nodes) {
            const parent = node.parent && map.has(node.parent) ? node.parent : null;
            const group = children.get(parent) || [];
            group.push(node);
            children.set(parent, group);
        }
        for (const group of children.values()) {
            group.sort((a, b) => a.rank - b.rank || a.name.localeCompare(b.name, undefined, {numeric: true}));
        }
        selected = null;
        realButton.className = `btn btn-sm ${mode === "live" ? "btn-primary" : "btn-outline-secondary"}`;
        demoButton.className = `btn btn-sm ${mode === "demo" ? "btn-primary" : "btn-outline-secondary"}`;
        realButton.setAttribute("aria-pressed", String(mode === "live"));
        demoButton.setAttribute("aria-pressed", String(mode === "demo"));
        exampleNotice.hidden = mode !== "demo";
        update();
    }

    function ancestry(id) {
        const chain = [], visited = new Set();
        let node = map.get(id);
        while (node && !visited.has(node.id)) {
            visited.add(node.id);
            chain.unshift(node);
            node = node.parent ? map.get(node.parent) : null;
        }
        return chain;
    }

    function isDescendant(id, ancestor) {
        if (!ancestor) return true;
        return ancestry(id).some(node => node.id === ancestor);
    }

    function select(id, emit = true) {
        selected = id && map.has(String(id)) ? String(id) : null;
        if (emit && mode === "live") {
            const node = selected ? map.get(selected) : null;

            if (node?.legacy) {
                // Historical nodes must never become Django location IDs.
                // Keep the 3D selection without triggering a 2D reset.
                document.dispatchEvent(
                    new CustomEvent(
                        "b3-storage-legacy-selected",
                        {detail: {id: selected}}
                    )
                );
            } else {
                document.dispatchEvent(
                    new CustomEvent(
                        "b3-storage-select-request",
                        {detail: {id: selected}}
                    )
                );
            }
        }
        update();
    }

    function button(label, parent, callback, className = "") {
        const element = document.createElement("button");
        element.type = "button";
        element.textContent = label;
        element.className = className;
        element.addEventListener("click", callback);
        parent.append(element);
        return element;
    }

    function updateControls() {
        crumbs.replaceChildren();
        listing.replaceChildren();
        button("Overview", crumbs, () => select(null));
        for (const node of ancestry(selected)) {
            button(node.name, crumbs, () => select(node.id));
        }
        const items = children.get(selected) || [];
        for (const node of items) {
            button(`${node.name} · ${node.type}${node.active ? "" : " · inactive"}`, listing, () => select(node.id));
        }
        if (!items.length) {
            const message = document.createElement("p");
            message.className = "small text-muted";
            message.textContent = selected ? "No child locations." : "No storage locations registered.";
            listing.append(message);
        }
        backButton.disabled = selected === null;
        selectionText.textContent = selected ? (map.get(selected)?.path || map.get(selected)?.name) : "Storage overview";
    }

    function makeMesh(geometry, color, opacity = 1, id = null, materialOptions = {}) {
        const mat = new THREE.MeshStandardMaterial({
            color, roughness: 0.65, metalness: 0.09,
            transparent: opacity < 1, opacity,
            depthWrite: opacity === 1,
            side: THREE.DoubleSide, ...materialOptions
        });
        const mesh = new THREE.Mesh(geometry, mat);
        if (id) {
            mesh.userData.pickId = id;
            pickables.push(mesh);
        }
        return mesh;
    }

    function cuboid(group, w, h, d, x, y, z, color, opacity = 1, id = null) {
        const mesh = makeMesh(new THREE.BoxGeometry(w, h, d), color, opacity, id);
        mesh.position.set(x, y, z);
        group.add(mesh);
        return mesh;
    }

    function border(group, w, h, d, x, y, z, color = 0x6b8998) {
        const edges = new THREE.LineSegments(
            new THREE.EdgesGeometry(new THREE.BoxGeometry(w, h, d)),
            new THREE.LineBasicMaterial({color, transparent: true, opacity: 0.7})
        );
        edges.position.set(x, y, z);
        group.add(edges);
    }

    function disposal() {
        if (!world) return;
        world.traverse(object => {
            if (object.geometry) object.geometry.dispose();
            if (object.material) {
                for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
                    material.dispose();
                }
            }
        });
        scene.remove(world);
        world = null;
        pickables = [];
        animations = [];
    }

    function buildBox(group, box, y, rack, rackX, emphasize) {
        const b = new THREE.Group();
        b.position.set(rackX, y, 0.04);
        group.add(b);
        cuboid(b, .83, .30, .85, 0, 0, 0, 0xe5f0f2, .64, box.id);
        border(b, .83, .30, .85, 0, 0, 0);
        const lid = cuboid(b, .86, .038, .88, 0, .17, 0, 0x709aaa, .92, box.id);
        const content = model.samples.filter(sample => sample.box === box.id && sample.status === "active");
        if (selected === box.id) {
            const tubeGeometry = new THREE.CylinderGeometry(.033, .029, .20, 12);
            const assignments = content.slice(0, 250);
            const demoSlots = mode === "demo";
            // Only place tubes whose recorded coordinates are interpretable.
            // Unpositioned assignments are never assigned fictional coordinates.
            const positions = assignments.flatMap(sample => {
                const match = /^([A-Z])(\d{1,2})$/i.exec(sample.position.trim());
                if (!match) return [];
                const row = match[1].toUpperCase().charCodeAt(0) - 65;
                const col = Number(match[2]) - 1;
                return row >= 0 && row <= 25 && col >= 0 && col <= 25
                    ? [{...sample, row, col}] : [];
            });
            const maxRow = Math.max(...positions.map(item => item.row), demoSlots ? 8 : 0);
            const maxCol = Math.max(...positions.map(item => item.col), demoSlots ? 8 : 0);
            const cols = maxCol + 1, rows = maxRow + 1;
            const scale = .68 / Math.max(cols, rows, 1);
            const tubeMaterial = new THREE.MeshStandardMaterial({color: 0x2c9fae, metalness: 0.15, roughness: .35});
            const instanced = new THREE.InstancedMesh(tubeGeometry, tubeMaterial, positions.length);
            const dummy = new THREE.Object3D();
            for (let i = 0; i < positions.length; i++) {
                const item = positions[i];
                dummy.position.set((item.col - (cols - 1) / 2) * scale, .18, (item.row - (rows - 1) / 2) * scale);
                dummy.scale.setScalar(Math.max(.3, Math.min(1, scale / .085)));
                dummy.updateMatrix();
                instanced.setMatrixAt(i, dummy.matrix);
            }
            if (positions.length) {
                instanced.instanceMatrix.needsUpdate = true;
                b.add(instanced);
            } else {
                tubeGeometry.dispose();
                tubeMaterial.dispose();
            }
            animations.push({object: lid, from: .17, to: .63, axis: "y"});
            animations.push({object: b, from: .04, to: 1.18, axis: "z"});
            animations.push({object: b, fromY: y, toY: y + .42, axis: "y"});
        }
        if (emphasize) {
            // Individual boxes are highlighted only when a rack or box is selected.
            lid.material.color.setHex(0x248e9d);
        }
    }

    function buildFreezer(equipment, x, focus) {
        const equipmentChildren = children.get(equipment.id) || [];
        const directBoxes = equipmentChildren.filter(
            item => semantic(item.kind) === "box"
        );
        const registeredRacks = equipmentChildren.filter(
            item => semantic(item.kind) === "rack"
        );

        // Visual shelf for legacy boxes lacking a registered rack.
        // This is NOT a StorageLocation and is never persisted.
        const displayShelf = directBoxes.length ? [{
            id: equipment.id,
            virtual: true
        }] : [];

        const racks = [...registeredRacks, ...displayShelf];
        const shownRacks = racks.slice(0, 5);
        const nRacks = Math.max(shownRacks.length, 1);
        const maxBoxes = Math.max(3, ...shownRacks.map(rack => (children.get(rack.id) || []).length));
        const height = Math.max(2.4, maxBoxes * .44 + .55);
        const width = Math.max(1.8, nRacks * 1.04 + .45);
        const shell = new THREE.Group();
        shell.position.set(x, 0, 0);
        world.add(shell);
        const opacity = ghost ? .16 : .72;
        // Cutaway front is open: side panels + back, never a solid opaque cube.
        cuboid(shell, width, .08, 1.3, 0, height, 0, 0x819aa6, .9);
        cuboid(shell, width, .12, 1.3, 0, 0, 0, 0x7e98a5, .9);
        cuboid(shell, .07, height, 1.3, -width / 2, height / 2, 0, 0x8eabb8, opacity);
        cuboid(shell, .07, height, 1.3, width / 2, height / 2, 0, 0x8eabb8, opacity);
        cuboid(shell, width, height, .05, 0, height / 2, -.64, 0xc7d7df, opacity);
        border(shell, width, height, 1.3, 0, height / 2, 0);
        // A transparent cabinet with an explicit, selectable nameplate.
        cuboid(shell, Math.min(width * .5, 1.0), .12, .035, 0, height + .13, .67, 0x1e7081, 1, equipment.id);
        shownRacks.forEach((rack, index) => {
            const rackX = (index - (nRacks - 1) / 2) * 1.04;
            const rackGroup = new THREE.Group();
            rackGroup.position.set(0, 0, 0);
            shell.add(rackGroup);
            const rackBoxes = (
                rack.virtual
                    ? directBoxes
                    : (children.get(rack.id) || []).filter(
                        node => semantic(node.kind) === "box"
                    )
            ).slice(0, 12);

            const rackPick = rack.virtual
                ? equipment.id
                : rack.id;
            const levels = Math.max(3, rackBoxes.length);
            cuboid(rackGroup, .028, levels * .45 + .18, .91, rackX - .44, levels * .225 + .19, 0, 0x718c98, 1, rackPick);
            cuboid(rackGroup, .028, levels * .45 + .18, .91, rackX + .44, levels * .225 + .19, 0, 0x718c98, 1, rackPick);
            for (let row = 0; row < levels; row++) {
                cuboid(rackGroup, .91, .03, .95, rackX, .27 + row * .45, 0, 0x9aafb8, 1, rackPick);
            }
            rackBoxes.forEach((box, row) => {
                buildBox(rackGroup, box, .49 + row * .45, rack, rackX, selected === rack.id || selected === box.id);
            });
            if (focus.some(node => node.id === rack.id)) {
                animations.push({object: rackGroup, from: 0, to: .58, axis: "z"});
            }
        });
        return {height, width, shell};
    }

    function sceneContent() {
        if (!renderer) return;
        disposal();
        world = new THREE.Group();
        scene.add(world);
        cuboid(world, 14, .12, 11, 0, -.12, 0, 0xd4dfe4, 1);
        const focus = ancestry(selected);
        const nearestEquipment = focus.slice().reverse().find(node => semantic(node.kind) === "equipment");
        let equipment = model.nodes.filter(node => semantic(node.kind) === "equipment");
        if (nearestEquipment) {
            equipment = [nearestEquipment];
        } else if (selected) {
            equipment = equipment.filter(node => isDescendant(node.id, selected));
        }
        equipment = equipment.slice(0, 6);
        const spacing = 2.6;
        equipment.forEach((item, index) => {
            buildFreezer(item, (index - (equipment.length - 1) / 2) * spacing, focus);
        });
        wantedDistance = Math.max(5.5, equipment.length * 2.5 + 2.8);
        if (selected && nearestEquipment) wantedDistance = 5.7;
        if (focus.some(node => semantic(node.kind) === "box")) wantedDistance = 3.5;
        wantedTarget.set(0, selected ? 1.2 : 1.0, selected ? .52 : 0);
        const details = focus.at(-1);
        const box = focus.some(node => semantic(node.kind) === "box");
        const sampleCount = box ? model.samples.filter(s => s.box === selected && s.status === "active").length : null;
        if (!equipment.length) {
            status.textContent = mode === "live"
                ? "No freezers are registered under this location. Choose Explore example to inspect the design without adding inventory."
                : "This example contains no equipment.";
        } else if (box) {
            status.textContent = `${details?.name || "Box"}: ${sampleCount} recorded sample(s). Positions shown are recorded assignments only; free capacity is unknown.`;
        } else {
            status.textContent = `${equipment.length} ${equipment.length === 1 ? "equipment model" : "equipment models"} · schematic cutaway · click a rack or box to enter.`;
        }
    }

    function update() {
        updateControls();
        sceneContent();
    }

    function resize() {
        if (!renderer) return;
        const width = Math.max(2, canvas.clientWidth);
        const height = Math.max(2, canvas.clientHeight);
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
    }

    let prev = performance.now();
    function animate(now) {
        const dt = Math.min(.05, (now - prev) / 1000 || .016);
        prev = now;
        if (spinning && !reduceMotion) yaw += dt * .23;
        const factor = reduceMotion ? 1 : Math.min(1, dt * 5);
        distance += (wantedDistance - distance) * factor;
        cameraTarget.lerp(wantedTarget, factor);
        for (const anim of animations) {
            if (anim.fromY !== undefined) {
                anim.object.position.y += (anim.toY - anim.object.position.y) * factor;
            } else {
                anim.object.position[anim.axis] += (anim.to - anim.object.position[anim.axis]) * factor;
            }
        }
        camera.position.set(
            cameraTarget.x + distance * Math.sin(pitch) * Math.sin(yaw),
            cameraTarget.y + distance * Math.cos(pitch),
            cameraTarget.z + distance * Math.sin(pitch) * Math.cos(yaw)
        );
        camera.lookAt(cameraTarget);
        renderer.render(scene, camera);
        frame = requestAnimationFrame(animate);
    }

    async function start() {
        try {
            THREE = await import("../../vendor/three/0.182.0/three.module.js");
            renderer = new THREE.WebGLRenderer({canvas, alpha: true, antialias: true});
            renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
            renderer.setClearColor(0xe3ebef, 0);
            scene = new THREE.Scene();
            camera = new THREE.PerspectiveCamera(42, 1, .1, 120);
            cameraTarget = new THREE.Vector3(0, 1, 0);
            wantedTarget = cameraTarget.clone();
            raycaster = new THREE.Raycaster();
            scene.add(new THREE.HemisphereLight(0xffffff, 0x8297a1, 2.1));
            const lamp = new THREE.DirectionalLight(0xffffff, 1.9);
            lamp.position.set(6, 9, 7);
            scene.add(lamp);
            resize();
            loadModel();
            frame = requestAnimationFrame(animate);
        } catch (error) {
            status.textContent = "WebGL unavailable. Storage inventory and movement forms remain accessible below.";
            console.error("Storage cutaway initialization failed:", error);
        }
    }

    realButton.addEventListener("click", () => {mode = "live"; loadModel();});
    demoButton.addEventListener("click", () => {mode = "demo"; loadModel();});
    backButton.addEventListener("click", () => select(selected ? map.get(selected)?.parent : null));
    homeButton.addEventListener("click", () => select(null));
    spinButton.addEventListener("click", () => {
        spinning = !spinning;
        spinButton.setAttribute("aria-pressed", String(spinning));
    });
    ghostButton.addEventListener("click", () => {
        ghost = !ghost;
        ghostButton.setAttribute("aria-pressed", String(ghost));
        sceneContent();
    });
    document.addEventListener("b3-storage-location-selected", event => {
        if (mode === "live") {
            const id = event.detail?.id;
            selected = id && map.has(String(id)) ? String(id) : null;
            update();
        }
    });
    canvas.addEventListener("pointerdown", event => {
        pointer = {x: event.clientX, y: event.clientY, moved: 0};
        canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", event => {
        if (!pointer) return;
        const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y;
        pointer.moved += Math.abs(dx) + Math.abs(dy);
        yaw -= dx * .008;
        pitch = Math.max(.18, Math.min(1.52, pitch - dy * .006));
        pointer.x = event.clientX;
        pointer.y = event.clientY;
    });
    canvas.addEventListener("pointerup", event => {
        if (!pointer) return;
        const click = pointer.moved < 7;
        pointer = null;
        if (!click || !renderer) return;
        const rect = canvas.getBoundingClientRect();
        const coordinate = new THREE.Vector2(
            2 * (event.clientX - rect.left) / rect.width - 1,
            1 - 2 * (event.clientY - rect.top) / rect.height
        );
        raycaster.setFromCamera(coordinate, camera);
        const hits = raycaster.intersectObjects(pickables, false);
        const hit = hits.find(item => item.object.userData.pickId)?.object.userData.pickId;
        if (hit) select(hit);
        else if (selected) select(map.get(selected)?.parent || null);
    });
    canvas.addEventListener("pointercancel", () => {pointer = null;});
    canvas.addEventListener("wheel", event => {
        event.preventDefault();
        wantedDistance = Math.max(2.3, Math.min(24, wantedDistance + Math.sign(event.deltaY) * .35));
    }, {passive: false});
    window.addEventListener("resize", resize);
    start();
})();
