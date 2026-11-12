from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from core.services import interface_settings, sample_types


@login_required
def interface_settings_view(request):
    """Administrators choose which menu items and built-in Sample types this installation shows."""
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden("Only administrators can change the interface.")

    if request.method == "POST":
        shown = set(request.POST.getlist("show_feature"))
        shown_types = set(request.POST.getlist("show_type"))
        hidden_features = [key for key, _ in interface_settings.FEATURES if key not in shown]
        hidden_types = [name for name in interface_settings.BUILTIN_TYPES if name not in shown_types]
        interface_settings.save(hidden_features, hidden_types)
        messages.success(request, "Interface saved. The menu and the New Sample form now follow these choices.")

        return redirect("interface_settings")

    hidden = interface_settings.current()

    return render(request, "internal/interface_settings.html", {
        "features": [(key, label, key not in hidden["features"]) for key, label in interface_settings.FEATURES],
        "builtin_types": [(name, name not in hidden["types"]) for name in interface_settings.BUILTIN_TYPES],
        "custom_types": list(sample_types.custom_types()),
    })
