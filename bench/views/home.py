from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from core.context import base_context


def _url_or_none(name):
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


# Modules shown on the B3 Bench home page. "url_name" points to a screen that
# already exists; "step" names the roadmap step that will deliver the rest.
MODULES = (
    {
        "title": "ELN Notebook",
        "icon": "bi-journal-bookmark",
        "description": "Experiments, protocols and analyses linked to samples, chemicals and sequences.",
        "url_name": "notebook_index",
        "step": "Templates, categories, steps and extra fields: steps 1.1 to 3.4",
    },
    {
        "title": "Lab Calendar",
        "icon": "bi-calendar-week",
        "description": "Shared calendar with colour-coded layers, bookings with optional rules and recurring bookings.",
        "url_name": "lab_calendar",
        "step": "Booking rules: step 2.1 · new calendar screen: step 2.2",
    },
    {
        "title": "Jupyter Notebooks",
        "icon": "bi-code-square",
        "description": "Notebooks on the cluster, linked to ELN entries.",
        "url_name": "jupyter_index",
        "step": "Starter notebooks, sharing and unattended runs: step 6.3",
    },
    {
        "title": "Molecular Registry",
        "icon": "bi-bezier2",
        "description": "Sequences, plasmid maps, alignments and structures.",
        "url_name": "molecular_registry_index",
        "step": "OpenCloning strategies: step 4.4",
    },
    {
        "title": "Data submissions",
        "icon": "bi-cloud-upload",
        "description": "RO-Crate packages for ENA, Zenodo and the Biobank public catalog.",
        "url_name": "submission_list",
        "step": "Steps 5.2 and 6.6",
    },
)


@login_required
def bench_home(request):
    ctx = base_context(request)
    modules = []
    for module in MODULES:
        url = _url_or_none(module["url_name"]) if module["url_name"] else None
        modules.append({**module, "url": url})
    ctx["modules"] = modules
    return render(request, "bench/home.html", ctx)
