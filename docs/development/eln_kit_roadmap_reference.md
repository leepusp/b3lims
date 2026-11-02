# ELN roadmap: features adapted from eLabFTW

This is the working spec for extending the Biobank ELN, Lab Calendar and
chemical tools with features found in eLabFTW. Each implementation step has an
ID (for example `1.3`) that pull requests and prompts refer to.

Mockups: `docs/design/eln/` (open the HTML files in a browser).

## Ground rules

1. **No eLabFTW code.** eLabFTW is AGPL-3.0. Use its repository only to read
   which entities, fields and rules exist. Never copy or translate its PHP,
   SQL, TypeScript or Twig into this repository. Write Django code from this
   spec.
2. **Third-party front-end libraries** may be used directly when their licence
   allows it: FullCalendar core and the daygrid, timegrid, list and interaction
   plugins (MIT), Ketcher (Apache-2.0), jsoneditor (Apache-2.0), 3Dmol
   (BSD-3-Clause), OpenCloning (MIT, separate container). Do **not** use
   `@fullcalendar/timeline` or other FullCalendar premium plugins.
3. **Existing data is preserved.** Every model change ships with a migration;
   value changes ship with a data migration that has a reverse function.
4. **Tests run on SQLite** (`biobank/test_settings.py`). PostgreSQL-only
   features (exclusion constraints, `btree_gist`, RDKit) must be guarded by
   `connection.vendor == "postgresql"` and must also be enforced in Python.
5. **Permissions stay centralized** in `core/permissions/`. Views never check
   ownership inline.
6. **Business logic lives in `core/services/`**; views stay thin.
7. **English** for code, templates, labels, messages and migration names.
8. Before each pull request: `python manage.py check`,
   `python manage.py makemigrations --check --dry-run`, `python manage.py test`.

## Current state (before this roadmap)

- `core/models/lab_tools/notebook.py`: `NotebookEntry` with hard-coded
  `ENTRY_TYPE_CHOICES`, `STATUS_CHOICES`, `VISIBILITY_CHOICES`;
  `NotebookBlock`, `NotebookAttachment`, `NotebookSampleLink`,
  `NotebookChemicalLink`, `NotebookMolecularLink`, `NotebookJupyterLink`.
- Templates are a Python dict in
  `core/views/internal/lab_tools/notebook.py::_notebook_entry_templates()`.
- `notebook_delete_entry_api` deletes rows permanently.
- `core/permissions/notebook.py`: private / lab visibility; `shared` has no effect.
- `core/models/access_grants.py`: generic `ResourceAccessGrant`
  (user or `ResearchGroup`, level view/edit/manage).
- `core/views/internal/calendar/views.py`: lists the last 100 sample `Event`s.
- `core/models/chemicals/chemical.py`: `Chemical` mixes identity (name, CAS,
  formula) and stock (lot, quantity, location text).
- `core/models/samples/storage.py`: `StorageLocation` tree and
  `SampleStorageAssignment`.

## Phase 1 — Notebook foundation

### 1.1 Categories and statuses

New models in `core/models/lab_tools/notebook_settings.py`:

- `NotebookCategory`: `research_group` (FK, nullable = global), `title`,
  `color` (hex), `custom_id_prefix` (default `EXP`), `is_private`, `ordering`,
  `is_active`, timestamps. Unique `(research_group, title)` case-insensitive.
- `NotebookStatus`: `research_group`, `title`, `color`, `is_default`,
  `ordering`, `is_active`, timestamps. One default per group.

`NotebookEntry.category` and `NotebookEntry.status` become FKs
(`on_delete=PROTECT`, nullable during migration). A data migration creates
global categories from the current `ENTRY_TYPE_CHOICES` and global statuses from
`STATUS_CHOICES`, then maps every entry. The `archived` status becomes
`state=archived` in step 1.2. Keep the old fields until the data migration
runs, then remove them in a separate migration.

eLabFTW reference: tables `experiments_categories`, `experiments_status`.

### 1.2 Entry identity, state and locking

Add to `NotebookEntry`:

- `custom_id` (positive int, nullable) and property `display_id`
  (`{prefix}-{year}-{custom_id:03d}`). Assigned on create: next number per
  category prefix and year, inside a transaction (`select_for_update`).
- `rating` (0–5), `content_type` (`html` | `markdown`, default `html`).
- `state` (`normal` | `archived` | `deleted`, indexed). Default managers return
  `normal` only; add `all_objects`.
- `locked`, `locked_by`, `locked_at`; `last_change_by`.
- `created_from_template` (FK to `NotebookTemplate`, nullable, added in 1.3).

Delete becomes `state=deleted`; add archive, unarchive and restore actions and a
Trash filter. Locked entries reject edits except unlock by the locker, the owner
or a group coordinator.

