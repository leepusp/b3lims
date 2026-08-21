(() => {
    "use strict";

    const nodesElement =
        document.getElementById(
            "sample-network-nodes-json"
        );

    const edgesElement =
        document.getElementById(
            "sample-network-edges-json"
        );

    const container =
        document.getElementById(
            "network-container"
        );

    if (
        !nodesElement
        || !edgesElement
        || !container
        || typeof vis === "undefined"
    ) {
        return;
    }

    const nodes = JSON.parse(
        nodesElement.textContent
    );

    const edges = JSON.parse(
        edgesElement.textContent
    );

    const rawNodes =
        new vis.DataSet(
            nodes
        );

    const rawEdges =
        new vis.DataSet(
            edges
        );


    const state = {
        search: "",
        sampleType: "",
        status: "",
        biosafety: "",
        owner: "",
        biobank: "",
        researchGroup: "",
        collection: "",
        connectedOnly: false,
        relationships: {
            lineage: true,
            storage: true,
            infection: true,
            other: true,
        },
    };


    const controls = {
        search:
            document.getElementById(
                "network-filter-search"
            ),
        sampleType:
            document.getElementById(
                "network-filter-type"
            ),
        status:
            document.getElementById(
                "network-filter-status"
            ),
        biosafety:
            document.getElementById(
                "network-filter-biosafety"
            ),
        owner:
            document.getElementById(
                "network-filter-owner"
            ),
        biobank:
            document.getElementById(
                "network-filter-biobank"
            ),
        researchGroup:
            document.getElementById(
                "network-filter-group"
            ),
        collection:
            document.getElementById(
                "network-filter-collection"
            ),
        connectedOnly:
            document.getElementById(
                "network-connected-only"
            ),
        edgeLineage:
            document.getElementById(
                "network-edge-lineage"
            ),
        edgeStorage:
            document.getElementById(
                "network-edge-storage"
            ),
        edgeInfection:
            document.getElementById(
                "network-edge-infection"
            ),
        edgeOther:
            document.getElementById(
                "network-edge-other"
            ),
        resetFilters:
            document.getElementById(
                "network-reset-filters"
            ),
        layout:
            document.getElementById(
                "network-layout"
            ),
        clusterBy:
            document.getElementById(
                "network-cluster-by"
            ),
        fit:
            document.getElementById(
                "network-fit"
            ),
        resetView:
            document.getElementById(
                "network-reset-view"
            ),
        inspector:
            document.getElementById(
                "network-inspector"
            ),
    };


    function normalize(value) {
        return String(
            value || ""
        )
            .trim()
            .toLocaleLowerCase();
    }


    function populateSelect(
        element,
        values
    ) {
        if (!element) {
            return;
        }

        const unique =
            Array.from(
                new Set(
                    values
                    .filter(
                        (value) => (
                            String(
                                value || ""
                            ).trim()
                        )
                    )
                )
            )
            .sort(
                (left, right) => (
                    String(left)
                    .localeCompare(
                        String(right)
                    )
                )
            );

        unique.forEach(
            (value) => {
                const option =
                    document.createElement(
                        "option"
                    );

                option.value =
                    String(value);

                option.textContent =
                    String(value);

                element.appendChild(
                    option
                );
            }
        );
    }


    populateSelect(
        controls.sampleType,
        nodes.map(
            (node) => node.sample_type
        )
    );

    populateSelect(
        controls.status,
        nodes.map(
            (node) => node.status_label
        )
    );

    populateSelect(
        controls.biosafety,
        nodes.map(
            (node) => node.biosafety_level
        )
    );

    populateSelect(
        controls.owner,
        nodes.map(
            (node) => node.owner
        )
    );

    populateSelect(
        controls.biobank,
        nodes.map(
            (node) => node.biobank
        )
    );

    populateSelect(
        controls.researchGroup,
        nodes.map(
            (node) => node.research_group
        )
    );

    populateSelect(
        controls.collection,
        nodes.flatMap(
            (node) => (
                Array.isArray(
                    node.collections
                )
                    ? node.collections
                    : []
            )
        )
    );


    function relationshipEnabled(edge) {
        const category =
            edge.relationship_category
            || "other";

        return (
            state.relationships[
                category
            ] !== false
        );
    }


    function basicNodeMatches(node) {
        if (
            state.sampleType
            && node.sample_type
                !== state.sampleType
        ) {
            return false;
        }

        if (
            state.status
            && node.status_label
                !== state.status
        ) {
            return false;
        }

        if (
            state.biosafety
            && node.biosafety_level
                !== state.biosafety
        ) {
            return false;
        }

        if (
            state.owner
            && node.owner
                !== state.owner
        ) {
            return false;
        }

        if (
            state.biobank
            && node.biobank
                !== state.biobank
        ) {
            return false;
        }

        if (
            state.researchGroup
            && node.research_group
                !== state.researchGroup
        ) {
            return false;
        }

        if (state.collection) {
            const collections =
                Array.isArray(
                    node.collections
                )
                    ? node.collections
                    : [];

            if (
                !collections.includes(
                    state.collection
                )
            ) {
                return false;
            }
        }

        const term =
            normalize(
                state.search
            );

        if (term) {
            const searchable = [
                node.sample_id,
                node.organism_name,
                node.sample_type,
                node.owner,
                node.research_group,
                node.biobank,
                node.collections_text,
            ];

            const found =
                searchable.some(
                    (value) => (
                        normalize(
                            value
                        ).includes(
                            term
                        )
                    )
                );

            if (!found) {
                return false;
            }
        }

        return true;
    }


    function matchingNodeIdSet() {
        return new Set(
            rawNodes
            .get()
            .filter(
                basicNodeMatches
            )
            .map(
                (node) => node.id
            )
        );
    }


    function connectedNodeIdSet(
        candidateIds
    ) {
        const connected =
            new Set();

        rawEdges.get().forEach(
            (edge) => {
                if (
                    !relationshipEnabled(
                        edge
                    )
                ) {
                    return;
                }

                if (
                    candidateIds.has(
                        edge.from
                    )
                    && candidateIds.has(
                        edge.to
                    )
                ) {
                    connected.add(
                        edge.from
                    );

                    connected.add(
                        edge.to
                    );
                }
            }
        );

        return connected;
    }


    let currentVisibleNodeIds =
        matchingNodeIdSet();


    const nodesView =
        new vis.DataView(
            rawNodes,
            {
                filter(node) {
                    const candidateIds =
                        matchingNodeIdSet();

                    if (
                        !candidateIds.has(
                            node.id
                        )
                    ) {
                        return false;
                    }

                    if (
                        state.connectedOnly
                    ) {
                        return (
                            connectedNodeIdSet(
                                candidateIds
                            )
                            .has(
                                node.id
                            )
                        );
                    }

                    return true;
                },
            }
        );


    const edgesView =
        new vis.DataView(
            rawEdges,
            {
                filter(edge) {
                    return (
                        relationshipEnabled(
                            edge
                        )
                        && currentVisibleNodeIds
                            .has(
                                edge.from
                            )
                        && currentVisibleNodeIds
                            .has(
                                edge.to
                            )
                    );
                },
            }
        );


    const forceOptions = {
        layout: {
            hierarchical: {
                enabled: false,
            },
        },
        physics: {
            enabled: true,
            solver: "forceAtlas2Based",
            forceAtlas2Based: {
                gravitationalConstant: -55,
                centralGravity: 0.008,
                springLength: 125,
                springConstant: 0.075,
            },
            stabilization: {
                iterations: 180,
            },
        },
    };


    const options = {
        nodes: {
            shape: "dot",
            size: 20,
            borderWidth: 2,
            shadow: true,
            font: {
                size: 12,
                face: "system-ui",
                color: "#334155",
            },
        },
        groups: {
            bacteria: {
                color: {
                    background: "#198754",
                    border: "#146c43",
                },
            },
            phage: {
                color: {
                    background: "#dc3545",
                    border: "#b02a37",
                },
            },
            plasmid: {
                color: {
                    background: "#0dcaf0",
                    border: "#0891b2",
                },
            },
            generic: {
                color: {
                    background: "#64748b",
                    border: "#475569",
                },
            },
        },
        edges: {
            smooth: {
                type: "continuous",
            },
            color: {
                inherit: false,
                color: "#94a3b8",
            },
            width: 2,
            font: {
                size: 10,
                align: "middle",
                color: "#64748b",
            },
        },
        interaction: {
            hover: true,
            tooltipDelay: 250,
            navigationButtons: true,
            keyboard: true,
            multiselect: false,
        },
        ...forceOptions,
    };


    const network =
        new vis.Network(
            container,
            {
                nodes: nodesView,
                edges: edgesView,
            },
            options
        );


    function refreshViews(
        fit = false
    ) {
        const candidates =
            matchingNodeIdSet();

        currentVisibleNodeIds =
            state.connectedOnly
                ? connectedNodeIdSet(
                    candidates
                )
                : candidates;

        nodesView.refresh();
        edgesView.refresh();

        clearClusters();

        if (controls.clusterBy.value) {
            applyClustering(
                controls.clusterBy.value
            );
        }

        if (fit) {
            setTimeout(
                () => {
                    network.fit(
                        {
                            animation: {
                                duration: 350,
                            },
                        }
                    );
                },
                60
            );
        }
    }


    function bindSelect(
        element,
        stateKey
    ) {
        element.addEventListener(
            "change",
            () => {
                state[
                    stateKey
                ] = element.value;

                refreshViews(
                    true
                );
            }
        );
    }


    controls.search.addEventListener(
        "input",
        () => {
            state.search =
                controls.search.value;

            refreshViews(
                false
            );
        }
    );

    bindSelect(
        controls.sampleType,
        "sampleType"
    );

    bindSelect(
        controls.status,
        "status"
    );

    bindSelect(
        controls.biosafety,
        "biosafety"
    );

    bindSelect(
        controls.owner,
        "owner"
    );

    bindSelect(
        controls.biobank,
        "biobank"
    );

    bindSelect(
        controls.researchGroup,
        "researchGroup"
    );

    bindSelect(
        controls.collection,
        "collection"
    );


    controls.connectedOnly
    .addEventListener(
        "change",
        () => {
            state.connectedOnly =
                controls.connectedOnly.checked;

            refreshViews(
                true
            );
        }
    );


    [
        [
            controls.edgeLineage,
            "lineage",
        ],
        [
            controls.edgeStorage,
            "storage",
        ],
        [
            controls.edgeInfection,
            "infection",
        ],
        [
            controls.edgeOther,
            "other",
        ],
    ].forEach(
        ([element, key]) => {
            element.addEventListener(
                "change",
                () => {
                    state.relationships[
                        key
                    ] = element.checked;

                    refreshViews(
                        true
                    );
                }
            );
        }
    );


    function setLayout(value) {
        clearClusters();

        if (value === "hierarchical") {
            network.setOptions(
                {
                    layout: {
                        hierarchical: {
                            enabled: true,
                            direction: "LR",
                            sortMethod: "directed",
                            nodeSpacing: 135,
                            levelSeparation: 165,
                        },
                    },
                    physics: {
                        enabled: false,
                    },
                }
            );
        } else {
            network.setOptions(
                forceOptions
            );
        }

        setTimeout(
            () => network.fit(),
            120
        );
    }


    controls.layout.addEventListener(
        "change",
        () => {
            setLayout(
                controls.layout.value
            );
        }
    );


    let clusterIds = [];


    function clearClusters() {
        clusterIds
        .slice()
        .reverse()
        .forEach(
            (clusterId) => {
                try {
                    if (
                        network.isCluster(
                            clusterId
                        )
                    ) {
                        network.openCluster(
                            clusterId
                        );
                    }
                } catch (_error) {
                    // A cluster may already have been opened.
                }
            }
        );

        clusterIds = [];
    }


    function computeComponents() {
        const visibleIds =
            new Set(
                nodesView
                .get()
                .map(
                    (node) => node.id
                )
            );

        const adjacency =
            new Map();

        visibleIds.forEach(
            (id) => {
                adjacency.set(
                    id,
                    new Set()
                );
            }
        );

        edgesView.get().forEach(
            (edge) => {
                if (
                    !visibleIds.has(
                        edge.from
                    )
                    || !visibleIds.has(
                        edge.to
                    )
                ) {
                    return;
                }

                adjacency.get(
                    edge.from
                ).add(
                    edge.to
                );

                adjacency.get(
                    edge.to
                ).add(
                    edge.from
                );
            }
        );

        const componentById =
            new Map();

        let componentNumber = 0;

        visibleIds.forEach(
            (startId) => {
                if (
                    componentById.has(
                        startId
                    )
                ) {
                    return;
                }

                componentNumber += 1;

                const queue = [
                    startId,
                ];

                componentById.set(
                    startId,
                    componentNumber
                );

                while (
                    queue.length
                ) {
                    const current =
                        queue.shift();

                    adjacency
                    .get(
                        current
                    )
                    .forEach(
                        (neighbor) => {
                            if (
                                componentById
                                .has(
                                    neighbor
                                )
                            ) {
                                return;
                            }

                            componentById.set(
                                neighbor,
                                componentNumber
                            );

                            queue.push(
                                neighbor
                            );
                        }
                    );
                }
            }
        );

        return componentById;
    }


    function groupingValue(
        node,
        key,
        components
    ) {
        if (
            key === "connected_component"
        ) {
            const value =
                components.get(
                    node.id
                );

            return value
                ? `Component ${value}`
                : "Unassigned";
        }

        if (
            key === "node_type"
        ) {
            const labels = {
                bacteria: "Bacteria",
                phage: "Phages",
                plasmid: "Plasmids",
                generic: "Other",
            };

            return (
                labels[
                    node.node_type
                ]
                || "Other"
            );
        }

        return (
            node[
                key
            ]
            || "Unassigned"
        );
    }


    function applyClustering(
        key
    ) {
        clearClusters();

        if (!key) {
            return;
        }

        const visibleNodes =
            nodesView.get();

        const components =
            computeComponents();

        const values =
            new Set(
                visibleNodes.map(
                    (node) => (
                        groupingValue(
                            node,
                            key,
                            components
                        )
                    )
                )
            );

        values.forEach(
            (value) => {
                const memberIds =
                    visibleNodes
                    .filter(
                        (node) => (
                            groupingValue(
                                node,
                                key,
                                components
                            ) === value
                        )
                    )
                    .map(
                        (node) => (
                            node.id
                        )
                    );

                if (
                    memberIds.length < 2
                ) {
                    return;
                }

                const id =
                    `cluster:${key}:${value}`;

                network.cluster(
                    {
                        joinCondition(
                            node
                        ) {
                            return (
                                memberIds
                                .includes(
                                    node.id
                                )
                            );
                        },
                        clusterNodeProperties: {
                            id,
                            label:
                                `${value} (${memberIds.length})`,
                            shape: "database",
                            color: {
                                background: "#dbeafe",
                                border: "#2563eb",
                            },
                            font: {
                                color: "#1e3a8a",
                                size: 13,
                            },
                            borderWidth: 2,
                        },
                    }
                );

                clusterIds.push(
                    id
                );
            }
        );

        setTimeout(
            () => network.fit(),
            100
        );
    }


    controls.clusterBy
    .addEventListener(
        "change",
        () => {
            applyClustering(
                controls.clusterBy.value
            );
        }
    );


    network.on(
        "doubleClick",
        (params) => {
            if (
                params.nodes.length !== 1
            ) {
                return;
            }

            const nodeId =
                params.nodes[0];

            if (
                network.isCluster(
                    nodeId
                )
            ) {
                network.openCluster(
                    nodeId
                );

                return;
            }

            const node =
                rawNodes.get(
                    nodeId
                );

            if (
                node
                && node.detail_url
            ) {
                window.location.href =
                    node.detail_url;
            }
        }
    );


    function clearInspector() {
        controls.inspector.className =
            "sample-network-inspector-empty";

        controls.inspector.textContent =
            "Nothing selected.";
    }


    function appendText(
        parent,
        className,
        value
    ) {
        const element =
            document.createElement(
                "div"
            );

        element.className =
            className;

        element.textContent =
            String(
                value
            );

        parent.appendChild(
            element
        );

        return element;
    }


    function appendRow(
        parent,
        key,
        value
    ) {
        if (
            value === null
            || value === undefined
            || String(value).trim() === ""
        ) {
            return;
        }

        const row =
            document.createElement(
                "div"
            );

        row.className =
            "sample-network-inspector-row";

        appendText(
            row,
            "sample-network-inspector-key",
            key
        );

        appendText(
            row,
            "sample-network-inspector-value",
            value
        );

        parent.appendChild(
            row
        );
    }


    function inspectorSection(
        parent,
        title
    ) {
        const section =
            document.createElement(
                "div"
            );

        section.className =
            "sample-network-inspector-section";

        appendText(
            section,
            "sample-network-inspector-label",
            title
        );

        parent.appendChild(
            section
        );

        return section;
    }


    function showNode(
        node
    ) {
        controls.inspector.className = "";
        controls.inspector.replaceChildren();

        appendText(
            controls.inspector,
            "sample-network-inspector-heading",
            node.organism_name
                || "Unspecified organism"
        );

        appendText(
            controls.inspector,
            "sample-network-inspector-id",
            node.sample_id
        );

        const badges =
            document.createElement(
                "div"
            );

        badges.className =
            "sample-network-badges";

        [
            node.sample_type,
            node.status_label,
            node.biosafety_level,
        ]
        .filter(Boolean)
        .forEach(
            (value) => {
                appendText(
                    badges,
                    "sample-network-badge",
                    value
                );
            }
        );

        controls.inspector.appendChild(
            badges
        );

        const governance =
            inspectorSection(
                controls.inspector,
                "Governance"
            );

        appendRow(
            governance,
            "Owner",
            node.owner
        );

        appendRow(
            governance,
            "Research Group",
            node.research_group
        );

        appendRow(
            governance,
            "Biobank",
            node.biobank
        );

        appendRow(
            governance,
            "Collections",
            node.collections_text
        );

        const relationships =
            inspectorSection(
                controls.inspector,
                "Network"
            );

        appendRow(
            relationships,
            "Connections",
            node.degree
        );

        appendRow(
            relationships,
            "Sample relations",
            node.relationship_count
        );

        appendRow(
            relationships,
            "Host ranges",
            node.host_range_count
        );

        if (
            node.detail_url
        ) {
            const link =
                document.createElement(
                    "a"
                );

            link.href =
                node.detail_url;

            link.className =
                "btn btn-sm btn-primary w-100 mt-3";

            link.textContent =
                "View Sample";

            controls.inspector.appendChild(
                link
            );
        }
    }


    function showEdge(
        edge
    ) {
        controls.inspector.className = "";
        controls.inspector.replaceChildren();

        appendText(
            controls.inspector,
            "sample-network-inspector-heading",
            edge.label
                || "Relationship"
        );

        appendText(
            controls.inspector,
            "sample-network-inspector-id",
            edge.relationship_category
                || "other"
        );

        const source =
            rawNodes.get(
                edge.from
            );

        const target =
            rawNodes.get(
                edge.to
            );

        const endpoints =
            inspectorSection(
                controls.inspector,
                "Endpoints"
            );

        appendRow(
            endpoints,
            "Source",
            source
                ? source.sample_id
                : edge.from
        );

        appendRow(
            endpoints,
            "Target",
            target
                ? target.sample_id
                : edge.to
        );

        const metadata =
            inspectorSection(
                controls.inspector,
                "Relationship"
            );

        appendRow(
            metadata,
            "Type",
            edge.relationship_type
        );

        appendRow(
            metadata,
            "Notes",
            edge.notes
        );

        appendRow(
            metadata,
            "Created by",
            edge.created_by
        );

        appendRow(
            metadata,
            "EOP",
            edge.efficiency_eop
        );

        if (
            edge.relation_source
            === "host_range"
        ) {
            appendRow(
                metadata,
                "Isolation host",
                edge.is_isolation_host
                    ? "Yes"
                    : "No"
            );
        }
    }


    function focusGroupedSample(
        clusterId,
        node
    ) {
        if (
            clusterId
            && network.isCluster(
                clusterId
            )
        ) {
            network.openCluster(
                clusterId
            );
        }

        network.selectNodes(
            [
                node.id,
            ]
        );

        network.focus(
            node.id,
            {
                scale: 1.45,
                animation: {
                    duration: 550,
                    easingFunction:
                        "easeInOutQuad",
                },
            }
        );

        showNode(
            node
        );
    }


    function showCluster(
        clusterId
    ) {
        const memberIds =
            network.getNodesInCluster(
                clusterId
            );

        const members =
            rawNodes
            .get(
                memberIds
            )
            .filter(Boolean)
            .sort(
                (left, right) => (
                    String(
                        left.sample_id
                        || left.label
                        || ""
                    )
                    .localeCompare(
                        String(
                            right.sample_id
                            || right.label
                            || ""
                        ),
                        undefined,
                        {
                            numeric: true,
                            sensitivity: "base",
                        }
                    )
                )
            );

        controls.inspector.className =
            "";

        controls.inspector
        .replaceChildren();

        let groupName =
            "Grouped Samples";

        const groupingKey =
            controls.clusterBy
                ? controls.clusterBy.value
                : "";

        if (
            members.length
            && groupingKey
        ) {
            const components =
                groupingKey
                === "connected_component"
                    ? computeComponents()
                    : new Map();

            groupName =
                groupingValue(
                    members[0],
                    groupingKey,
                    components
                );
        }

        appendText(
            controls.inspector,
            "sample-network-inspector-heading",
            groupName
        );

        appendText(
            controls.inspector,
            "sample-network-inspector-id",
            `${members.length} Sample${
                members.length === 1
                    ? ""
                    : "s"
            }`
        );


        const connectedCount =
            members.filter(
                (node) => (
                    Number(
                        node.degree
                        || 0
                    ) > 0
                )
            ).length;

        const isolatedCount =
            members.length
            - connectedCount;


        const summary =
            document.createElement(
                "div"
            );

        summary.className =
            "sample-network-group-summary";

        appendText(
            summary,
            "sample-network-group-summary-item",
            `${connectedCount} connected`
        );

        appendText(
            summary,
            "sample-network-group-summary-item",
            `${isolatedCount} isolated`
        );

        controls.inspector.appendChild(
            summary
        );


        const section =
            inspectorSection(
                controls.inspector,
                "Samples"
            );


        const search =
            document.createElement(
                "input"
            );

        search.type =
            "search";

        search.className =
            (
                "form-control "
                + "form-control-sm "
                + "sample-network-group-search"
            );

        search.placeholder =
            "Filter Sample ID or organism...";

        search.autocomplete =
            "off";

        section.appendChild(
            search
        );


        const count =
            document.createElement(
                "div"
            );

        count.className =
            "sample-network-group-result-count";

        section.appendChild(
            count
        );


        const list =
            document.createElement(
                "div"
            );

        list.className =
            "sample-network-group-members";

        section.appendChild(
            list
        );


        function renderMembers() {
            const term =
                normalize(
                    search.value
                );

            const filtered =
                members.filter(
                    (node) => {
                        if (!term) {
                            return true;
                        }

                        return [
                            node.sample_id,
                            node.organism_name,
                            node.sample_type,
                        ].some(
                            (value) => (
                                normalize(
                                    value
                                ).includes(
                                    term
                                )
                            )
                        );
                    }
                );


            count.textContent =
                `${filtered.length} of ${members.length} shown`;

            list.replaceChildren();


            if (!filtered.length) {
                appendText(
                    list,
                    "sample-network-group-empty",
                    "No Samples match this group search."
                );

                return;
            }


            filtered.forEach(
                (node) => {
                    const button =
                        document.createElement(
                            "button"
                        );

                    button.type =
                        "button";

                    button.className =
                        "sample-network-group-member";

                    button.title =
                        `Locate ${node.sample_id}`;


                    const copy =
                        document.createElement(
                            "span"
                        );

                    copy.className =
                        "sample-network-group-member-copy";


                    appendText(
                        copy,
                        "sample-network-group-member-id",
                        node.sample_id
                            || node.label
                            || `Sample ${node.id}`
                    );


                    if (
                        node.organism_name
                    ) {
                        appendText(
                            copy,
                            "sample-network-group-member-organism",
                            node.organism_name
                        );
                    }


                    const locate =
                        document.createElement(
                            "span"
                        );

                    locate.className =
                        "sample-network-group-member-locate";

                    locate.setAttribute(
                        "aria-hidden",
                        "true"
                    );

                    const icon =
                        document.createElement(
                            "i"
                        );

                    icon.className =
                        "bi bi-crosshair";

                    locate.appendChild(
                        icon
                    );


                    button.appendChild(
                        copy
                    );

                    button.appendChild(
                        locate
                    );


                    button.addEventListener(
                        "click",
                        () => {
                            focusGroupedSample(
                                clusterId,
                                node
                            );
                        }
                    );


                    list.appendChild(
                        button
                    );
                }
            );
        }


        search.addEventListener(
            "input",
            renderMembers
        );


        renderMembers();


        if (
            members.length
        ) {
            const actions =
                document.createElement(
                    "div"
                );

            actions.className =
                "sample-network-group-actions";


            const fitMembers =
                document.createElement(
                    "button"
                );

            fitMembers.type =
                "button";

            fitMembers.className =
                (
                    "btn btn-sm "
                    + "btn-outline-primary w-100"
                );

            fitMembers.textContent =
                "Show Group in Graph";


            fitMembers.addEventListener(
                "click",
                () => {
                    if (
                        network.isCluster(
                            clusterId
                        )
                    ) {
                        network.openCluster(
                            clusterId
                        );
                    }

                    network.selectNodes(
                        memberIds
                    );

                    network.fit(
                        {
                            nodes:
                                memberIds,
                            animation: {
                                duration: 550,
                                easingFunction:
                                    "easeInOutQuad",
                            },
                        }
                    );
                }
            );


            actions.appendChild(
                fitMembers
            );

            controls.inspector.appendChild(
                actions
            );
        }
    }


    network.on(
        "click",
        (params) => {
            if (
                params.nodes.length === 1
            ) {
                const nodeId =
                    params.nodes[0];

                if (
                    network.isCluster(
                        nodeId
                    )
                ) {
                    showCluster(
                        nodeId
                    );

                    return;
                }

                const node =
                    rawNodes.get(
                        nodeId
                    );

                if (node) {
                    showNode(
                        node
                    );
                }

                return;
            }

            if (
                params.edges.length === 1
            ) {
                const edge =
                    rawEdges.get(
                        params.edges[0]
                    );

                if (edge) {
                    showEdge(
                        edge
                    );
                }

                return;
            }

            clearInspector();
        }
    );


    controls.fit.addEventListener(
        "click",
        () => {
            network.fit(
                {
                    animation: {
                        duration: 350,
                    },
                }
            );
        }
    );


    controls.resetView
    .addEventListener(
        "click",
        () => {
            clearClusters();

            controls.clusterBy.value =
                "";

            controls.layout.value =
                "force";

            setLayout(
                "force"
            );

            network.fit();
        }
    );


    controls.resetFilters
    .addEventListener(
        "click",
        () => {
            state.search = "";
            state.sampleType = "";
            state.status = "";
            state.biosafety = "";
            state.owner = "";
            state.biobank = "";
            state.researchGroup = "";
            state.collection = "";
            state.connectedOnly = false;

            Object.keys(
                state.relationships
            ).forEach(
                (key) => {
                    state.relationships[
                        key
                    ] = true;
                }
            );

            controls.search.value = "";
            controls.sampleType.value = "";
            controls.status.value = "";
            controls.biosafety.value = "";
            controls.owner.value = "";
            controls.biobank.value = "";
            controls.researchGroup.value = "";
            controls.collection.value = "";
            controls.connectedOnly.checked = false;
            controls.edgeLineage.checked = true;
            controls.edgeStorage.checked = true;
            controls.edgeInfection.checked = true;
            controls.edgeOther.checked = true;

            refreshViews(
                true
            );
        }
    );


    refreshViews(
        false
    );
})();
