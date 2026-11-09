# B3 LIMS: ELN, calendar and registry checklist

Working list agreed with the lab. Each block must be finished, tested and deployed
before the next one starts. `[x]` done and live, `[~]` done, waiting for deploy,
`[ ]` open.

## Block A: finish ELN 2.2 (do this before anything else)

- [x] Advanced search (`title:gel and status:completed`, `extrafield:Medium:TSB`)
- [~] Sharing: read / edit / manage grants for users and research groups (no migration)
- [~] "Shared with me" filter in the entries dashboard
- [~] Ownership transfer (to a person who already has access; former author keeps edit; history stays)
- [x] Categories and statuses per research group, with colours (migration 0098; entry picks the group, coordinator and superusers edit the lists at /internal/lab-tools/notebook/lists/)
- [x] Editable entry templates (stored in the database: "Save as template" from any entry, shared with nobody, a research group or the lab; manage at /internal/lab-tools/notebook/templates/; built-in templates stay in code)
- [x] Favourite tags panel and step groups (ELN tags and keywords now use the biobank-wide Tag and Keyword vocabulary; legacy NotebookTag and NotebookEntry.tags are kept for rollback and are to be dropped in a later release)
- [x] Field builder for extra fields (the visual builder and "Load fields"). A JSON editor was built and then removed on Nov 4: no use for it now; revisit only for import/export between systems.
- [x] ELN as a hub of the LIMS, part 1: sample, reagent, molecular record and Jupyter
      notebook pages show a panel "Used in experiments" (links, @-mentions, creation entry),
      listing only entries the viewer may see (`core/services/notebook_backlinks.py`).
- [ ] ELN as a hub, part 2: shipments, collections, storage positions, constructions (with
      Block D), and the same panel for extra-field references (items, compounds).
- [x] Review (Nov 4): dashboard filters now include category, group, tag and keyword with
      removable chips; the cloud became a "Tags and keywords" panel with favourites on top;
      the to-do and "Steps with deadlines" became one "My tasks" card (tasks can point to an entry);
      the JSON editor was removed.
- [~] Rename the stored keys (`extra_fields`, `elabftw.extra_fields_groups`) to `custom_fields` and
      `custom_field_groups`. Expand release done in code (read either, write both, data migration
      0101, `backfill_custom_field_layout` command for after a rollback). Contract release open:
      set `WRITE_LEGACY_KEYS = False` in `core/services/custom_field_layout.py`, drop the fallbacks
      and the old keys once the rollback target no longer needs them.
- [ ] Gaps found against the reference screens, none built yet: "Draw something" canvas saved as
      an attachment (2.4), spreadsheet editor polish, compounds search, storage containers on the
      entry (2.3), exclusive "More" menu actions. Decide each one on use, not on parity.
- [ ] Browser check of all of the above on production

## Block B: Lab Calendar (new, runs on the existing `bench` Booking models)

Today `/calendar/` only lists the last 100 sample events. It becomes a real calendar.

Foundation
- [x] Month, week, day and agenda views (FullCalendar 6, MIT, vendored with checksums)
- [x] Manage layers: each layer has a name, a colour and a description of what it stands for.
      Built-in layers (step deadlines, sample events grouped per day and type) are styled per person;
      custom layers (an instrument, a room, lab meetings) are shared, with booking rules kept optional
- [ ] More built-in layers: to-dos, shipments, sample reminders
- [x] Create, move and resize bookings in the calendar, with conflict detection
      and the existing resource rules (rule messages shown in the form, drag reverts on refusal)
- [~] Recurring bookings: every N days or weeks, chosen weekdays, ending after N times or on a date;
      cancel one or the rest of the series. Still open: monthly rules, per-event reminders
- [ ] Attendees with accept / decline, and a link from an event to an ELN entry
- [x] Dashboard card "Today and this week" (own bookings and step deadlines, shown through an extension panel)

