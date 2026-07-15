# Biobank

Biobank is a Django-based laboratory information management platform for
biological sample collections. It was developed in the context of CEPID B3 —
the Center for Research, Innovation and Dissemination in Bacterial and
Bacteriophage Biology — to improve traceability, governance, biosafety, and
collaboration around biological assets.

The project is under active development. The repository contains application
source code, database migrations, templates, static assets, and generic
operational documentation. Runtime databases, uploaded files, credentials,
backups, and institution-specific configuration must remain outside Git.

## Main capabilities

- Multiple biobank repositories and research-group associations
- Role-based access at biobank and collection level
- Biological sample registration, classification, relationships, and lineage
- Collections, tags, keywords, QR codes, and printable labels
- Hierarchical storage locations and inventory assignments
- Batch sample intake and spreadsheet import
- Sample-associated scientific files and molecular sequences
- Electronic laboratory notebook and protocol content
- Chemical inventory, governance, and stock movements
- Shipment planning, documentation, traceability, receipt, and package labels
- Biosafety, GMO/CIBio, CQB, MTA/TTM, and transport-document workflows
- Public collection and shipment submission interfaces
- PostgreSQL and uploaded-file backup status integration

## Architecture

```mermaid
flowchart TD
    Client["Web browser"] --> Proxy["Reverse proxy / web server"]
    Proxy --> App["Gunicorn / Django"]
    Proxy --> Static["Collected static assets"]
    App --> Database["PostgreSQL"]
    App --> Storage["Protected persistent file storage"]
    App --> Backup["Database and file backup workflows"]
```

The application can run with Django's development server for local work.
Production deployments should use a WSGI server such as Gunicorn behind a
reverse proxy. PostgreSQL is the authoritative production database. Uploaded
files and other persistent artifacts are stored separately from the source
checkout.

## Technology stack

- Python 3.12 or newer
- Django
- PostgreSQL for production
- Gunicorn
- Django REST Framework
- django-import-export
- django-filter
- Biopython, pandas, NumPy, Matplotlib, and openpyxl
- HTML, CSS, and JavaScript templates served by Django

The current production environment is tested with Python 3.14, Django 6.0, and
PostgreSQL 18. Local development may use SQLite when `DATABASE_URL` is not
configured.

## Repository structure

```text
biobank/
├── biobank/                  # Django project settings, URLs, ASGI, and WSGI
├── core/
│   ├── interfaces/           # Internal and public templates/static sources
│   ├── management/commands/  # Inventory and sample-file maintenance commands
│   ├── migrations/           # Versioned database schema migrations
│   ├── models/               # Domain models grouped by feature
│   ├── permissions/          # Centralized authorization rules
│   ├── services/             # Business and infrastructure services
│   ├── templatetags/         # Custom Django template tags
│   └── views/                # Internal and public request handlers
├── docs/                     # Development and generic operations guidance
├── static/                   # Additional source static assets
├── manage.py
└── requirements.txt
```

Generated `staticfiles/`, local databases, uploaded data, environment files,
logs, backups, and Python caches are intentionally excluded from version
control.

## Local development

### 1. Prerequisites

Install Git and Python 3.12 or newer. PostgreSQL client and server packages are
also required when using PostgreSQL locally.

### 2. Clone the repository

```bash
git clone https://github.com/leepusp/biobank.git
cd biobank
```

### 3. Create a virtual environment

Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 5. Configure the environment

```bash
cp .env.example .env
```

Generate a local secret key with:

```bash
python -c "from secrets import token_urlsafe; print(token_urlsafe(64))"
```

Replace the placeholder in `.env`. Never commit environment files, database
connection strings, credentials, private keys, access tokens, or
institution-specific configuration.

### 6. Initialize the database

For the default local SQLite configuration:

```bash
python manage.py migrate
```

For PostgreSQL, create an empty database and set `DATABASE_URL` before running
the same migration command. For example:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
```

Do not run `makemigrations` as an installation step. New migrations should be
created only when an intentional model change is being developed.

### 7. Create an administrator

```bash
python manage.py createsuperuser
```

### 8. Start the development server

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/> unless a deployment-specific URL prefix is
configured.

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

## Language policy

English is the official language for source-code comments, docstrings,
templates, interface labels, Django messages, migration names, commit messages,
and developer documentation. Existing non-English content should be translated
incrementally when touched.

See `docs/development/language_policy.md`.

## Contributing

Contributions should:

- preserve database and migration history;
- include migrations for intentional model changes;
- reuse centralized permission helpers;
- protect all file and export endpoints;
- avoid real or identifying data in tests and examples;
- document new environment variables and operational requirements;
- include focused validation steps in the pull request description.

## License

This project is developed for academic and scientific work within CEPID B3 —
FAPESP. A standalone software license has not yet been added to the repository.
Contact the project maintainers before redistribution or use outside the
project's research and development context.
