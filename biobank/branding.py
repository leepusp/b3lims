"""Words the command line uses to introduce B3 LIMS.

Kept apart from the logic so the text can be edited (or translated) without touching the commands.
Only features that exist in the code are listed under INTEGRATIONS; planned ones are marked as such.
"""

NAME = "B3 LIMS"

TAGLINE = "Samples, freezers, notebooks and shipments for research labs."

# Provisional wording: replace with the project's own statement.
MISSION = (
    "B3 LIMS keeps a laboratory's biological material, where it is stored, what was done with it\n"
    "and where it was sent in one traceable place, so that collections stay findable, shareable\n"
    "and citable. It grew out of the CEPID B3 and runs on a single computer, a lab server or a\n"
    "cluster. Your data stays on your machine."
)

BANNER = r"""
  ____  _____   _     ___ __  __ ____
 | __ )|___ /  | |   |_ _|  \/  / ___|
 |  _ \  |_ \  | |    | || |\/| \___ \
 | |_) |___) | | |___ | || |  | |___) |
 |____/|____/  |_____|___|_|  |_|____/
"""

# (what, how to use it, where it runs)
INTEGRATIONS = [
    ("Reference taxonomies",
     "python manage.py build_taxonomy_index | build_gtdb_index | build_ictv_index",
     "offline, from files you download"),
    ("Zenodo publishing",
     "set BIOBANK_ZENODO_TOKEN (sandbox by default)",
     "online, optional"),
    ("Address search for biobanks",
     "set BIOBANK_PUBLIC_URL so the geocoder can identify you",
     "online, optional"),
    ("Transport documents (MTA/TTM, CIBio)",
     "Shipments module in the web interface",
     "offline"),
    ("Jupyter servers through Slurm",
     "see docs/hpc.md",
     "cluster only, optional"),
]

PLANNED = [
    "Read-only API with personal access tokens",
    "biobank_client for notebooks (Jupyter or any Python)",
    "Sample types for cells, nucleic acids and datasets",
]


def welcome(version=""):
    suffix = f"  v{version}" if version else ""

    return f"{BANNER.rstrip()}\n  {NAME}{suffix}  -  {TAGLINE}\n"


def about(version=""):
    lines = [welcome(version), MISSION, "", "Integrations that exist today:"]

    for what, how, where in INTEGRATIONS:
        lines.append(f"  - {what} ({where})")
        lines.append(f"      {how}")

    lines += ["", "Planned:"] + [f"  - {item}" for item in PLANNED]
    lines += ["", "Documentation: docs/index.md   Source: https://github.com/leepusp/biobank", ""]

    return "\n".join(lines)


HELP_EPILOG = """\
first time:     biobank-local setup            (add --demo to load a fictional lab)
every day:      biobank-local run
upgrading:      biobank-local migrate
safety:         biobank-local backup
more:           biobank-local about            (purpose, integrations, what is planned)
"""
