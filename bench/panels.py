"""Panels that B3 Bench contributes to core screens.

Each feature registers its panels here; ``BenchConfig.ready()`` calls
``register_all()`` once at start-up.
"""

from core.services.extension_panels import ExtensionPanel, register_panel


def _agenda_context(request, obj):
    from bench.services.agenda import agenda

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    return {"agenda": agenda(user)}


def register_all():
    """Register B3 Bench panels on core screens."""
    register_panel(
        ExtensionPanel(
            slot="notebook_dashboard.sidebar",
            key="bench.agenda",
            template="bench/panels/agenda.html",
            get_context=_agenda_context,
            title="Today and this week",
            order=10,
        )
    )
