from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from core.context import base_context
from core.models.events.model import Event

@login_required
def calendar_view(request):
    ctx = base_context(request)
    
    # Busca os últimos 100 eventos para a agenda
    events = Event.objects.all().select_related('sample', 'performed_by').order_by('-timestamp')[:100]
    
    # Agrupamento simples por data poderia ser feito no template com o tag {% ifchanged %}
    ctx['events'] = events
    
    return render(request, "internal/calendar/calendar.html", ctx)
