# B3 LIMS — Storage V8/V8.9 Development Status

Date: 2026-10-15

## Canonical source

- Repository: `/home/ladmin/git/biobank`
- Branch: `main`
- Baseline HEAD: `55175af5cff1c915c9be7e84859c6c6d107ae64d`
- Current development changes are in the Git working tree.
- Validation checkpoints are disposable and are not application source code.

## Validated

- Standalone: 19 tests passed, none skipped.
- Django SQLite: 1,639 tests run, 21 skipped, zero failures.
- Storage JavaScript existing suite: 20 tests passed.
- Movement comparison HTTP regression: 29 tests passed.
- PostgreSQL full regression before V8.9 UI additions:
  1,633 tests run, 19 skipped, zero failures.
- PostgreSQL legacy migration rehearsal:
  core 0086 to 0090 passed for compatible historical fixtures.
- Case-insensitive active-position conflicts block migration.
- Legacy assignment and movement rows remained preserved.
- No new migration required for V8.9 UI additions.

## Storage V8.9 implementation

- Workspace-scoped hierarchy map.
- Authorized inventory data reused from Storage Explorer.
- Read-only Before/After comparison for:
  container moves, individual Sample moves, and bulk moves.
- HTTP coverage for authorized and denied previews.
- Existing movement execution services unchanged.

## Pending before online validation and rollout

- Review and consolidate the uncommitted Git changes.
- Verify V8.9 interactive behavior with a real browser.
- Re-run PostgreSQL regression with current V8.9 source.
- Audit real database occupancy conflicts before migrations.
- Review the existing root-owned release deployment.
- Back up the live database and application state.
- Publish into the existing biobank.service and URL.
- Verify authenticated online behavior.

## Deployment separation

The existing online service uses:

- WorkingDirectory: `/home/public/apps/biobank/current`
- Service: `biobank.service`
- URL: `https://davinci.icb.usp.br/b3lims/`

The release directory is protected and requires authorized
administrative access. Git working-tree modifications have not
yet been published to the online service.
