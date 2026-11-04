from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.context import base_context


@login_required
def calendar_view(request):
    """The Lab Calendar screen; its events come from the bench calendar API."""
    return render(request, "internal/calendar/calendar.html", base_context(request))
