# B3 LIMS — Hybrid ELN Architecture v1

## Objective

Integrate the original eLabFTW experiment engine into the
canonical B3 LIMS Django application while adopting the
visual design references from the ELN kit.

The existing Django Notebook remains unchanged during
the experimental phase.

## Sources of truth

- B3 LIMS / PostgreSQL:
  Samples, Storage, Chemicals, Molecular Registry,
  institutional permissions and cross-system links.
- eLabFTW 6.0.9 / MySQL 8.4:
  Experiments, experiment templates, steps, revisions,
  comments, audit trails and native ELN attachments.

Do not duplicate eLabFTW experiment records as new
NotebookEntry objects.

## Integration contract

- Use eLabFTW REST API v2.
- Do not directly modify eLabFTW MySQL tables from Django.
- Associate records through stable external identifiers.
- Enforce Django-side authorization before API operations.
- Preserve user attribution and eLabFTW team permissions.
- Do not share one unrestricted user identity across researchers.
- Do not expose database or API credentials to browsers.
- Do not claim connectivity until an authenticated API call passes.

## User interface

- New Lab Tools > ELN Experimental menu item.
- Existing Notebook stays visible and functional.
- Page templates extend internal/common/base.html.
- English labels and Bootstrap 5.3 conventions.
- First screens: experiment list, detail and templates.
- Kit HTML/PNG files are design references only.
- No dynamic JavaScript evaluator from mockups.
- The feature is disabled by default and restricted to
  explicitly authorized evaluators.

## Runtime

- Original upstream eLabFTW version: 6.0.9.
- MySQL: 8.4, database b3eln_poc.
- Private rootless Podman network.
- Persistent experimental storage:
  /home/public/apps/biobank/storage/eln-experimental
- No externally published container ports.
- No production data migrations.
- Keep upstream source separate from the Django source.
- Review AGPL-3.0 obligations before release.

## Delivery sequence

1. Preserve kit mockups and document the hybrid design.
2. Implement feature gate, isolated URL, view and template.
3. Test evaluator authorization and disabled behavior.
4. Establish secure Django-to-eLabFTW API connectivity.
5. Provision and map experimental identities.
6. Implement read-only experiments and templates.
7. Validate synthetic create/edit/revision workflows.
8. Implement Biobank links to experiment identifiers.
9. Complete backup, restore and resource-limit validation.
10. Deploy through the existing production release workflow.

## Acceptance criteria for initial UI

- Existing Notebook unchanged.
- Experimental URL inaccessible when disabled.
- Unauthorized users cannot access experimental data.
- No dependency on a running eLabFTW service for
  ordinary B3 LIMS routes or tests.
- No new Django schema migration for the initial UI.
- Existing tests remain green.
- Validation uses only:
  https://davinci.icb.usp.br/b3lims

## Reference material

- docs/design/eln_kit_reference/
- docs/development/eln_kit_roadmap_reference.md

The kit roadmap describes a Django-native backend approach.
It is retained as a requirements reference, not as the
implementation authority for this hybrid design.
