from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def molecular_viewer(request):
    """
    Renderiza o visualizador Mol* (Molstar).
    """
    # Exemplo: Se quiser carregar um PDB específico via URL, pegue o ID aqui.
    # pdb_id = request.GET.get('pdb', '1q4r') 
    
    context = {
        'page_title': 'Molecular Viewer (Mol*)',
        'default_pdb': '1q4r', # GFP (Proteína verde fluorescente) como exemplo inicial
    }
    return render(request, 'internal/lab_tools/molecular_viewer.html', context)