### 1.3 Templates as records

`NotebookTemplate`: `title`, `description`, `icon` (Bootstrap Icons name),
`owner`, `research_group`, `default_category`, `default_status`, `content`,
`protocol_content`, `blocks_json` (initial blocks), `metadata` (extra-field
schema, used in 3.1), `default_read_base`, `default_write_base`, `ordering`,
`is_active`, timestamps. Steps for templates come in 3.3.

Data migration: create one global template per entry in
`_notebook_entry_templates()` (same keys, labels, icons, content). The create
menu reads templates from the database; `notebook_create?template=<id>` copies
fields into the new entry and sets `created_from_template`. Keep the helper
function only as the seed source, or delete it once tests use the table.

### 1.4 Revisions, changelog and comments

- `NotebookRevision`: `entry`, `content`, `protocol_content`, `content_type`,
  `created_by`, `created_at`. Saved by a service when content changes and at
  most once per 5 minutes per user, plus always before lock and sign.
  Keep the last 100 per entry.
- `NotebookChangelog`: `entry`, `user`, `field`, `old_value`, `new_value`,
  `created_at`. Written by the service for title, category, status, rating,
  permissions, lock state, links and steps.
- `NotebookComment`: `entry`, `author`, `body`, `is_immutable`, timestamps.
- Views: revision list and side-by-side compare; restore a revision (creates a
  new revision); comment create/delete (author only, not when immutable).

### 1.5 Read and write permissions

Replace `visibility` with `read_base` and `write_base`
(`owner` | `group` | `institution`) plus explicit `ResourceAccessGrant`s for
users and research groups. Migration: `private` → `owner`, `lab` →
`institution` (current behaviour: any authenticated user), `shared` → `owner`.
Rewrite `visible_notebook_entries_for_user`, `can_view_notebook_entry` and
`can_edit_notebook_entry`; add `can_manage_notebook_entry`. Superusers keep full
access. Permissions modal in the entry view.

### 1.6 Entry list (mockup `01-eln-entry-list`)

Scope tabs (mine / my groups / all readable), filters (category, status, owner,
state, tags), search with simple `key:value` terms (`category:`, `status:`,
`tag:`, `owner:`), pinned entries (`NotebookPin`: user + entry), steps progress,
rating, integrity column, batch actions (status, tag, lock, archive, export).
Paginate server side.

### 1.7 Entry view (mockup `02-eln-entry-view`)

Header with display ID, category, inline status select, rating, lock badge,
tags; toolbar (edit, lock/unlock, duplicate, request signature, timestamp,
permissions, export, pin); metadata row; right column with linked items,
integrity card and Comments / Revisions / Changelog tabs. Existing blocks and
attachments stay as they are.

## Phase 2 — Lab Calendar

### 2.1 Bookable equipment and bookings

`core/models/scheduling/`:

- `BookableResource`: `name`, `description`, `research_group`, `location`
  (FK `StorageLocation`, nullable), `color`, `is_bookable`, `max_minutes`
  (0 = no limit), `max_slots` (open future bookings per user, 0 = no limit),
  `can_overlap`, `users_can_book_in_past`, `is_cancellable`,
  `cancel_minutes`, `booking_window_days` (0 = no limit), `hourly_rate`,
  `currency`, `requires_note`, `is_active`. Who can book uses
  `ResourceAccessGrant` (edit level = can book, manage = can manage).
- `Booking`: `resource`, `user`, `research_group`, `title`, `start`, `end`,
  `notebook_entry` (nullable), `recurrence_id` (UUID, nullable),
  `recurrence_index`, `recurrence_rule` (JSON: frequency daily|weekly,
  interval, weekdays, count or until), `cancelled_at`, timestamps.
- `core/services/booking_rules.py`: `validate_booking(resource, user, start,
  end, exclude_ids=())` checks, in order: permission, end after start, past
  start, `max_minutes`, `booking_window_days`, `max_slots`, overlap. Returns
  every failed rule (the UI lists them). Recurring bookings expand to one row
  per occurrence and are validated as a whole.
- PostgreSQL only: `btree_gist` + an exclusion constraint on
  `(resource, tstzrange(start, end))` for non-overlapping resources, added with
  a vendor-guarded `RunSQL`.

### 2.2 Calendar UI (mockup `04-lab-calendar`)

Replace `calendar_view`. FullCalendar 6 (daygrid, timegrid, list, interaction)
from a CDN already allowed by the project. JSON endpoints: list events in a
range, create, move/resize, cancel, plus a `validate` endpoint used live by the
booking form. Sample `Event`s stay visible as a separate toggleable source.
CSV export of bookings for a range.

## Phase 3 — Extra fields, builder, steps, links

