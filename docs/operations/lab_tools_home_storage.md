# Per-user Lab Tools storage

Biobank keeps institutional inventory metadata and files in PostgreSQL and
the shared application storage. Personal Lab Tools artifacts are isolated in
the authenticated Linux user's home, following the deployment pattern used
for Galaxy real-user storage.

## Ownership model

For a Linux user `alice`, the managed layout is:

```text
/home/alice/biobank/lab_tools/
├── eln/entries/<entry-id>/attachments/
├── jupyter/notebooks/notebook_<notebook-id>/
├── jupyter/jobs/notebook_<notebook-id>/<run-id>/
├── molecular/records/                 # reserved for molecular file exports
├── exports/
└── tmp/
```

The user and their primary group own these directories and artifacts. Their
mode is `0770` for directories and `0660` for files. A named ACL grants the
trusted `ladmin` application account only the access required to serve and
update the owner's data. No other user receives access.

PostgreSQL remains the source of truth for object identifiers, ownership,
visibility, permissions, relationships, audit metadata, and Jupyter session
state. Inventory/sample uploads remain under `MEDIA_ROOT`. ELN attachments
and Jupyter files are never served directly by Apache; authenticated Django
views enforce object permissions before opening them.

## Slurm identity

The web process does not impersonate a user directly. It invokes two narrowly
scoped, root-owned helpers through sudo. The Jupyter helper validates the
Linux account and every path, then invokes both `sbatch` and `scancel` through
`runuser` as the notebook owner. Consequently, `squeue` and `sacct` show the
real user and use that user's normal Slurm account and limits—not the shared
`biobank` account.

Repository changes, Django checks, migrations, and application tests run as
`ladmin`. Root is used only to install the reviewed helpers and sudo policy or
to repair ownership and ACLs. During a normal launch, Django runs as `ladmin`,
the root-owned helper validates the request, and `sbatch` runs as the notebook
owner through `runuser`.

## Jupyter node and resource selection

The launch form defaults to `Automatic (Slurm decides)`. A user may instead
request one allowlisted compute node: `n01`, `gn01`, `gn02`, or `gn03`. The
selection is validated by the Django view, the Jupyter service, and the
root-owned runner. The runner omits `--nodelist` for automatic placement and
adds exactly one validated `--nodelist=NODE` argument for an explicit choice.

The application and runner share these limits:

- 1–128 CPU cores;
- 1024–1048576 MB of memory;
- `basic`: 1–72 hours;
- `max50`: 1–168 hours.

Slurm remains authoritative for current node state, available resources, and
partition policy.

## Managed and standalone JupyterLab

A running Biobank notebook exposes **Open JupyterLab**. The Notebook and
JupyterLab interfaces use the same authenticated Slurm allocation,
Jupyter server, protected node proxy, token and persistent workspace.
Opening JupyterLab does not submit another job.

The managed server exposes only the authenticated Linux user's home as
its file-browser root. It opens initially at
`biobank/lab_tools/jupyter/notebooks/notebook_<id>/notebook.ipynb`.
The `/workspace` path remains an alias for that notebook workspace.

When the managed session is stopped, **Standalone JupyterLab** links to
the Open OnDemand application. Open OnDemand creates a separate Slurm
allocation and does not replace or resume the Biobank-managed session.

The managed JupyterLab URL must use the protected Biobank node proxy.
It must never link directly to a compute-node port.

## Runtime artifact retention

`jupyter/notebooks/notebook_<id>/` is persistent user data.

`jupyter/jobs/notebook_<id>/<run_id>/` is transient control data. It may
contain the generated submission script, Slurm output, connection
metadata and isolated Jupyter runtime directories.

The protected runner removes a run directory after a terminal status,
an owner-scoped stop, a failed submission, or an explicit protected
`session-cleanup`. Persistent notebook workspaces are not removed by
session cleanup.

Although `$HOME` is the authenticated user's real `/home/<username>`,
Jupyter runtime, configuration, data, cache, Matplotlib and IPython
paths are redirected to `/runtime`. These artifacts remain transient
and are removed with the session run directory.

## Deployment order

1. Back up PostgreSQL, the Git candidate, `/home/public/biobank`, the current
   Jupyter runner, and the applicable sudoers files.
2. Confirm there are no active legacy Biobank Jupyter jobs. Stop them through
   the application before changing the runner.
3. Have an administrator run `deploy/install_lab_tools_home_storage.sh` from
   the reviewed release tree. This is the only step requiring unrestricted
   root access. It installs the reviewed sandbox runtime under
   `/home/public/biobank/runtime/notebook_server.sh`, a root-controlled path
   shared with every compute node. A head-node-only path such as
   `/usr/local/libexec` must not be written into Slurm job scripts. Installation
   accepts only the reviewed isolated-runtime SHA-256
   `2e9144ff1591509eb8c8912d0ce655fac9434f7584ab217afd84f6160b2784a1`
   or the current authenticated-home runtime SHA-256
   `9a576f69972add1e9a455e425964be9d4ab711fc734b66eec37fdf622f31ad0f`.
4. Set `BIOBANK_LAB_TOOLS_PROVISION_ON_LOGIN=1` in the protected Biobank
   service environment, deploy the Django source, then run:

   ```bash
   /home/public/conda/envs/biobank/bin/python manage.py check
   /home/public/conda/envs/biobank/bin/python manage.py makemigrations --check --dry-run
   /home/public/conda/envs/biobank/bin/python manage.py migrate
   ```

5. Preview and apply legacy ELN attachment copies:

   ```bash
   /home/public/conda/envs/biobank/bin/python manage.py migrate_lab_tools_attachments
   /home/public/conda/envs/biobank/bin/python manage.py migrate_lab_tools_attachments --apply
   ```

   Keep the shared sources until backup and user acceptance are complete.
   Only then rerun with `--apply --delete-source` if removal is explicitly
   approved.

6. Restart `biobank.service`, log in as two different real users, and create
   one ELN attachment and one Jupyter notebook for each user.
7. Validate ownership and isolation:

   ```bash
   namei -l /home/USER/biobank/lab_tools
   getfacl -p /home/USER/biobank/lab_tools
   find /home/USER/biobank/lab_tools -maxdepth 5 -printf '%M %u:%g %p\n'
   squeue -o '%.18i %.12u %.20j %.10T'
   ```

   For Jupyter, test both automatic placement and one explicit node. Confirm
   that the job owner is the authenticated Linux user and that the selected
   node appears in `squeue` after allocation.

The runner automatically copies an old notebook workspace from the exact
legacy `user_<django-id>_<username>/notebook_<id>` directory the first time
that notebook is started. It does not delete the old workspace.

## Rollback

Stop new Jupyter starts, restore the backed-up helper and sudoers policy,
restore the application release, and restart `biobank.service`. Migration
0066 changes only the Django storage declaration and field length; legacy
attachment names remain readable, so rolling back does not require moving
files immediately. Do not delete per-user or legacy data during rollback.
