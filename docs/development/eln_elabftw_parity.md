# B3 ELN — parity checklist with eLabFTW

Source studied: `elabftw/elabftw` master `e60e66b` (2 Nov 2026), read for
behaviour only. eLabFTW is AGPL-3.0: **no code is copied**; every feature
below is reimplemented in Django. The client libraries eLabFTW builds on
are permissively licensed and may be used directly:

| Library | Licence | Used for |
| --- | --- | --- |
| TinyMCE 6.8.x (last MIT line) | MIT | main rich-text editor (menus, tables, templates) |
| jspreadsheet-ce 5 | MIT | spreadsheet with formulas inside entries |
| FullCalendar 6 | MIT | scheduler / Lab Calendar |
| Ketcher 3 | Apache-2.0 | chemical structure editor |
| 3Dmol.js 2 | BSD-3 | molecule / structure viewer |
| jsoneditor 10 | Apache-2.0 | metadata JSON editor |

B3-only modules stay where eLabFTW has no equivalent: Biobank inventory
(samples, collections, shipments), Molecular Registry, Jupyter/Slurm,
workflows/Galaxy, ENA/NCBI/Zenodo submission.

Status: ✅ done · 🟡 partial · ⬜ to do. Release = planned B3 Bench release.

The classic notebook page was retired in 2.1; old links redirect to the entry page.

## Entities

| eLabFTW | B3 | Status | Release |
| --- | --- | --- | --- |
| Experiments | NotebookEntry | 🟡 | — |
| Resources (Items) + Items types | Biobank Samples, Chemicals, Molecular Registry + generic "Resources" for equipment/other | 🟡 | 2.3 |
| Experiment templates | built-in templates in code | 🟡 → editable templates model | 2.2 |
| Resource templates | — | ⬜ | 2.3 |
| Categories + Status (per team, colours) | fixed entry_type/status choices | 🟡 → team-defined categories/status | 2.2 |

## Entry page

| Feature | Status | Release |
| --- | --- | --- |
| Title, date, custom ID, rating, tags | ✅ (1.A) | — |
| Rich text with full menu bar (File/Edit/View/Insert/Format/Tools/Table) | ✅ TinyMCE 6.8 + Biobank menu (2.0) | — |
| Markdown body option | ⬜ | 2.0 |
| Spreadsheet editor with formulas, import/export xlsx/csv | ✅ formulas + CSV export (2.0); xlsx import ⬜ | 2.6 |
| Custom fields (15 types, groups, required, load fields) | ✅ (1.A) | — |
| Field builder modal + JSON editor | 🟡 | 2.2 |
| Steps (groups, deadlines, done by/at) | ✅ (step groups ⬜) | 2.2 |
| Links to experiments | ✅ | — |
| Links to resources (categories) | 🟡 samples/reagents/molecules | 2.3 |
| Compounds (PubChem import, hazards) | 🟡 Chemicals | 2.4 |
| Storage containers on entry | ⬜ | 2.3 |
| Uploads: drag & drop, versions (replace), description, grid/table view, image annotation, QR | 🟡 drag & drop, versions (replace) and description ✅ (2.1); grid view, annotation, QR ⬜ | 2.6 |
| Comments (+ immutable comments) | ✅ comments (2.1); immutable comments ⬜ | 2.5 |
| Draw something / chem editor | ⬜ | 2.4 |
| Exclusive edit mode (lock while editing) | ✅ (2.1) | — |
| Autosave + revisions (restore, compare) | ✅ (2.1) | — |
| Changelog per entry | ⬜ (field-level history; text history is in revisions) | 2.5 |
| Pin / favourite | ✅ (dashboard) | — |
| Duplicate entry | ✅ (2.0) | — |

## Integrity

| Feature | Status | Release |
| --- | --- | --- |
| Lock / unlock | ⬜ | 2.5 |
| Signatures with sig keys (meaning: approval, review…) | ⬜ | 2.5 |
| Trusted timestamp RFC 3161 (configurable TSA) | ⬜ | 2.5 |
| Bloxberg / Keeex anchoring | ⬜ (optional) | later |
| Audit logs (instance-wide) | ⬜ | 2.5 |
| Request actions (ask a colleague to review/sign/timestamp) | ⬜ | 2.5 |

## Permissions and teams

| Feature | Status | Release |
| --- | --- | --- |
| canread / canwrite JSON (base, teams, team groups, users) | 🟡 visibility only | 2.2 |
| Teams, team groups | ResearchGroup | 🟡 | 2.2 |
| Ownership transfer | ⬜ | 2.2 |
| Admin panel (team settings, categories, status, templates) | ⬜ | 2.2 |
| API keys + REST API v2 | ⬜ | 2.6 |
| Webhooks | ⬜ | later |
| Notifications (comment, step deadline, request) | ⬜ | 2.5 |

## Lists, search, dashboards

| Feature | Status | Release |
| --- | --- | --- |
| Entries list with filters, sort, pagination | ✅ (1.A dashboard) | — |
| Batch actions | ✅ status/tag/archive/pin | 2.2 (lock, permissions, export) |
| Advanced search query language (`title:x and status:y`) | ⬜ | 2.2 |
| Extra-field search (`extrafield:Medium:TSB`) | ⬜ | 2.2 |
| Dashboard (recent, steps, bookings, todo) | 🟡 recent, steps, todo ✅; bookings ⬜ | 2.3 |
| Todolist | ✅ personal list on the dashboard (2.1) | — |
| Favourite tags panel | ⬜ | 2.2 |
| Trash / restore (state: deleted) | ⬜ | 2.2 |

## Import / export

| Feature | Status | Release |
| --- | --- | --- |
| PDF (single, multi), with attachments and timestamps | ⬜ | 2.6 |
| .eln (RO-Crate) export and import | ⬜ | 2.6 |
| ZIP, CSV, JSON, QR PNG/SVG/PDF | ⬜ | 2.6 |
| CSV import | ⬜ | 2.6 |
| DSpace / repository deposit | ⬜ → B3 submissions | Phase 6 |

## Tools

| Feature | Status | Release |
| --- | --- | --- |
| Scheduler (bookings, recurrence, rules, export) | 🟡 rules + model (2.1 bench) | 2.3 calendar UI |
| Inventory / storage units | Biobank storage | 🟡 | 2.3 |
| Compounds database | Chemicals | 🟡 | 2.4 |
| Chem editor (Ketcher) | ⬜ | 2.4 |
| 3D molecule viewer | Molecular Registry | 🟡 | 2.4 |
| Procurement requests | ⬜ | later |
| Reports (scheduler, inventory, compounds) | ⬜ | 2.6 |