Google Calendar
- [ ] Step 1, no credentials needed: per-user private `.ics` feed, with a token that can be
      renewed or revoked, to subscribe from Google Calendar ("From URL").
      Needs the LIMS address to be reachable from Google's servers, and Google
      refreshes subscribed feeds only every several hours.
- [x] Step 1: "Add to Google Calendar" button and `.ics` download on every booking
- [ ] Step 2, needs a Google Cloud OAuth client created by the lab: push LIMS events
      to the user's Google Calendar and keep them updated or removed; optional read of
      busy times to avoid booking conflicts. Tokens stored encrypted, one-click disconnect.
- [~] Export of the view on screen as `.ics` is done (CSV still open)

Other useful functions
- [ ] Usage report per layer (hours per user and per group)
- [ ] Booking approval for restricted equipment, and e-mail notification
- [ ] "Find a free slot" for a resource and for a group of people
- [ ] Booking templates for common runs (sequencing, qPCR, culture passages)

## Block C: ELN 2.3 to 2.6 (see `eln_elabftw_parity.md`)

- [ ] 2.3 resources, storage on entry
- [ ] 2.4 Ketcher, PubChem, 3D viewer, drawing
- [ ] 2.5 lock, signatures, RFC 3161 timestamps, audit, request actions, notifications
- [ ] 2.6 exports (PDF, `.eln`, CSV, ZIP, QR), imports, REST API with keys

## Block D: Molecular Registry rework

- [ ] Map what the Registry does today and where each OpenCloning module fits
      (cloning, primers, description, sequence, data model, settings)
- [ ] Implement the OpenCloning-style structures in the Registry
- [ ] Clean up the old structures
- [x] Record page shell: record bar, tracks rail, inspector, docked annotation editor, interactive ORF panel (p26, p27)
- [ ] Workbench by function (design in the Registry canvas, boards 5 to 7): focus mode, Map / Digest / Primers modes, collapsible panels, one map + sequence view instead of separate viewers
- [ ] Digest with gel simulation and fragment list (calculation in a small UMD module with Node tests)
- [ ] Primer tools: Tm, dimers, binding sites across the Registry, PCR product to Insert record
- [ ] Chemistry workbench: structure editor (Ketcher, Apache-2.0, embedded), SMILES/MOL import, calculated properties, reaction stoichiometry table linked to Chemicals stock (Block C 2.4)
- [ ] ELN cards: embed a Registry record view (map, digest, primer, structure) in an entry, pinned to a version or live, opening the workbench on the same view
- [ ] Bench calculators (dilution, buffer, molarity, master mix, gel marker, plate layout) as small pure-JS tools, inspired by Lablaps (closed product, ideas only; no code to reuse)
- [ ] Decide OpenCloning route: library inside Django, adopt its JSON history, or embedded container

## Block E: workflows and submissions

- [ ] Map the workflow steps already announced on the Laboratory hub (6.1 to 6.7) and what exists today
- [x] Workflow model (phase 1): steps with status, owner, due date and connections, linked to ELN entries, molecular records and samples; steps due show in the Calendar
- [ ] 6.3 Run Jupyter notebooks inside workflows (Slurm job, inputs and outputs linked to the ELN entry)
- [ ] Galaxy steps in a workflow
- [ ] Review NoLabs (Apache-2.0; FastAPI microservices for ESMFold, DiffDock, RFdiffusion, ProteinMPNN, BLAST; Celery + Redis scheduler) as a source of model steps: call its microservice REST endpoints from a workflow step, store result as a Registry record (PDB to Protein structure); do not adopt its UI or workflow engine
- [x] Workflow builder screen (canvas, side panel, import of ELN steps, members)
- [ ] 5.2 and 6.6 Data submissions: RO-Crate packages for ENA, Zenodo and the public catalog
- [ ] Submissions: ENA, NCBI, Zenodo
- [ ] Hub cards for Workflows and Data submissions move from "Planned" to "Available" as each ships

## Block F: Storage interface review (to be scheduled)

