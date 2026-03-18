from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def plasmid_editor(request):
    """
    Renderiza o editor de plasmídeos (OVE).
    """
    context = {
        'page_title': 'Plasmid Editor (OVE)',
    }
    return render(request, 'internal/lab_tools/plasmid_editor.html', context)
