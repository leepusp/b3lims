from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required

# Imports Específicos do Molecular
from core.models.lab_tools.molecular import MolecularSequence


# --- MOLECULAR VIEWER VIEWS ---

@login_required
def molecular_index(request):
    """Lista todas as sequências moleculares salvas"""
    sequences = MolecularSequence.objects.all().order_by('-created_at')
    return render(request, 'internal/lab_tools/molecular_list.html', {
        'sequences': sequences
    })


@login_required
def molecular_upload(request):
    """
    Processa o formulário de upload vindo do modal em molecular_list.html.
    Cria o objeto no banco e redireciona para o visualizador.
    """
    if request.method == "POST":
        name = request.POST.get('name')
        seq_type = request.POST.get('seq_type')
        sequence_data = request.POST.get('sequence_data')
        description = request.POST.get('description')

        # Criação do registro no banco de dados
        new_seq = MolecularSequence.objects.create(
            name=name,
            seq_type=seq_type,
            sequence_data=sequence_data,
            description=description,
            author=request.user
        )

        # Redireciona imediatamente para o visualizador da molécula recém-criada
        return redirect('molecular_viewer', seq_id=new_seq.id)

    return redirect('molecular_index')


@login_required
def molecular_viewer(request, seq_id):
    """Visualizador Híbrido: 3D para PDB e Texto formatado para DNA/Proteína"""
    sequence = get_object_or_404(MolecularSequence, id=seq_id)

    context = {
        'sequence': sequence,
        'formatted_seq': None
    }

    # Lógica de formatação para leitura biológica (blocos de texto de 80 caracteres)
    if sequence.seq_type in ['DNA', 'PROTEIN']:
        # Remove quebras de linha espúrias e normaliza para maiúsculas
        raw = sequence.sequence_data.replace('\n', '').replace('\r', '').upper()

        # Divide em chunks de 80 caracteres para melhor leitura no grid
        chunks = [raw[i:i + 80] for i in range(0, len(raw), 80)]

        formatted_seq = []
        current_index = 1
        for chunk in chunks:
            formatted_seq.append({'index': current_index, 'text': chunk})
            current_index += 80

        context['formatted_seq'] = formatted_seq
        context['seq_length'] = len(raw)

    return render(request, 'internal/lab_tools/molecular_viewer.html', context)