Context: the storage view started as a 3D scene (`_viewer_3d.html`, `storage_spatial_v5.js`
and the V8 scene files). It broke depending on the browser, so the lab moved to a 2D
view that is still visual and interactive (isometric, hierarchy, graph and position grid:
`storage_isometric_v813.js`, `storage_2d_hierarchy_v89b.js`, `storage_graph_v811.js`,
`storage_position_grid_v8146c3.js`). Not started; needs a review before any work.

- [x] Review how Storage behaves (moves, positions, capacity, occupancy, permissions, history): see `storage_review.md`
- [x] Review how the interface illustrates it (isometric, hierarchy, graph, position grid): see `storage_review.md`
- [x] Decide what to keep, merge or drop, then plan the changes in small releases
- [x] One occupancy rule (grid positions only; outside-a-grid and off-the-grid counted apart)
- [x] Path tree fits the frame; columns named by location type
- [x] Manage tab: list beside the edit form; historical registrations collapsed; transfers explained
- [x] Layout tab, first version (read-only; judged not useful on Nov 4, to be redone below)
- [~] Storage is a free tree: the user picks the levels (institute, corridor, room, fridge, box...).
      A location says how it holds Samples: a single place, a grid (box, rack) or named
      compartments (doors, drawers, shelves), drawn live while it is created (migration 0102)
- [~] Any level can receive Samples; the position is checked against the drawing (A1 inside the
      grid, or one of the compartment names); sample registration shows the drawing and the
      user clicks free positions
- [~] Layout tab redone: grids and named compartments drawn with what is stored in them; select
      a position or compartment to see its Samples and move them
- [~] Destination picker: the tree on the left, the drawing of the chosen place on the right;
      click the first free position and N Samples take the next N free ones. Used to move a
      whole location (all Samples inside go with it), one Sample, or a batch (up to 50 per preview).
      Every move still goes through the server preview and confirmation
- [ ] Edit the drawing of an existing location (add a door, widen a grid)
- [ ] Server-side search and pagination of samples per location
- [ ] Free-position helper and capacity check on registration and moves
- [ ] Retire the legacy interface (`?legacy=1`), its scripts, scene model and services

- [ ] Review how Storage behaves (create, move, occupy, free, history, permissions)
- [ ] Review how Storage is illustrated in the interface (which views stay, what each shows,
      browser behaviour, mobile, empty and full states)
- [ ] Decide what to keep, merge or retire, then implement

- [ ] Review the whole storage UI and how it is built: about 20 script files with version
      suffixes (`v4` to `v8146c3`), one 1,094-line template (`index_v814.html`) and two
      generations of explorer; decide what is still used, merge or remove the rest
- [ ] Decide whether the old 3D viewer and scene scripts stay, are hidden behind a flag,
      or are removed (do not ship code that breaks on some browsers)
- [ ] Improve the 2D view: clearer boxes, freezers, racks and positions, search and
      highlight a sample, drag to move, colour by collection or status, zoom and pan
- [ ] Optional 3D later, only if it works everywhere: probe WebGL support first and fall
      back to 2D automatically, with the same data and the same controls
- [ ] Phone and tablet layout for the storage views
- [ ] Review the storage data model and screens together (workspaces, positions,
      movements) before changing the interface, so the new view fits the data

## Housekeeping

- [x] Test research groups removed and the LIMS user `ladmin` deleted (production, 2026-11-03)
- [ ] Look for other test leftovers (collections, biobanks, users, samples)
- [ ] Remove old `static-releases` (keep live, rollback and the two latest)
- [ ] `notebook.py` still holds the Molecular Registry views; split it during Block D

## Housekeeping: stored custom-field keys

- [x] Expand: entries and templates store `custom_fields` / `custom_field_groups`, readers accept both, writers store both, migration 0101 copies rows
- [ ] Contract (later release, once the pre-expand release is no longer a rollback target): set `WRITE_LEGACY_KEYS = False`, run `backfill_custom_field_layout`, drop the old keys
