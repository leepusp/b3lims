# Local installation, repository cleanup and ELN ideas

Review of Nov 11, 2026, updated Nov 12, 2026. Nothing here changes behaviour; it lists what was found and
proposes an order of work. Status marks as in `roadmap_checklist.md`: `[ ]` open.

## 1. Repository and release flow (done)

- [x] The public repository is `leepusp/b3lims`. Its `main` carries the full current code
      (the former `feature/schema-release` line), with a clean history.
- [x] Releases are tagged (`release-p102` ... `release-p108`; later releases are tagged as
      they are deployed).
- [x] Single flow: dev repo, then patch, then DaVinci (`git am` and the immutable-release
      deploy), then `git push origin main` to `leepusp/b3lims` on every deploy.
- [x] The old `leepusp/biobank` repository is obsolete. Its extra branches were either
      already inside `main` or test work (`public-shipments-quarantine-v1`, the
      Sep 7 shipments quarantine experiment), and none of them is needed. It is to be made
      private or deleted by an organization owner; nothing in the project depends on it.
- [x] The local branch `feature/bench-app` (Lab Calendar / equipment booking) was merged
      through `release/b3-bench-home`.


## 2. What already exists for a local installation

- `biobank/standalone_settings.py`: SQLite, local Django login (PAM middleware removed),
  localhost only, no URL prefix, persistent root `~/.biobank-local`.
- Checked today: `manage.py check` passes and `manage.py migrate` applies all 118
  migrations on an empty SQLite database with this profile.
- Vendored frontend assets (`feature/offline-assets`): the templates load no CDN scripts.
- Postgres-only features: none found (`select_for_update` is accepted and ignored by
  SQLite, so concurrency guarantees weaken; see 3.4).

## 3. What still ties the product to DaVinci

| Area | Where | Local replacement |
|---|---|---|
| Login by PAM and Unix groups | `core/middleware/pam_remote_user.py`, `BIOBANK_PAM_*` | Django auth (done in standalone); optional OIDC/LDAP later |
| Per-user folders as real Unix users, written through `sudo` runners | `lab_tools_storage.py`, `sample_data_storage.py`, `jupyter_server.py` | A storage backend interface: `UnixHomeBackend` (DaVinci) and `LocalFolderBackend` (plain directories under `BIOBANK_LOCAL_ROOT`) |
| Jupyter started by Slurm (`BIOBANK_JUPYTER_*`, partitions `basic`/`max50`, nodes `n01`, `gn0x`) | `jupyter_server.py` (1001 lines), `jupyter_*.py` views | Jupyter becomes a client of the Biobank: token-based read API plus a `biobank_client` package; the server launcher is optional and only enabled on HPC |
| Reference indexes in `/scratch/global/databases/...` (taxonomy, GTDB, ICTV) | `taxonomy_local.py`, `gtdb_local.py`, `ictv_local.py`, `BIOBANK_REPOSITORY_ROOT`, `BIOBANK_TAXONOMY_DIR` | `BIOBANK_DATA_DIR` default under the local root; a `build_*_index` command per source and a "Reference data" admin page that downloads and builds them |
| Zenodo sandbox, NCBI, PubChem, RCSB, AlphaFold, OpenStreetMap tiles | services | Already optional; each needs a clear offline message and an on/off setting |
| Apache, systemd, fail2ban, PAM, sudoers files | `deploy/` | Keep for DaVinci. Local installation is done: `pip`/`pipx` with the `biobank-local` wizard, and Docker Compose |
| Hard-coded defaults pointing at `/home/public/apps/biobank/...` and `/scratch/global/...` | `biobank/settings.py` | Standalone profile already defaults to the local root; institution values (hosts, storage admins, public URL) are now `BIOBANK_*` variables. Remaining: path defaults in `settings.py` |

### 3.4 Database

- Keep PostgreSQL for DaVinci; SQLite for single-user installs; PostgreSQL through
  `DATABASE_URL` for a lab server. The `DATABASES` setting already reads `DATABASE_URL`.
- Test the suite on both engines in CI. `select_for_update` and the writer lock in
  `storage_writer_lock.py` need a look: on SQLite they must degrade to a database-level
  lock instead of silently doing nothing.
- Migrations are additive, so one history serves both engines.

## 4. Repository cleanup

- [x] `db.sqlite3` in the repository root is git-ignored (not tracked); keep it out of release packages.
- [x] `requirements.txt`: duplicate `django-import-export` entry removed.
- [ ] Split requirements into `requirements/base.txt`, `hpc.txt` (Jupyter/Slurm extras)
      and `dev.txt`.
- [ ] Very large modules to split: `views/internal/samples/views.py` (4.9k lines),
      `views/internal/lab_tools/notebook.py` (4.8k), `models/lab_tools/notebook.py` (1.3k,
      mixes notebook, molecular and Jupyter models), `rcsb_pdb.py` (1.2k).
- [ ] Storage "v8..." file names (`storage_workspaces_v8.py`, `..._v8146c2.py`) carry
      version tags in module names; rename once the storage rework settles.
- [ ] Legacy storage projection/sync (`storage_legacy_*.py`, `Sample.storage_location` text)
      and legacy notebook tags (kept for rollback, to be dropped): schedule the removal.
