# Biological Sample Collections Database (Biobank LIMS)

Este sistema é um LIMS (Laboratory Information Management System) desenvolvido para o CEPID B3 (Centro de Pesquisa, Inovação e Difusão - Biologia de Bactérias e Bacteriófagos). O software visa centralizar o armazenamento, organização e distribuição de patrimônio biológico de alto valor científico.

Sobre o Projeto
Bactérias resistentes a antibióticos representam um desafio global de saúde pública. O CEPID B3, financiado pela FAPESP, investiga as bases moleculares desses mecanismos, gerando um acervo inestimável de linhagens clínicas, ambientais, bacteriófagos e plasmídeos.

Objetivo
Estabelecer um repositório centralizado com protocolos padronizados de curadoria, garantindo:

Rastreabilidade e Segurança: Controle rigoroso de estoque e conformidade com o SisGen.

Organização Molecular: Visualização avançada de sequências e estruturas 3D.

Colaboração: Facilitação do compartilhamento entre os mais de 160 pesquisadores da rede (USP, UNESP, UNICAMP e UNIFESP).

Funcionalidades Principais
ELN (Electronic Lab Notebook): Caderno de laboratório digital com sistema de menções para amostras.

Molecular Viewer: * Visualização 3D de proteínas (estilo Benchling) via 3Dmol.js.

Mapas de plasmídeos interativos (Circulares e Lineares) via SeqViz.

Gestão de Inventário: Controle de Biobancos, Coleções e Amostras.

Conformidade Legal: Campos dedicados para registro de patrimônio genético.

Instalação e Configuração
Siga os passos abaixo para configurar o ambiente de desenvolvimento localmente.

1. Pré-requisitos
Python 3.10 ou superior

Git

2. Clonar o Repositório
Bash

git clone https://github.com/leepbioinfo/biobank.git
cd biobank
3. Configurar o Ambiente Virtual
Bash

# Criar o ambiente
python3 -m venv biobank-env

# Ativar no Linux/macOS
source biobank-env/bin/activate

# Ativar no Windows
biobank-env\Scripts\activate
4. Instalar Dependências
Bash

pip install -r requirements.txt
5. Configurar o Banco de Dados
O sistema utiliza SQLite para desenvolvimento por padrão.

Bash

python manage.py makemigrations
python manage.py migrate
6. Criar Usuário Administrador
Para acessar o painel de gestão e o Django Admin:

Bash

python manage.py createsuperuser

Execução
Para rodar o servidor de desenvolvimento:

Bash

python manage.py runserver
