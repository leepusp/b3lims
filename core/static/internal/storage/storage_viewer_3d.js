(() => {
    "use strict";

    const panel = document.getElementById("storage-3d-details");
    const source = document.getElementById("storage-explorer-data");

    if (!panel || !source) return;

    const canvas = document.getElementById("storage-3d-canvas");
    const status = document.getElementById("storage-3d-status");
    const path = document.getElementById("storage-3d-path");
    const objects = document.getElementById("storage-3d-objects");
    const previous = document.getElementById("storage-3d-prev");
    const next = document.getElementById("storage-3d-next");
    const pageLabel = document.getElementById("storage-3d-page");

    const locations = Array.from(
        source.content.querySelectorAll("[data-location-id]")
    ).map(node => ({
        id: node.dataset.locationId,
        parent: node.dataset.parentId || null,
        name: node.dataset.locationName,
        kind: node.dataset.locationKind || "",
        type: node.dataset.locationType || "Location",
        path: node.dataset.locationPath || node.dataset.locationName,
        rank: Number(node.dataset.locationRank || 0)
    }));

    const byId = new Map(locations.map(x => [x.id, x]));
    const children = new Map();

    for (const location of locations) {
        const parent = location.parent && byId.has(location.parent)
            ? location.parent : null;
        const key = parent || "";

        if (!children.has(key)) children.set(key, []);
        children.get(key).push(location);
    }

    for (const group of children.values()) {
        group.sort((a, b) =>
            a.rank - b.rank ||
            a.name.localeCompare(b.name, undefined, {
                numeric: true,
                sensitivity: "base"
            })
        );
    }

    const PAGE_SIZE = 18;

    let selected = null;
    let page = 0;
    let THREE = null;
    let renderer = null;
    let scene = null;
    let camera = null;
    let group = null;
    let picks = [];
    let frame = 0;
    let yaw = 0.65;
    let pitch = 0.95;
    let distance = 10;

    function choose(id) {
        selected = id && byId.has(String(id))
            ? String(id) : null;
        page = 0;

        document.dispatchEvent(new CustomEvent(
            "b3-storage-select-request",
            { detail: { id: selected } }
        ));

        if (renderer) draw();
    }

    function dimensions(kind) {
        const value = kind.toLowerCase();

        if (/freezer|fridge|refrigerator/.test(value)) {
            return [1.45, 2.2, 1.2, 0x6c99ad];
        }
        if (/rack|shelf|basket/.test(value)) {
            return [1.1, 1.65, 0.85, 0x8ba3ad];
        }
        if (/box|container/.test(value)) {
            return [1.25, 0.4, 1.0, 0x6cb7c6];
        }
        if (/room/.test(value)) {
            return [1.7, 0.2, 1.45, 0xa1b7c2];
        }
        return [1.15, 0.8, 1.0, 0x91a9b6];
    }

    function disposeGroup() {
        if (!group) return;

        group.traverse(object => {
            if (object.geometry) object.geometry.dispose();

            if (object.material) {
                const materials = Array.isArray(object.material)
                    ? object.material : [object.material];

                materials.forEach(material => material.dispose());
            }
        });

        scene.remove(group);
        picks = [];
    }

    function resize() {
        if (!renderer) return;

        const width = Math.max(1, canvas.clientWidth);
        const height = Math.max(1, canvas.clientHeight);

        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
    }

    function draw() {
        if (!renderer) return;

        disposeGroup();
        group = new THREE.Group();
        scene.add(group);

        const current = selected ? byId.get(selected) : null;
        const entries = children.get(selected || "") || [];

        const pages = Math.max(
            1, Math.ceil(entries.length / PAGE_SIZE)
        );
        page = Math.min(page, pages - 1);

        const visible = entries.slice(
            page * PAGE_SIZE,
            (page + 1) * PAGE_SIZE
        );

        // A leaf is shown alone, rather than inventing its contents.
        const items = visible.length
            ? visible
            : entries.length
                ? []
                : current
                    ? [current]
                    : [];

        const columns = Math.max(
            1, Math.ceil(Math.sqrt(items.length))
        );
        const rows = Math.max(
            1, Math.ceil(items.length / columns)
        );

        items.forEach((item, index) => {
            const [w, h, d, color] = dimensions(
                item.kind || item.type
            );

            const geometry = new THREE.BoxGeometry(w, h, d);
            const material = new THREE.MeshStandardMaterial({
                color,
                roughness: 0.64,
                metalness: 0.12,
                transparent: true,
                opacity: 0.82
            });

            const mesh = new THREE.Mesh(geometry, material);

            const column = index % columns;
            const row = Math.floor(index / columns);

            mesh.position.set(
                (column - (columns - 1) / 2) * 2.5,
                h / 2,
                (row - (rows - 1) / 2) * 2.5
            );

            mesh.userData.locationId = item.id;
            group.add(mesh);
            picks.push(mesh);

            const outline = new THREE.LineSegments(
                new THREE.EdgesGeometry(geometry),
                new THREE.LineBasicMaterial({
                    color: 0x354e5a
                })
            );
            outline.position.copy(mesh.position);
            group.add(outline);
        });

        const floor = new THREE.Mesh(
            new THREE.PlaneGeometry(
                Math.max(4, columns * 2.7),
                Math.max(4, rows * 2.7)
            ),
            new THREE.MeshStandardMaterial({
                color: 0xdde6eb,
                roughness: 1
            })
        );

        floor.rotation.x = -Math.PI / 2;
        floor.position.y = -0.05;
        group.add(floor);

        distance = Math.max(
            5, Math.max(columns, rows) * 2.7 + 3
        );

        path.textContent = current
            ? current.path : "Storage overview";

        pageLabel.textContent =
            `Page ${page + 1} of ${pages}`;

        previous.disabled = page === 0;
        next.disabled = page >= pages - 1;

        objects.replaceChildren();

        for (const item of visible) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-sm btn-outline-secondary";
            button.textContent = `${item.name} · ${item.type}`;
            button.addEventListener("click", () => choose(item.id));
            objects.append(button);
        }

        if (!entries.length) {
            const message = document.createElement("p");
            message.className = "small text-muted mb-0";
            message.textContent = current
                ? "No child locations. Inspect recorded positions in the 2D explorer."
                : "No visible storage locations.";
            objects.append(message);
        }

        status.textContent =
            `${entries.length} child location(s). ` +
            "Schematic geometry; no inventory changes.";
    }

    function animate() {
        if (!panel.open || !renderer) {
            frame = 0;
            return;
        }

        camera.position.set(
            distance * Math.sin(pitch) * Math.sin(yaw),
            distance * Math.cos(pitch),
            distance * Math.sin(pitch) * Math.cos(yaw)
        );

        camera.lookAt(0, 0.75, 0);
        renderer.render(scene, camera);

        frame = requestAnimationFrame(animate);
    }

    async function initialize() {
        if (renderer) {
            resize();
            if (!frame) animate();
            return;
        }

        status.textContent = "Loading 3D viewer...";

        try {
            THREE = await import(
                "../../vendor/three/0.182.0/three.module.js"
            );

            if (!panel.open) return;

            renderer = new THREE.WebGLRenderer({
                canvas,
                antialias: true,
                alpha: true
            });

            renderer.setPixelRatio(
                Math.min(window.devicePixelRatio || 1, 1.5)
            );

            scene = new THREE.Scene();
            camera = new THREE.PerspectiveCamera(
                42, 1, 0.1, 200
            );

            scene.add(new THREE.HemisphereLight(
                0xffffff, 0x64748b, 2.0
            ));

            const light = new THREE.DirectionalLight(
                0xffffff, 1.8
            );

            light.position.set(4, 8, 6);
            scene.add(light);

            resize();
            draw();
            animate();
        } catch (error) {
            status.textContent =
                "3D viewer unavailable. The 2D inventory remains accessible.";
            console.error("Storage 3D initialization:", error);
        }
    }

    let pointer = null;
    const raycaster = { value: null };

    canvas.addEventListener("pointerdown", event => {
        pointer = {
            x: event.clientX,
            y: event.clientY,
            moved: 0
        };
        canvas.setPointerCapture(event.pointerId);
    });

    canvas.addEventListener("pointermove", event => {
        if (!pointer) return;

        const dx = event.clientX - pointer.x;
        const dy = event.clientY - pointer.y;

        pointer.moved += Math.abs(dx) + Math.abs(dy);

        yaw -= dx * 0.008;
        pitch = Math.min(
            1.5, Math.max(0.18, pitch - dy * 0.006)
        );

        pointer.x = event.clientX;
        pointer.y = event.clientY;
    });

    canvas.addEventListener("pointerup", event => {
        if (!pointer) return;

        const clicked = pointer.moved < 6;
        pointer = null;

        if (!clicked || !renderer) return;

        const rect = canvas.getBoundingClientRect();

        const coordinates = new THREE.Vector2(
            ((event.clientX - rect.left) / rect.width) * 2 - 1,
            -((event.clientY - rect.top) / rect.height) * 2 + 1
        );

        if (!raycaster.value) {
            raycaster.value = new THREE.Raycaster();
        }

        raycaster.value.setFromCamera(coordinates, camera);

        const hits = raycaster.value.intersectObjects(
            picks, false
        );

        if (hits.length) {
            choose(hits[0].object.userData.locationId);
        } else if (selected) {
            const current = byId.get(selected);
            choose(current?.parent || null);
        }
    });

    canvas.addEventListener("wheel", event => {
        event.preventDefault();
        distance = Math.max(
            3, Math.min(45, distance + Math.sign(event.deltaY))
        );
    }, { passive: false });

    previous.addEventListener("click", () => {
        if (page > 0) {
            page--;
            draw();
        }
    });

    next.addEventListener("click", () => {
        page++;
        draw();
    });

    document.getElementById("storage-3d-back")
        .addEventListener("click", () => {
            const current = selected
                ? byId.get(selected) : null;
            choose(current?.parent || null);
        });

    document.getElementById("storage-3d-home")
        .addEventListener("click", () => choose(null));

    document.addEventListener(
        "b3-storage-location-selected",
        event => {
            const id = event.detail?.id;
            selected = id && byId.has(String(id))
                ? String(id) : null;
            page = 0;
            if (renderer) draw();
        }
    );

    panel.addEventListener("toggle", () => {
        if (panel.open) {
            initialize();
        } else if (frame) {
            cancelAnimationFrame(frame);
            frame = 0;
        }
    });

    window.addEventListener("resize", resize);
})();