### 3.1 Extra fields

Add `metadata = JSONField(default=dict)` to `NotebookEntry` (template already has
it). Format, kept compatible with the `.eln` export of eLabFTW:

```json
{
  "elabftw": {"extra_fields_groups": [{"id": 1, "name": "Culture conditions"}]},
  "extra_fields": {
    "Temperature (°C)": {"type": "number", "value": "28", "group_id": 1, "position": 3,
                          "required": true, "description": "", "blank_value_on_duplicate": false}
  }
}
```

Types: `text`, `number`, `date`, `datetime-local`, `time`, `select` (with
`options`, optional `allow_multi_values`), `radio`, `checkbox`, `email`, `url`,
`users`, `items` (Biobank `Sample` IDs), `experiments` (ELN entry IDs),
`compounds` (`Compound` IDs, phase 4), `uploads` (attachment IDs).
`core/services/notebook_metadata.py` validates schema and values, resolves
linked IDs against the user's permissions, and copies the schema from the
template on create (values kept unless `blank_value_on_duplicate`).
Rendered as grouped form fields in the entry (mockup 02).

### 3.2 Template builder and settings (mockup `03-eln-templates`)

Template list and editor: defaults, permissions, extra-field table with
add/reorder/edit/delete and group management, optional raw JSON editor
(jsoneditor). Category and status management per research group with drag to
reorder. Only group coordinators and superusers manage group settings.

### 3.3 Steps

`NotebookStepGroup` (`entry` or `template`, `title`, `ordering`) and
`NotebookStep` (`entry` or `template`, `group`, `body`, `ordering`, `is_done`,
`done_at`, `done_by`, `deadline`, `notify_deadline`). Exactly one of entry or
template is set (check constraint). Templates copy steps into new entries.
Management command `notify_step_deadlines` (cron) emails owners of steps due
in the next 24 h, once per step. Progress shown in list and view.

### 3.4 Entry links and pins

`NotebookEntryLink` (`entry`, `linked_entry`, `created_by`, `created_at`,
unique pair, no self link) shown in both directions. Pins from 1.6 if not done.

## Phase 4 — Tools

### 4.1 Compounds

`Compound`: `name`, `iupac_name`, `molecular_formula`, `molecular_weight`,
`smiles`, `inchi`, `inchi_key` (unique, nullable), `cas_number` (unique,
nullable), `pubchem_cid` (unique, nullable), optional external IDs (ChEBI,
ChEMBL, DrugBank, KEGG, Wikidata), and boolean hazard flags (corrosive,
explosive, flammable, gas under pressure, hazardous to environment, hazardous
to health, serious health hazard, oxidising, toxic, radioactive, antibiotic,
antibiotic precursor, drug, drug precursor, explosive precursor, CMR, nano,
controlled), timestamps, `created_by`. `Chemical.compound` FK (nullable) with a
data migration that matches existing chemicals by CAS. `NotebookCompoundLink`.
`core/services/pubchem.py` imports by CID, CAS or name through the PubChem
PUG REST API with timeouts and caching, following the style of
`core/services/sample_enrichment/ncbi_taxonomy.py`.

### 4.2 Structure editor

Page with Ketcher standalone (served as static files); save as new `Compound`
or search existing by exact InChIKey. Optional notebook block type
`chemical_structure` storing SMILES and MOL.

### 4.3 Inventory

`StorageLocation.capacity` (nullable) and `StorageLocationMove` history
(location, old parent, new parent, user, date). `ChemicalStorageAssignment`
(chemical container → location, quantity, unit) replacing free-text location.
Capacity check before assigning. Storage tree with occupancy bars and an Excel
export (openpyxl).

### 4.4 OpenCloning

Deployment files: container `manulera/opencloning` (read-only, no capabilities),
Apache reverse proxy at `/opencloning` behind the existing auth guard, feature
flag `BIOBANK_OPENCLONING_ENABLED`. Page that embeds it and a save action that
stores the resulting GenBank as a `MolecularSequence` linked to an entry.

## Phase 5 — Integrity and export

### 5.1 Lock, sign, timestamp

`NotebookSignature` (entry, user, meaning approve|review|author, revision,
content hash, signed_at); signing locks the entry and makes attachments
immutable. `NotebookTimestamp` (entry, revision, sha256 of the exported PDF,
TSA URL, token file, created_at) using an RFC 3161 TSA configured by settings.
`NotebookAttachment.sha256` computed on upload.

### 5.2 Export and import

PDF export of an entry (blocks, extra fields, steps, links, signatures).
`.eln` export and import (RO-Crate 1.2: `ro-crate-metadata.json` plus files),
mapping `metadata.extra_fields` unchanged so files exchange with eLabFTW.
