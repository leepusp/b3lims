from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q
import json

from core.models.lab_tools.notebook import NotebookEntry
from core.models.samples.sample import Sample

@login_required
def notebook_index(request):
    entries = NotebookEntry.objects.filter(author=request.user)
    active_entry_id = request.GET.get('entry_id')
    active_entry = None
    if active_entry_id:
        active_entry = get_object_or_404(NotebookEntry, id=active_entry_id, author=request.user)
    elif entries.exists():
        active_entry = entries.first()
    return render(request, 'internal/lab_tools/notebook.html', {
        'entries': entries,
        'active_entry': active_entry
    })

@login_required
def notebook_create(request):
    new_entry = NotebookEntry.objects.create(
        title="Novo Experimento",
        author=request.user,
        content=""
    )
    return redirect(f'/internal/lab-tools/notebook/?entry_id={new_entry.id}')

@login_required
def notebook_save_api(request, entry_id):
    if request.method == "POST":
        entry = get_object_or_404(NotebookEntry, id=entry_id, author=request.user)
        try:
            data = json.loads(request.body)
            entry.title = data.get('title', entry.title)
            entry.content = data.get('content', '')
            entry.save()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=405)

@login_required
def search_samples_api(request):
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse([], safe=False)
    samples = Sample.objects.filter(
        Q(sample_id__icontains=query) | Q(name__icontains=query)
    )[:10]
    results = [{'id': s.id, 'value': f"{s.sample_id} - {s.name}" if s.name else s.sample_id} for s in samples]
    return JsonResponse(results, safe=False)