- [ ] Lint pass (pyflakes reports many unused imports, for example in
      `views/internal/samples/views.py`).
- [ ] `docs/transport` and `docs/design/eln_kit_reference` hold reference material; move
      out of the code tree or into a `docs/reference` folder.
- [ ] 269 test files / 2,571 tests run in about 35 s: keep this as the gate for both
      profiles (`test_settings` and `standalone_settings`).

## 5. Beyond microorganisms: sample types

Today `Sample.sample_type` is free text and the biological detail lives in
`core/models/samples/subtypes.py` (bacteria and similar). The sample table templates
(p99/p100) already define columns per type in code (`sample_tables.py`). Proposal:

- [ ] A `SampleType` registry (name, slug, ID prefix, icon, biosafety default, required
      fields, extra-field schema) editable by superusers; the built-in four become rows.
- [ ] New built-in types: Cell line (species, tissue, passage, mycoplasma status, authentication
      such as STR), Primary cell/tissue, Nucleic acid (DNA/RNA extract, concentration, A260/280),
      Protein/antibody (target, clone, host), Reagent-like biological material, Sequencing library,
      Environmental/clinical specimen (collection event, matrix, preservation), Dataset/file
      (a "digital sample" with a checksum and a location instead of a position).
- [ ] Extra fields per type reuse the existing custom-field layout (migration 0101), so a new
      type needs no new table.
- [ ] Templates, import, export, validation and ID prefixes read the registry instead of
      the hard-coded lists.
- [ ] Taxonomy lookup applies only to types that have an organism; other types use their
      own vocabularies (Cellosaurus, UBERON, ChEBI) as optional offline indexes.

## 6. ELN ideas from the references

Sources: Chemotion ELN (UI "Adjusting views", Details/Analyses, element model,
LabIMotion), LabCollector ELN add-on. The B3 ELN already has: author signature with
lock, amend and deviations (`notebook_trace.py`), revisions, templates stored in the
database, backlinks to samples/reagents/molecules/Jupyter, sharing with groups, favourite
tags, step groups, custom fields, Zenodo export. Ideas that are still missing:

From Chemotion:
- [ ] Per-user list columns and detail tabs: drag items between "shown" and "available"
      (entries list, samples list, registry cards); stored in the user profile.
- [ ] Collapsible side bars and a one-click full-screen detail window.
- [ ] Analyses: entry or sample, then analyses, then datasets, then attachments; file
      conversions produce more attachments (spectra, chromatograms, gel images).
      Start with a generic "Analysis" block that groups files and metadata per
      measurement, with instrument and method fields.
- [ ] Wellplate / screen element: a plate map (the storage grid drawing can be reused) with
      one Sample per well and results per well; screen = a set of plates.
- [ ] Research plan: an entry type that mixes text, tables, images and links to other
      elements (we have blocks; add a plan template and a timeline).
- [ ] Inbox: a folder where instrument files arrive (or are dropped) and are attached
      to entries later (Chemotion "Inbox", "folder collector").
- [ ] Generic modules builder (LabIMotion): define a new entry module with typed fields
      and publish it as a template; we have the field builder, extend it to repeatable
      groups and units.
- [ ] Repository transfer: publish selected entries/datasets with metadata (JSON-LD,
      DOI through Zenodo); a review step before publishing.
- [ ] History tracker for tables with variations (reaction variations); for us: per-cell
      history in entry tables.

From LabCollector:
- [ ] Review and witness workflow: second signature with meaning (witnessed, reviewed,
      approved), signature certificate with name, title and role, searchable by those.
- [ ] Duplicate a protocol page as a linked sub-page per batch (repeated assays such as
      ELISA), keeping the link to the parent protocol.
- [ ] Template preview before use, and locked steps in validated templates.
- [ ] Integrated spreadsheets with templates and a diagram designer (we have tables and
      Whiteboard-like artifacts; add a simple diagram block).
- [ ] Report builder: compile several entries into one print/PDF, with the audit trail.
- [ ] Data link: reference any LIMS record (sample, equipment, reagent) inside a page
      with a live card (done for samples; extend to equipment and storage positions,
      which is "hub, part 2" in the checklist).
- [ ] Structure and substructure search in the chemical module (structure_search exists;
      expose it in the ELN).

## 7. Suggested order

1. ~~Repository: reconcile GitHub, tag releases, clean branches~~ (done).
2. Settings: remaining path defaults, `requirements` split, CI on PostgreSQL in addition
   to SQLite (2 to 3 days). CI on SQLite, install and Docker already run.
3. Storage backend interface and `LocalFolderBackend` (the biggest coupling; 1 week).
4. Biobank read API with tokens and the `biobank_client` package; Jupyter becomes optional
   (1 to 2 weeks; also gives notebooks on a laptop).
5. Reference data manager (download and build indexes from the interface).
6. `SampleType` registry and the first new types (cell line, nucleic acid, dataset).
7. ELN: per-user columns and tabs, analyses/datasets, witness workflow, wellplate.
8. ~~Local installer: Docker Compose and a pip/pipx package with a first-run wizard~~
   (done; optional data downloads from the wizard are still open).
