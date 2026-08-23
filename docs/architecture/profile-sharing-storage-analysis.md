# B3 LIMS identity, sharing, storage, and analysis architecture

Status: Proposed implementation baseline
Date: 2026-08-23

## Context

B3 LIMS uses Apache PAM authentication, Django authorization, PostgreSQL, broker-managed filesystems, Slurm, and immutable releases.

The platform must support scientific profiles, sharing outside the owner's group, Samples, ELN, Molecular Registry, Jupyter, Data Analysis, and future Galaxy integration.

## Audited baseline

- One active Profile route.
- Three active Sample sharing routes.
- No active Collection membership route.
- `SampleAccessGrant` has a direct Sample foreign key.
- Ten Django file fields exist.
- Four fields use managed user-home storage.
- Six fields use central media storage.
- Forty-two relevant text or JSON fields contain structured records.
- Collection membership is broken, dormant, and unrouted.
- Eight planned Profile attributes are absent.

## Identity and Profile

PAM remains the authentication authority. B3 LIMS does not manage passwords and does not expose a visible logout action.

Django `User` stores username, first name, last name, email, and active state.

A one-to-one `UserProfile` stores preferred name, institution, department or laboratory, ORCID, phone, expertise, biography, visibility, and update timestamp.

Research-group membership remains relational. Roles are scoped to a Biobank or resource through models such as `BiobankUserRole`.

Explicit sharing never changes Unix group membership.

## Generalized sharing

`SampleAccessGrant` remains operational during migration but is not the generic model.

Introduce `ResourceAccessGrant` with content type, object identifier, user or ResearchGroup principal, `view`, `edit`, or `manage` access, grantor, timestamps, expiration, and revocation metadata.

Supported content types use an explicit allowlist.

Authorization combines ownership, ResearchGroup access, Biobank roles, explicit grants, expiration, administrator override, and audit events.

An outside collaborator may receive a grant without joining the owner's Unix or ResearchGroup membership.

Existing Sample grants migrate only after equivalence tests preserve current behavior.

## Storage tiers

### User-owned scientific artifacts

Canonical root:

`/home/<username>/biobank/`

Logical domains:

- `data/samples/`;
- `lab_tools/eln/attachments/`;
- `lab_tools/molecular/alignments/`;
- `lab_tools/molecular/structures/`;
- `lab_tools/jupyter/notebooks/`;
- `analysis/inputs/`;
- `analysis/workflows/`;
- `analysis/results/`;
- `analysis/reports/`;
- `analysis/logs/`.

Only reviewed storage services and brokers resolve physical paths.

### Shared institutional artifacts

Shipment documents, Chemical Registry documents, group exports, controlled templates, and retention records remain in protected shared filesystem storage. Their lifecycle must not depend on one user's home.

### PostgreSQL records

PostgreSQL remains authoritative for identity, ownership, memberships, grants, audits, lifecycle state, relative paths, checksums, MIME types, ELN text, protocols, curated sequences, annotations, taxonomy, external identifiers, and compute-job metadata.

## File-field decisions

Already managed in user homes:

- `SampleFile.file`;
- `NotebookAttachment.file`;
- `MolecularAlignment.file`;
- `MolecularStructure.file`.

Migration candidates:

- `SampleImportBatch.original_file` moves to the submitter's home;
- `HostRange.plaque_morphology` moves after defining a deterministic owner.

Protected shared storage:

- `ChemicalFile.file`;
- `ShipmentDocument.generated_file`;
- `ShipmentDocument.signed_file`;
- `ShipmentDocumentFormData.signed_file`.

Every migration preserves identity, checksum, filename, ownership or custody, access behavior, and rollback evidence.

## ELN, Molecular Registry, and Jupyter

ELN text, protocols, blocks, links, and structured snapshots remain in PostgreSQL. Attachments remain in the user's home.

Curated molecular sequences may remain in PostgreSQL. Complete genomes, raw reads, alignments, structures, and generated results are filesystem artifacts.

A Jupyter notebook has a canonical `.ipynb` file in the user's home. PostgreSQL stores metadata, relative path, checksum, state, and job relationships.

`JupyterNotebook.notebook_json` may remain temporarily for compatibility or snapshots but not as the only canonical operational copy.

## Filesystem authorization

PostgreSQL is the authorization source. The broker enforces file operations.

POSIX ACLs protect the owner, application service, and reviewed administrators.

Initial cross-group sharing may stream authorized files through B3 LIMS without direct shell access to the owner's home.

Direct recipient ACLs require transactional creation and reliable revocation.

## Data Analysis

Introduce:

- `AnalysisProject`;
- `AnalysisWorkflow`;
- `AnalysisRun`;
- `AnalysisArtifact`;
- `ComputeJob`.

PostgreSQL stores metadata and state. Inputs, workflows, outputs, reports, figures, notebooks, and logs remain in the user's `analysis/` directory.

The first reference workflow supports a whole-genome use case.

Slurm records job ID, partition, resources, submitter, timestamps, state, exit code, working directory, provenance, and artifacts.

Future Galaxy integration stores external workflow, history, dataset, and job identifiers without duplicating Galaxy-managed datasets in PostgreSQL.

## Implementation order

1. Add UserProfile and redesign Profile.
2. Introduce the centralized authorization service.
3. Add ResourceAccessGrant and equivalence tests.
4. Migrate Sample grants.
5. Complete user-home storage for user-owned artifacts.
6. Rebuild Collection membership.
7. Redesign Sample Edit.
8. Review taxonomy and external database enrichment.
9. Rebuild Workspace metrics, reports, and quick actions.
10. Implement Data Analysis and Slurm submission.
11. Add optional Galaxy integration.

## Refactoring policy

Large modules are refactored incrementally with the feature that needs them.

Priorities include Sample views, ELN and notebook views, molecular workspace JavaScript, plasmid-map JavaScript, and the main notebook template.

Refactoring preserves routes, authorization, storage contracts, and regression coverage.

## Security invariants

Every phase preserves PAM authentication, no visible logout, test database isolation, path containment, broker allowlists, symlink protections, checksums, explicit ownership, auditable grants, non-force pushes, immutable releases, and rollback evidence.
