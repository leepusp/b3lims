# Biological Sample Collections Database (Biobank LIMS)

This project is a Biobank developed for CEPID B3 — Center for Research, Innovation and Dissemination in Bacterial and Bacteriophage Biology.

The system was designed to centralize the storage, organization, and distribution of biological assets of high scientific value, promoting traceability, legal compliance, and collaboration among researchers.

# Installation and Configuration

Follow the steps below to configure the development environment locally.

# 1. Prerequisites

Python 3.10+

Git

# 2. Clone the Repository

git clone https://github.com/leepbioinfo/biobank.git cd biobank

# 3. Configure Virtual Environment

python3 -m venv biobank-env

# Activate on Linux/macOS

source biobank-env/bin/activate

# Activate on Windows

biobank-env\Scripts\activate

# 4. Install Dependencies

pip install -r requirements.txt

# 5. Configure Database

python manage.py makemigrations python manage.py migrate

python manage.py migrate

# 6. Create Administrator User

python manage.py createsuperuser

# 7. Execution

python manage.py runserver

# License

This project is developed for academic and scientific purposes within the scope of CEPID B3 — FAPESP.
