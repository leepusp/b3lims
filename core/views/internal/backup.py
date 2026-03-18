import os
import zipfile
import tempfile
from io import StringIO
from django.core.management import call_command
from django.http import HttpResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils import timezone

@login_required
def workspace_backup_view(request):
    # Apenas superusuários podem fazer backup
    if not request.user.is_superuser:
        raise PermissionDenied("Apenas administradores podem realizar backups.")

    # Configuração Padrão (Full Backup) se for GET
    include_db = True
    include_files = True

    # Se for POST (via algum formulário de opções avançadas), respeita as escolhas
    if request.method == 'POST':
        include_db = request.POST.get('include_db') in ['on', 'true', '1']
        include_files = request.POST.get('include_files') in ['on', 'true', '1']

    # Cria um arquivo temporário seguro
    # delete=False permite que reabramos o arquivo para enviar ao usuário antes de apagar
    temp_file = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
    temp_zip_path = temp_file.name
    temp_file.close() # Fecha para o zipfile poder abrir

    try:
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            
            # 1. Backup do Banco de Dados (Metadados JSON)
            if include_db:
                out = StringIO()
                # Exclui tabelas de sessão e logs para não inchar o backup
                call_command('dumpdata', indent=2, stdout=out, exclude=['contenttypes', 'auth.permission', 'sessions', 'admin.logentry'])
                zipf.writestr('database_dump.json', out.getvalue())

            # 2. Backup dos Arquivos de Mídia (Uploads)
            if include_files:
                media_root = settings.MEDIA_ROOT
                if os.path.exists(media_root):
                    for root, dirs, files in os.walk(media_root):
                        for file in files:
                            file_path = os.path.join(root, file)
                            # Caminho relativo dentro do zip (ex: media/uploads/foto.jpg)
                            arcname = os.path.join('media', os.path.relpath(file_path, media_root))
                            zipf.write(file_path, arcname)

        # Prepara o download
        with open(temp_zip_path, 'rb') as f:
            file_data = f.read()

        response = HttpResponse(file_data, content_type='application/zip')
        timestamp = timezone.now().strftime('%Y-%m-%d_%H%M')
        response['Content-Disposition'] = f'attachment; filename="biobank_full_backup_{timestamp}.zip"'
        return response

    except Exception as e:
        return HttpResponse(f"Erro ao gerar backup: {str(e)}", status=500)

    finally:
        # Garante que o arquivo temporário é removido do servidor
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
