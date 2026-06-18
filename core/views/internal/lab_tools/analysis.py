import json

import numpy as np
import pandas as pd
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from core.models.lab_tools.notebook import NotebookEntry

try:
    import plotly.express as px
    import plotly.io as pio
    PLOTLY_AVAILABLE = True
except ImportError:
    px = None
    pio = None
    PLOTLY_AVAILABLE = False


@login_required
def run_notebook_analysis(request, entry_id):
    """
    Execute lightweight notebook code for interactive plots.

    This endpoint is intended for small internal analyses. Heavy tasks should
    be routed through a controlled Slurm job block.
    """
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Method not allowed"},
            status=405,
        )

    entry = get_object_or_404(NotebookEntry, id=entry_id, author=request.user)

    try:
        data = json.loads(request.body)
        code = data.get("code", "")

        if not PLOTLY_AVAILABLE and ("px." in code or "plotly" in code.lower()):
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "Plotly is not installed in the biobank environment. "
                        "Install plotly or use this block only for non-plotting code until Slurm-backed analysis is enabled."
                    ),
                },
                status=400,
            )

        table_blocks = entry.blocks.filter(block_type="table")

        safe_builtins = {
            "abs": abs,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "range": range,
            "round": round,
            "set": set,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
        }

        ctx_env = {
            "__builtins__": safe_builtins,
            "pd": pd,
            "np": np,
        }

        if PLOTLY_AVAILABLE:
            ctx_env["px"] = px

        for index, block in enumerate(table_blocks, start=1):
            table_data = block.content_data.get("content", [])

            if len(table_data) > 1:
                headers = table_data[0]
                rows = table_data[1:]

                df = pd.DataFrame(
                    rows,
                    columns=[str(header).strip() for header in headers],
                )
                df = df.apply(pd.to_numeric, errors="ignore")
                ctx_env[f"table_{index}"] = df

        exec(code, ctx_env, ctx_env)

        fig = ctx_env.get("fig")

        if fig is None:
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        'No "fig" object was defined. '
                        "When Plotly is installed, end your code with something like: fig = px.bar(...)."
                    ),
                },
                status=400,
            )

        if not PLOTLY_AVAILABLE:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "A fig object was defined, but Plotly is not installed on the server.",
                },
                status=400,
            )

        graph_dict = json.loads(pio.to_json(fig))

        return JsonResponse(
            {
                "status": "success",
                "graph_data": graph_dict,
            }
        )

    except Exception as exc:
        return JsonResponse(
            {"status": "error", "message": f"Python error: {exc}"},
            status=400,
        )
