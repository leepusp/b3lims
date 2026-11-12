"""``biobank-local``: install, configure and run Biobank on one computer.

    biobank-local setup      guided first-time installation (a short wizard)
    biobank-local run        start the web application
    biobank-local createuser add another administrator
    biobank-local migrate    update the database after installing a newer version
    biobank-local backup     copy the database and uploaded files
    biobank-local doctor     check the installation

The commands use the standalone profile (``biobank.standalone_settings``): a local
database, local accounts and plain folders. Nothing here needs an HPC cluster, Slurm,
PAM accounts or a web server; those stay optional (see ``docs/hpc.md``).
"""

import argparse
import getpass
import os
import secrets
import shutil
import sys
import tarfile
from datetime import datetime
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".biobank-local"
CONFIG_NAME = "config.env"


def resolve_root(value=None):
    return Path(value or os.environ.get("BIOBANK_LOCAL_ROOT") or DEFAULT_ROOT).expanduser().resolve()


# ---------------------------------------------------------------- configuration

def read_config(root):
    path = Path(root) / CONFIG_NAME
    values = {}

    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()

    return values


def write_config(root, values):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / CONFIG_NAME
    lines = ["# Written by `biobank-local setup`. Edit and restart to change a setting."]
    lines += [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        path.chmod(0o600)  # holds the secret key
    except OSError:
        pass

    return path


def activate(root, config=None):
    """Point the process at the standalone profile and load the saved settings."""
    root = resolve_root(root)
    os.environ["BIOBANK_LOCAL_ROOT"] = str(root)
    os.environ["DJANGO_SETTINGS_MODULE"] = "biobank.standalone_settings"

    for key, value in (config if config is not None else read_config(root)).items():
        os.environ.setdefault(key, value)

    import django

    django.setup()

    return root


def manage(*args, **options):
    from django.core.management import call_command

    call_command(*args, **options)


# ---------------------------------------------------------------- the wizard

def ask(question, default="", secret=False, input_fn=input):
    suffix = f" [{default}]" if default and not secret else ""
    text = f"{question}{suffix}: "
    answer = (getpass.getpass(text) if secret else input_fn(text)).strip()

    return answer or default


def ask_yes(question, default=True, input_fn=input):
    hint = "Y/n" if default else "y/N"
    answer = input_fn(f"{question} [{hint}]: ").strip().lower()

    return default if not answer else answer.startswith("y")


def collect_answers(args, input_fn=input):
    """Questions of the wizard; every one can be given as an option instead."""
    interactive = not args.non_interactive
    root = resolve_root(args.root)
    out = {"root": root}

    if interactive:
        from biobank import branding

        print(branding.welcome(package_version()))
        print("Setup\n" + "=" * 5)
        print("Step 1 of 4  Where should your data live?")
        out["root"] = resolve_root(ask("Data folder", str(root), input_fn=input_fn))

    existing = read_config(out["root"])
    out["secret_key"] = existing.get("BIOBANK_SECRET_KEY") or secrets.token_urlsafe(50)

    if interactive:
        print("\nStep 2 of 4  Database")
        print("  1) SQLite  (one file, nothing to install; best for one person or a small lab)")
        print("  2) PostgreSQL  (for a lab server shared by many people)")
        choice = ask("Choose 1 or 2", "1", input_fn=input_fn)
        out["database_url"] = ""

        if choice == "2":
            out["database_url"] = ask(
                "PostgreSQL address", "postgres://user:password@localhost:5432/biobank", input_fn=input_fn,
            )
    else:
        out["database_url"] = args.database_url or existing.get("BIOBANK_DATABASE_URL", "")

    if interactive:
        print("\nStep 3 of 4  Administrator account")
        out["admin_user"] = ask("Username", "admin", input_fn=input_fn)
        out["admin_email"] = ask("E-mail (optional)", "", input_fn=input_fn)
        out["admin_password"] = ""

        while len(out["admin_password"]) < 8:
            out["admin_password"] = ask("Password (at least 8 characters)", secret=True)
    else:
        out["admin_user"] = args.admin_user
        out["admin_email"] = args.admin_email or ""
        out["admin_password"] = args.admin_password or os.environ.get("BIOBANK_ADMIN_PASSWORD", "")

    if interactive:
        print("\nStep 4 of 4  Network")
        shared = ask_yes("Will other computers open this installation (not only this one)?", False, input_fn)
        out["host"] = "0.0.0.0" if shared else "127.0.0.1"
        out["allowed_hosts"] = (
            ask("Server name or address people will type in the browser", "", input_fn=input_fn) if shared else ""
        )
        out["time_zone"] = ask("Time zone", existing.get("BIOBANK_TIME_ZONE", "UTC"), input_fn=input_fn)
    else:
        out["host"] = args.host
        out["allowed_hosts"] = args.allowed_hosts or ""
        out["time_zone"] = args.time_zone or existing.get("BIOBANK_TIME_ZONE", "UTC")

    return out


def build_config(answers):
    config = {
        "BIOBANK_SECRET_KEY": answers["secret_key"],
        "BIOBANK_TIME_ZONE": answers["time_zone"],
        "BIOBANK_HOST": answers["host"],
    }

    if answers.get("database_url"):
        config["BIOBANK_DATABASE_URL"] = answers["database_url"]

    if answers.get("allowed_hosts"):
        config["BIOBANK_ALLOWED_HOSTS"] = answers["allowed_hosts"]
        origins = ",".join(
            f"http://{host.strip()}" for host in answers["allowed_hosts"].split(",") if host.strip()
        )
        config["BIOBANK_CSRF_TRUSTED_ORIGINS"] = origins

    return config


def create_admin(username, email, password):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.filter(**{User.USERNAME_FIELD: username}).first()

    if user:
        user.is_staff = user.is_superuser = True
        user.set_password(password)
        user.save()

        return False

    User.objects.create_superuser(username, email or "", password)

    return True


def cmd_setup(args, input_fn=input):
    answers = collect_answers(args, input_fn)

    if not answers["admin_user"] or len(answers["admin_password"]) < 8:
        print("An administrator username and a password of at least 8 characters are required.", file=sys.stderr)

        return 2

    config = build_config(answers)
    root = answers["root"]
    path = write_config(root, config)
    print(f"\nWriting settings to {path}")

    activate(root, config)

    print("Creating the database ...")
    manage("migrate", verbosity=0, interactive=False)

    if not getattr(args, "skip_static", False):
        print("Preparing the web files ...")
        manage("collectstatic", verbosity=0, interactive=False)

    created = create_admin(answers["admin_user"], answers["admin_email"], answers["admin_password"])
    print(("Created" if created else "Updated") + f" administrator '{answers['admin_user']}'.")

    if getattr(args, "demo", False):
        try:
            manage("seed_demo")
        except Exception as exc:  # the demo data command is optional
            print(f"Demo data was not loaded: {exc}")

    port = args.port
    print(
        "\nDone. Start B3 LIMS with:\n\n"
        f"    biobank-local run{'' if root == DEFAULT_ROOT.resolve() else f' --root {root}'}\n\n"
        f"then open http://127.0.0.1:{port}/ and sign in as '{answers['admin_user']}'.\n"
        "Optional features (HPC, Slurm, Jupyter, online services) are documented in docs/hpc.md."
    )

    return 0


# ---------------------------------------------------------------- other commands

def cmd_run(args):
    root = resolve_root(args.root)

    if not (root / CONFIG_NAME).is_file():
        print(f"No installation found in {root}. Run `biobank-local setup` first.", file=sys.stderr)

        return 2

    config = read_config(root)
    activate(root, config)
    host = args.host or config.get("BIOBANK_HOST", "127.0.0.1")
    print(f"B3 LIMS is running at http://{'127.0.0.1' if host == '0.0.0.0' else host}:{args.port}/  (Ctrl+C to stop)")

    try:
        from waitress import serve
    except ImportError:
        manage("runserver", f"{host}:{args.port}", use_reloader=False)

        return 0

    from biobank.wsgi import application

    serve(application, host=host, port=args.port, threads=8)

    return 0


def cmd_migrate(args):
    """After upgrading the software: bring the database and web files up to date."""
    root = resolve_root(args.root)

    if not (root / CONFIG_NAME).is_file():
        print(f"No installation found in {root}. Run `biobank-local setup` first.", file=sys.stderr)

        return 2

    activate(root)
    manage("migrate", verbosity=0, interactive=False)

    if not args.skip_static:
        manage("collectstatic", verbosity=0, interactive=False)

    print("Database and web files are up to date.")

    return 0


def cmd_createuser(args):
    root = resolve_root(args.root)
    activate(root)
    password = args.password or getpass.getpass("Password: ")
    created = create_admin(args.username, args.email or "", password)
    print(("Created" if created else "Updated") + f" administrator '{args.username}'.")

    return 0


def cmd_backup(args):
    root = resolve_root(args.root)
    config = read_config(root)

    if not config:
        print(f"No installation found in {root}.", file=sys.stderr)

        return 2

    target = Path(args.output or root / "backups")
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = target / f"biobank_{stamp}.tar.gz"

    if config.get("BIOBANK_DATABASE_URL"):
        print("PostgreSQL is configured: back it up with pg_dump; files are archived below.")

    with tarfile.open(archive, "w:gz") as tar:
        for name in ("database", "data", "storage", CONFIG_NAME):
            item = root / name

            if item.exists():
                tar.add(item, arcname=name)

    print(f"Backup written to {archive}")

    return 0


def cmd_doctor(args):
    root = resolve_root(args.root)
    problems = 0
    print(f"Data folder: {root}")

    if not (root / CONFIG_NAME).is_file():
        print("  [!] no config.env: run `biobank-local setup`")

        return 1

    print("  [ok] config.env found")
    activate(root)

    from django.core.management import call_command
    from django.db import connection

    try:
        call_command("check", verbosity=0)
        print("  [ok] Django configuration")
    except Exception as exc:
        problems += 1
        print(f"  [!] configuration: {exc}")

    try:
        connection.ensure_connection()
        print(f"  [ok] database ({connection.vendor})")
    except Exception as exc:
        problems += 1
        print(f"  [!] database: {exc}")

    free = shutil.disk_usage(root).free // (1024 ** 2)
    print(f"  [{'ok' if free > 500 else '!'}] free disk space: {free} MB")

    return 1 if problems else 0


def cmd_about(args):
    from biobank import branding

    print(branding.about(package_version()))

    return 0


def package_version():
    try:
        from importlib.metadata import version

        return version("biobank-lims")
    except Exception:  # not installed as a package (running from a checkout)
        return ""


def build_parser():
    from biobank import branding

    parser = argparse.ArgumentParser(
        prog="biobank-local",
        description=f"{branding.NAME}: {branding.TAGLINE}\nInstall and run it on one computer.",
        epilog=branding.HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", help=f"data folder (default: {DEFAULT_ROOT})")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="guided first-time installation")
    setup.add_argument("--non-interactive", action="store_true", help="use the options below instead of asking")
    setup.add_argument("--admin-user", default="admin")
    setup.add_argument("--admin-email")
    setup.add_argument("--admin-password", help="or set BIOBANK_ADMIN_PASSWORD")
    setup.add_argument("--database-url", help="PostgreSQL address; SQLite when omitted")
    setup.add_argument("--host", default="127.0.0.1")
    setup.add_argument("--allowed-hosts", help="comma-separated names people use to reach the server")
    setup.add_argument("--time-zone")
    setup.add_argument("--port", type=int, default=8000)
    setup.add_argument("--demo", action="store_true", help="also load example data")
    setup.add_argument("--skip-static", action="store_true", help=argparse.SUPPRESS)
    setup.set_defaults(func=cmd_setup)

    run = sub.add_parser("run", help="start the web application")
    run.add_argument("--host")
    run.add_argument("--port", type=int, default=8000)
    run.set_defaults(func=cmd_run)

    migrate = sub.add_parser("migrate", help="update the database after installing a newer version")
    migrate.add_argument("--skip-static", action="store_true", help=argparse.SUPPRESS)
    migrate.set_defaults(func=cmd_migrate)

    user = sub.add_parser("createuser", help="create or reset an administrator")
    user.add_argument("username")
    user.add_argument("--email")
    user.add_argument("--password")
    user.set_defaults(func=cmd_createuser)

    backup = sub.add_parser("backup", help="archive the database folder and uploaded files")
    backup.add_argument("--output", help="folder for the archive")
    backup.set_defaults(func=cmd_backup)

    doctor = sub.add_parser("doctor", help="check the installation")
    doctor.set_defaults(func=cmd_doctor)

    about = sub.add_parser("about", help="what B3 LIMS is for and which integrations it supports")
    about.set_defaults(func=cmd_about)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
