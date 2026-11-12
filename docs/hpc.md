# Optional: clusters, Slurm and the DaVinci-style deployment

A local installation needs none of this. Everything below is optional and off by default.

| Feature | Local default | What to set to enable it |
|---|---|---|
| Sign-in | Accounts in the application | PAM behind Apache: use `biobank.settings` and the files in `deploy/` |
| Jupyter notebooks | Not started by the server (use your own Jupyter and the read API, planned) | `BIOBANK_JUPYTER_*` settings and a runner script; needs Slurm |
| Reference indexes (taxonomy, GTDB, ICTV) | Built on demand into the data folder | `BIOBANK_REPOSITORY_ROOT`, `BIOBANK_TAXONOMY_DIR` to share a folder on a cluster |
| Database | SQLite | `BIOBANK_DATABASE_URL=postgres://...` |
| Web server | Built-in (waitress + WhiteNoise) | Gunicorn behind Apache/Nginx; see `deploy/` and `docs/operations/` |

The production profile used at CEPID B3 on the DaVinci cluster is `biobank.settings`; the
local profile is `biobank.standalone_settings`. Both come from the same code base.
