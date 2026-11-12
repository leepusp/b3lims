# Install and upgrade

B3 LIMS needs **Python 3.12 or newer** (or Docker). It does not need a cluster, Slurm, PAM accounts or a separate web server.

## Before you start: your system

| System | Recommended route | Prepare it with |
|---|---|---|
| Ubuntu / Debian | Option 1 (pipx) | `sudo apt install -y pipx python3-venv`, then `pipx ensurepath` |
| Fedora / other Linux | Option 1 (pipx) | your package manager's `pipx`, or `python3 -m pip install --user pipx` |
| macOS | Option 1 (pipx) | `brew install pipx python@3.12`, then `pipx ensurepath` |
| Windows 10/11 | **Docker Desktop** (Option 2) or **WSL 2 with Ubuntu** (then follow the Ubuntu line) | Docker Desktop from docker.com; or `wsl --install -d Ubuntu` in PowerShell, then open Ubuntu |
| Any system, no Python 3.12 | Docker (Option 2) | [Docker Engine](https://docs.docker.com/engine/install/) or Docker Desktop |

Check Python first: `python3 --version` must print 3.12 or newer. Ubuntu 24.04 has it; Ubuntu 22.04 and Debian 12 do not, so use Docker, or install Python 3.12 (for example with [uv](https://docs.astral.sh/uv/): `uv tool install --python 3.12 "git+https://github.com/leepusp/b3lims.git"`).

The automated tests run on Linux. On Windows, use Docker Desktop or WSL 2; a plain Windows Python installation is not tested. In WSL, keep the data folder inside the Linux home (the default `~/.biobank-local`), not under `/mnt/c`, and open `http://127.0.0.1:8000` from the Windows browser.

## Option 1: pipx and the setup wizard

```bash
pipx install "git+https://github.com/leepusp/b3lims.git"
biobank-local setup
biobank-local run
```

`pipx` keeps B3 LIMS in its own environment (`pip install` into a virtual environment works too). `setup` asks four questions:

1. **Data folder** (default `~/.biobank-local`): the database, uploaded files, backups and `config.env` live here. It is the only folder you need to back up.
2. **Database**: SQLite (one file, best for one person or a small lab) or PostgreSQL (a lab server with many users).
3. **Administrator**: user name, optional e-mail and a password of at least 8 characters.
4. **Network**: whether other computers will open the installation, and the time zone.

To script it, use `biobank-local setup --non-interactive --admin-user NAME --admin-password SECRET` (`--database-url`, `--allowed-hosts`, `--time-zone`, `--demo` are also available).

## Option 2: Docker Compose

```bash
git clone https://github.com/leepusp/b3lims.git && cd b3lims
BIOBANK_ADMIN_PASSWORD='choose-a-long-password' docker compose up -d
```

The first start creates the installation from environment variables; later starts only bring the database up to date. Data lives in the `biobank-data` volume. With PostgreSQL:

```bash
BIOBANK_ADMIN_PASSWORD=... BIOBANK_DATABASE_URL=postgres://biobank:biobank@db:5432/biobank \
  docker compose --profile postgres up -d
```

## Option 3: from source

```bash
git clone https://github.com/leepusp/b3lims.git && cd b3lims
python -m venv .venv && . .venv/bin/activate
pip install -e .
biobank-local setup
```

## Letting the rest of the lab use it

By default B3 LIMS listens on `127.0.0.1` (this computer only). To open it to your network:

```bash
biobank-local run --host 0.0.0.0
```

and, during `setup` (or in `config.env`), give the name people will type: `BIOBANK_ALLOWED_HOSTS=biobank.mylab.example,192.168.1.20`. If they reach it through an HTTPS reverse proxy (Caddy, Nginx, Apache), also set `BIOBANK_CSRF_TRUSTED_ORIGINS=https://biobank.mylab.example`. Use HTTPS whenever people sign in over a network you do not control.

## Backups

```bash
biobank-local backup                 # writes ~/.biobank-local/backups/biobank_YYYYMMDD_HHMMSS.tar.gz
```

The archive holds the database folder (SQLite), uploaded files and `config.env`. With PostgreSQL, also run `pg_dump -Fc` (the archive only notes this). To restore, unpack the archive over an empty data folder and run `biobank-local doctor`. Test a restore before you need it.

## Upgrading

```bash
pipx upgrade biobank-lims            # or: git pull && pip install -e .   /   docker compose pull && up -d --build
biobank-local migrate                # updates the database; never touches accounts
```

Take a backup first.

## Troubleshooting

| Problem | What to do |
|---|---|
| `biobank-local: command not found` | `pipx ensurepath`, then open a new terminal |
| The page has no styling | `biobank-local migrate` (it also collects the web files) |
| `Bad Request (400)` from another computer | add the name or address you typed to `BIOBANK_ALLOWED_HOSTS` in `config.env` and restart |
| "CSRF verification failed" behind a proxy | set `BIOBANK_CSRF_TRUSTED_ORIGINS` to the public `https://` address |
| Anything else | `biobank-local doctor` checks the settings, the database and the free disk space |
