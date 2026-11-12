"""Which menu items and built-in Sample types an administrator chose to hide."""

from django.core.cache import cache

FEATURES = [
    ("biobanks", "Biobanks"),
    ("collections", "Collections"),
    ("shipments", "Transport (shipments and documents)"),
    ("chemicals", "Chemicals"),
    ("calendar", "Lab Calendar"),
    ("eln", "ELN Notebook"),
    ("molecular", "Molecular Registry"),
    ("jupyter", "Jupyter"),
    ("submissions", "Data submissions"),
]
BUILTIN_TYPES = ["Bacterium (Host)", "Phage (Virus)", "Plasmid", "Other"]
CACHE_KEY = "b3lims.interface_settings"


def current():
    """{'features': set, 'types': set} of hidden items; cached for a short time."""
    data = cache.get(CACHE_KEY)

    if data is None:
        from core.models.interface_settings import InterfaceSettings

        row = InterfaceSettings.objects.first()
        data = {
            "features": list(row.hidden_features) if row else [],
            "types": list(row.hidden_sample_types) if row else [],
        }
        cache.set(CACHE_KEY, data, 30)

    return {"features": set(data["features"]), "types": set(data["types"])}


def save(hidden_features, hidden_types):
    from core.models.interface_settings import InterfaceSettings

    known = {key for key, _ in FEATURES}
    row = InterfaceSettings.objects.first() or InterfaceSettings()
    row.hidden_features = sorted(set(hidden_features) & known)
    row.hidden_sample_types = [t for t in BUILTIN_TYPES if t in set(hidden_types)]
    row.save()
    cache.delete(CACHE_KEY)

    return row
