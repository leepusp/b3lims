# core/views/internal/lab_tools/analysis.py

import json
import pandas as pd
import numpy as np  # Adicionado para cálculos matemáticos
import plotly.express as px
import plotly.io as pio
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from core.models.lab_tools.notebook import NotebookEntry, NotebookBlock

@login_required
def run_notebook_analysis(request, entry_id):
    """
    Motor de execução que transforma tabelas do ELN em gráficos interativos.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            code = data.get('code', '')
            
            # 1. Recupera os blocos de tabela da entrada ativa para que o código possa lê-los
            blocks = NotebookBlock.objects.filter(entry_id=entry_id, block_type='table')
            
            # 2. Namespace para execução (o "cérebro" do notebook)
            # Injetamos pandas, plotly e numpy para que o usuário não precise importar no bloco
            ctx_env = {
                'pd': pd,
                'px': px,
                'np': np,
            }
            
            # 3. Mapeia as tabelas JSON para DataFrames Pandas automaticamente
            # O usuário acessa via table_1, table_2, etc. no bloco de código
            for i, block in enumerate(blocks):
                table_data = block.content_data.get('content', [])
                if len(table_data) > 1:
                    headers = table_data[0]
                    rows = table_data[1:]
                    
                    # Cria o DataFrame e limpa possíveis espaços em branco nos nomes das colunas
                    df = pd.DataFrame(rows, columns=[str(h).strip() for h in headers])
                    
                    # Tenta converter colunas numéricas (essencial para gráficos)
                    ctx_env[f'table_{i+1}'] = df.apply(pd.to_numeric, errors='ignore')

            # 4. Execução Segura do Código
            # Usamos ctx_env tanto para globals quanto para locals para manter persistência
            exec(code, ctx_env, ctx_env)
            
            # Busca a variável 'fig' definida pelo usuário
            fig = ctx_env.get('fig')

            if fig:
                # Transforma o objeto Plotly em JSON estruturado para o frontend
                graph_dict = json.loads(pio.to_json(fig))
                return JsonResponse({
                    'status': 'success', 
                    'graph_data': graph_dict
                })
            
            return JsonResponse({
                'status': 'error', 
                'message': 'Nenhum objeto "fig" foi definido. Certifique-se de terminar seu código com "fig = px..."'
            })

        except Exception as e:
            # Retorna o erro real do Python para o alerta do navegador
            return JsonResponse({'status': 'error', 'message': f"Erro no Python: {str(e)}"})

    return JsonResponse({'status': 'error', 'message': 'Método não permitido'}, status=405)
