# Contributing

Thank you for helping. B3 LIMS is a Django application; English is the language of the code, UI and documentation (`docs/development/language_policy.md`).

## Set up for development

```bash
git clone https://github.com/leepusp/biobank.git && cd biobank
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python manage.py test --settings=biobank.test_settings
```

To try the application: `pip install -e . && biobank-local setup && biobank-local run`.

## Pull requests

- One topic per pull request; add or update tests (`core/tests/`).
- Migrations must be additive (no destructive changes in the same release).
- Run the full test suite before opening the request; it takes about a minute.
- Do not commit databases, uploaded files, credentials or institution-specific settings.
- By contributing you agree that your work is released under the AGPL-3.0 license of the project.
