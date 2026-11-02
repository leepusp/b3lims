"""Synthetic visual preview only. No database access."""

DEMO_EXPERIMENTS = (
    {
        "id": "DEMO-001",
        "title": "Phage adsorption assay — pilot",
        "category": "Phage assay",
        "status": "Running",
        "progress": 35,
        "owner": "Demo Researcher A",
        "storage": "Private project",
        "updated": "Demo date",
        "pinned": True,
    },
    {
        "id": "DEMO-002",
        "title": "Bacterial growth curve",
        "category": "Culture",
        "status": "Completed",
        "progress": 100,
        "owner": "Demo Researcher B",
        "storage": "Published",
        "updated": "Demo date",
        "pinned": True,
    },
    {
        "id": "DEMO-003",
        "title": "PCR optimization",
        "category": "Molecular",
        "status": "Needs review",
        "progress": 65,
        "owner": "Demo Researcher A",
        "storage": "Private project",
        "updated": "Demo date",
        "pinned": True,
    },
    {
        "id": "DEMO-004",
        "title": "Plasmid verification",
        "category": "Molecular",
        "status": "Draft",
        "progress": 15,
        "owner": "Demo Researcher C",
        "storage": "Private project",
        "updated": "Demo date",
        "pinned": False,
    },
    {
        "id": "DEMO-005",
        "title": "Protein expression screening",
        "category": "Protocol",
        "status": "Running",
        "progress": 50,
        "owner": "Demo Researcher B",
        "storage": "Private project",
        "updated": "Demo date",
        "pinned": False,
    },
    {
        "id": "DEMO-006",
        "title": "Sample characterization",
        "category": "Culture",
        "status": "Completed",
        "progress": 100,
        "owner": "Demo Researcher C",
        "storage": "Published",
        "updated": "Demo date",
        "pinned": False,
    },
)


def build_demo_preview(params):
    """Build a filtered, immutable synthetic-only preview."""
    query = str(params.get("q", ""))[:80].strip()
    category = str(params.get("category", ""))[:40]
    status = str(params.get("status", ""))[:40]
    scope = str(params.get("scope", "all"))[:20]

    categories = (
        "Phage assay", "Culture", "Molecular", "Protocol"
    )
    statuses = (
        "Draft", "Running", "Needs review", "Completed"
    )

    if category not in categories:
        category = ""

    if status not in statuses:
        status = ""

    if scope not in {"all", "pinned"}:
        scope = "all"

    entries = list(DEMO_EXPERIMENTS)

    if query:
        needle = query.casefold()
        entries = [
            entry for entry in entries
            if needle in (
                entry["title"] + " " + entry["id"]
            ).casefold()
        ]

    if category:
        entries = [
            entry for entry in entries
            if entry["category"] == category
        ]

    if status:
        entries = [
            entry for entry in entries
            if entry["status"] == status
        ]

    if scope == "pinned":
        entries = [
            entry for entry in entries
            if entry["pinned"]
        ]

    return {
        "entries": entries,
        "pinned": [
            entry for entry in DEMO_EXPERIMENTS
            if entry["pinned"]
        ],
        "categories": categories,
        "statuses": statuses,
        "query": query,
        "selected_category": category,
        "selected_status": status,
        "scope": scope,
        "demo_total": len(DEMO_EXPERIMENTS),
    }
