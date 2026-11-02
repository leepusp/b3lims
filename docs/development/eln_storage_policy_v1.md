# B3 ELN — Storage Policy v1

## Objective

Keep unpublished scientific data under the owning
researcher's established project directory in their
Unix home, while using the centralized eLabFTW service
for explicitly published experiment versions.

## Storage ownership

### Private draft

- Source of truth: user's existing project directory.
- Store experiment body, steps, revisions and attachments
  within the authorized project namespace.
- Do not send draft contents to the central eLabFTW API.
- Do not store draft contents in the central MySQL database.
- Do not put scientific draft contents into shared logs.
- Never derive a filesystem path directly from a URL or
  user-supplied project name.

### Shared project

- A shared project is not automatically public.
- The authoritative project files remain in the
  authorized project directory.
- Collaboration requires an explicit access policy.
- Sharing must not trigger publication.

### Published version

- Publication is an explicit, authorized operation.
- A validated snapshot is sent to the eLabFTW REST API.
- The central eLabFTW database stores the published record.
- Published attachments use institutional storage.
- Publication preserves the private source.
- Record source version, checksum, publication status,
  remote ID, author and publication timestamp.
- Repeated submissions must not create duplicates.

## Filesystem integration

Reuse the existing Biobank user-home storage service
and its privileged storage broker.

The final project-relative ELN namespace must be
defined after verifying the existing project layout
and the broker's supported operations.

Do not grant unrestricted home-directory access
to apache or ladmin.

Never allow symlink traversal, path escape, cross-user
access or direct arbitrary filesystem operations.

Use atomic writes, ownership verification and restrictive
permissions. Failed saves must preserve existing data.

## Application integration

- Django enforces user and project authorization.
- Private drafts use the user-home storage adapter.
- Published records use eLabFTW REST API v2.
- MySQL remains owned and managed by eLabFTW.
- No direct Django writes to eLabFTW MySQL tables.
- The existing Notebook is preserved unchanged.
- The feature remains disabled until integration tests pass.

## Important limitation

A native eLabFTW private experiment is still stored
in its configured MySQL database.

Therefore, central eLabFTW private permissions alone
do not satisfy this storage policy.

Private editing functionality must be implemented
against the user-home storage contract, or supported
by another explicitly approved isolated architecture.

Do not claim the complete native eLabFTW editor works
with home-only persistence before this is demonstrated.

## Acceptance tests

- Private save never calls the central eLabFTW API.
- Private save never writes the central MySQL database.
- Cross-user reads and writes are denied.
- Path traversal and symlink escape are denied.
- Existing project ownership is preserved.
- Sharing does not publish.
- Publishing requires explicit authorization.
- Published content matches the approved source hash.
- Failed publication preserves the private version.
- No private content is exposed through a public index.
- All existing Biobank tests continue to pass.

## Production requirements

Canonical repository:
  /home/ladmin/git/biobank

Canonical validation URL:
  https://davinci.icb.usp.br/b3lims

No alternate browser endpoint, localhost preview,
or replacement of the existing Notebook.

No database migrations or deployment are authorized
by this document alone.
