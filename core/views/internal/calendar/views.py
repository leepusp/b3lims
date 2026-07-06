from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from core.context import base_context
from core.models.events.model import Event
from core.permissions.workspace import visible_workspace_events_for_user

@login_required
def calendar_view(request):
    ctx = base_context(request)
    # Busca os últimos 100 eventos
    events = visible_workspace_events_for_user(request.user).select_related('sample', 'performed_by').order_by('-timestamp')[:100]
    ctx['events'] = events
    return render(request, "internal/calendar/calendar.html", ctx)
