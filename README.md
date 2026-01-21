# Biological Sample Collections Database (Biobank LIMS)

Este projeto é um Biobank desenvolvido para o CEPID B3 — Centro de Pesquisa, Inovação e Difusão em Biologia de Bactérias e Bacteriófagos.

O sistema foi projetado para centralizar o armazenamento, organização e distribuição de patrimônio biológico de alto valor científico, promovendo rastreabilidade, conformidade legal e colaboração entre pesquisadores.

# Instalação e Configuração

Siga os passos abaixo para configurar o ambiente de desenvolvimento localmente.

# 1. Pré-requisitos

Python 3.10+

Git

# 2. Clonar o Repositório

git clone https://github.com/leepbioinfo/biobank.git
cd biobank

# 3. Configurar Ambiente Virtual

python3 -m venv biobank-env

# Ativar no Linux/macOS

source biobank-env/bin/activate

# Ativar no Windows

biobank-env\Scripts\activate

# 4.Instalar Dependências

pip install -r requirements.txt

# 5. Configurar Banco de Dados

python manage.py makemigrations
python manage.py migrate

# 6. Criar Usuário Administrador

python manage.py createsuperuser

# 7. Execução

python manage.py runserver


# Licença

Este projeto é desenvolvido para fins acadêmicos e científicos no âmbito do CEPID B3 — FAPESP.
