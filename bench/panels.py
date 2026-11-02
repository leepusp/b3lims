"""Panels that B3 Bench contributes to core screens.

Each feature registers its panels here; ``BenchConfig.ready()`` calls
``register_all()`` once at start-up.
"""


def register_all():
    """Register B3 Bench panels on core screens.

    Panels are added by the steps that need them (for example the bookings
    panel on the ELN entry in step 2.2).
    """
    return None
