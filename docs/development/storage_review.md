# Storage review: behaviour and interface

Date: 2026-11-04. Review only, no code changed. Screens checked in a dev
database with one workspace, nine locations (room, two freezers, two shelves,
rack, three boxes, two of them 9 x 9 grids) and 30 recorded samples.

## 1. What exists

Data model (`core/models/samples/storage.py`)

- `StorageWorkspace`: ownership boundary, personal or research group.
- `StorageLocation`: tree (room, freezer, shelf, rack, box, position, other),
  workspace optional (null = legacy unscoped inventory).
- `StorageLocationLayoutV8146C3`: optional grid (rows x columns, max 26 x 24)
  with type and temperature labels.
- `SampleStorageAssignment`: sample, location, free-text `position`, status;
  a unique active slot per (location, lower(position)).
- `StorageMovement` + `StorageMovementItem`: audited moves of a container, a
  sample or a selection, with path snapshots.
- `StorageSceneConfiguration`: per-user visual configuration (profiles per
  root) used only by the legacy interface.

Services: about 25 modules (`storage_*`), including movement preview and
confirmation, subtree delete/unassign, workspace delete, writer lock,
reconcile, legacy projection and sync. Permissions are workspace based.

Interface: `/storage/` serves `index_v814.html` (canonical). `?legacy=1`
serves `index.html` (the older Storage Designer). Both are in production.

## 2. Behaviour findings

1. Moves are safe by design: preview with before/after, a reason, one audited
   movement per operation, a lock for writers. Keep.
2. A location stores only its parent, so moving a container moves everything
   below it. The interface says so ("0 locations and 12 Samples depend on
   this level"). Keep.
3. Occupancy is only known for grid boxes. In the dev data the room card says
   "24/162 positions, 30 Samples": the 6 samples in a free box count as
   samples but not as occupied positions, so the ratio mixes two measures.
   Needs one rule (for example capacity shown only where every descendant box
   is a grid, otherwise show samples only).
4. `position` is free text. The grid view assumes "A1" style names; names
   such as "a1" or "1A" are tolerated by the unique index (case-insensitive)
   but may not land on the grid. Needs a validation or a "not on the map" list.
5. Historical registrations (legacy text locations) are shown read-only in
   every location view. Useful for audit, but they add noise to the main
   screen; they could move into a collapsed "Historical" section.
6. Everything is delivered in one page: all visible locations and all visible
   assignments are embedded as `<template>` data and filtered in the browser.
   Fine for hundreds of samples, a problem for tens of thousands. No
   pagination, no server-side search (the search box was hidden in v8.14.7).
7. Sample-to-storage links exist elsewhere (sample intake, bulk storage
   move, shipments, ELN is not linked yet). There is no storage container
   picker on an ELN entry (roadmap 2.3).

## 3. Interface findings

Canonical screen (v8.14), tabs Contents / Path tree / Movements / Manage.

- Contents: tree on the left with sample counts, stats cards, child cards,
  list of recorded samples (collapsed for boxes), position map for grids. The
  position map is the best part: clear, shows occupancy, selectable.
- Path tree: a horizontal graph of levels. With 5 levels the first two
  columns are cut off on a 1440 px screen ("zer -20 B"), and the "Level 5"
  label for a box counts the room as level 1, which is confusing for users.
- Movements: empty table plus a collapsed "Sample transfers" block, two
  places for one idea (container moves vs sample moves).
- Manage: long list with an inner scroll box and a second "Selected location"
  block below it, so the edit form is far from the list.
- Overview (nothing selected): shows only the root as a card with the mixed
  occupancy figure; nothing visual for the freezer or rack level.

Legacy screen (`?legacy=1`), which is where the "illustration" lives
(isometric blocks, 2D, hierarchy, graph, "Isometric + 2D" modes).

- Shows "0 Samples" on the room and on both freezers because counts are not
  rolled up, while the new screen rolls them up (30).
- Text overlaps at the bottom of the viewer and the Back button overlaps the
  level selector at 1440 px.
- The user already moved the lab off the 3D viewer because it broke by
  browser; the SVG isometric replaced it but it still is a separate mode set.
- About 6,900 lines of JS/CSS (14 scripts plus the explorer stylesheet) are
  loaded only by this screen, plus 2,068 lines of templates, plus the scene
  configuration model and services (about 680 lines). Tests still reference
  these files, which is why they cannot simply be deleted.

## 4. What the interface does not illustrate yet

- Freezer, shelf and rack levels have no picture: a user sees a list of
  child cards and a number. A rack could be shown as tiles (one per box) with
  a fill bar, a shelf as a row of racks, a freezer as its shelves.
- No heat of occupancy across the whole tree (which freezers are nearly full).
- No "find a free position" helper when registering or moving samples.
- No label/printing support (box labels, QR) and no scan-to-locate.
- No capacity warning when a box is full on registration.

## 5. Proposed decisions (to confirm)

Keep: the data model, movement flow and audit, the position grid, the tree
with roll-up counts, workspaces and permissions.

Change in small releases:

1. Define one occupancy rule and show it consistently (tree, cards, stats).
2. Container view: tiles with fill bars for the children of the selected
   location, replacing the isometric and graph modes in the new screen.
3. Path tree: fit levels in the viewport (scroll to the selected column,
   level numbers relative to the workspace root).
4. Manage tab: put the edit form beside or above the list, move the
   historical registrations into a collapsed section.
5. Server-side pagination and search for samples in a location (needed
   before the sample count grows).
6. Free-position helper and capacity check in registration and moves.

Retire (after the above): the `?legacy=1` interface, its 14 scripts,
templates, scene configuration model and services, with an expand/contract
plan for the model and its tests. Do this last, once the lab confirms that
nothing from the isometric view is still needed.

## 6. Questions for the lab

- Which view do people actually use today: legacy isometric, or only the new
  screen? (Production access logs can answer this.)
- Do boxes always use A1-style grids, or are other position names in use?
- Is label printing or scanning a requirement for this phase?
