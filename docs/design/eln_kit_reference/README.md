# ELN redesign mockups

Visual reference for the ELN, Lab Calendar and Tools work inspired by eLabFTW.
These files are design references only: the data is fictional and nothing here
is wired to Django.

| Screen | HTML (interactive) | PNG | Implemented in |
| --- | --- | --- | --- |
| ELN entry list | `01-eln-entry-list.html` | `01-eln-entry-list.png` | Phase 1 (step 1.6) |
| ELN entry view | `02-eln-entry-view.html` | `02-eln-entry-view.png` | Phases 1 and 3 (steps 1.7, 3.1, 3.3) |
| Templates and settings | `03-eln-templates.html` | `03-eln-templates.png` | Phase 3 (step 3.2) |
| Lab Calendar | `04-lab-calendar.html` | `04-lab-calendar.png` | Phase 2 (step 2.2) |
| Compounds, structure editor, inventory | `05-tools-compounds.html` | `05-tools-compounds.png` | Phase 4 |

Open the HTML files directly in a browser; they work offline. Buttons, tabs,
step checkboxes, the status selector, the extra-field builder and the booking
conflict fix are clickable.

Orange "eLabFTW" badges mark features that come from eLabFTW; blue badges mark
features the Biobank already has. Remove the badges when implementing.

## Conventions to keep

- Layout: existing `internal/common/base.html` shell (navy sidebar, Bootstrap 5.3,
  Bootstrap Icons, Inter).
- Colors: page `#f6f8fa`, sidebar `#002b45`, primary `#0b66b2`, borders `#dfe5ec`,
  muted text `#5b6672`.
- Category and status colors are data (stored on `NotebookCategory` and
  `NotebookStatus`), not CSS constants.
- Interface text is English (see `docs/development/language_policy.md`).

The full design spec is in `docs/development/eln_elabftw_roadmap.md`.
