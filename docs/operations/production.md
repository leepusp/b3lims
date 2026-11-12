# Production deployment, backups and governance

This page keeps the operational guidance that used to be in the README. It applies to a server that other people rely on (the institutional profile `biobank.settings`, or `biobank-local` on a lab server).

## Environment variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django cryptographic signing key |
| `DEBUG` | Enables or disables Django debug mode |
| `ALLOWED_HOSTS` | Comma-separated allowed host names |
| `DATABASE_URL` | Django database connection URL |
| `BIOBANK_MEDIA_ROOT` | Uploaded-file root |
| `BIOBANK_STORAGE_ROOT` | Root for persistent institutional storage |
| `BIOBANK_NOTEBOOK_STORAGE_MODE` | Notebook storage strategy |
| `BIOBANK_NOTEBOOK_ROOT` | Notebook artifact root |
| `BIOBANK_GROUP_ROOT` | Research-group storage root |
| `BIOBANK_INVENTORY_ROOT` | Inventory artifact root |
| `BIOBANK_SAMPLE_DOCS_ROOT` | Sample-document root |
| `BIOBANK_MANIFESTS_ROOT` | Generated manifest root |
| `BIOBANK_SHARED_ROOT` | Shared artifact root |

Use absolute, access-controlled paths in production. Values in `.env.example`
are development examples only.

## Static and persistent files

Source templates and static assets live under `core/interfaces/` and
`static/`. Build collected assets with:

```bash
python manage.py collectstatic --noinput
```

The generated `staticfiles/` directory must not be committed.

Uploaded sample files, notebook attachments, shipment documents, signed
documents, and import files are persistent data. They must:

- live outside the Git repository in production;
- use restrictive ownership and permissions;
- be backed up independently from PostgreSQL;
- be served only through an authorization-aware mechanism;
- never be exposed by an unrestricted static-file alias.

Database backups do not include uploaded files.

## Permissions and data governance

Authorization logic is centralized under `core/permissions/`. Supported
workflows include biobank-level and collection-level roles, ownership,
research-group membership, superuser administration, and visibility filtering.

New views, downloads, exports, and file-serving endpoints must apply the
appropriate permission helper. Hiding a link in a template is not an
authorization control.

Do not add real sample records, patient or participant information, scientific
metadata, user lists, shipment documents, signed forms, credentials, or
database dumps to fixtures, tests, screenshots, issues, or commits.

## Production deployment

A production installation should provide:

1. a dedicated application account and group;
2. an isolated Python environment;
3. a PostgreSQL database and restricted database role;
4. an environment file readable only by the application service;
5. persistent file storage outside the source checkout;
6. Gunicorn or another supported WSGI server;
7. a TLS-enabled reverse proxy;
8. collected static assets;
9. authorization-aware delivery of protected uploads;
10. separate, verified backups for PostgreSQL and persistent files.

Typical deployment validation:

```bash
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py collectstatic --noinput
```

Review migration plans and back up PostgreSQL and persistent files before
applying production schema changes. Deployment-specific hostnames, IP
addresses, users, paths, service definitions, authentication providers, and
backup schedules belong in private operational documentation.

## Backup and restore principles

PostgreSQL should be backed up with `pg_dump` in custom format. Persistent files
require a separate filesystem-level backup. Each backup should have an
integrity checksum and a retention policy.

A restore must first be tested against a temporary database and temporary file
root. Database and file backups should be selected from compatible points in
time. Stop write traffic and obtain explicit operational approval before a
production restore.

See `docs/operations/` for generic implementation guidance.

## Development workflow

Create focused branches from the current `main` branch:

```bash
git fetch origin --prune
git switch main
git pull --ff-only
git switch -c feature/short-description
```

Before opening a pull request:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
git status --short
```

Keep commits focused. Do not combine generated runtime data, local backups, or
unrelated production changes with application code.

