# Interface language plan

The biobank system should support Portuguese and English interfaces for both internal and public workflows.

## Target languages

- Portuguese: `pt-br`
- English: `en`

## Areas to translate

- Public shipment submission form
- Public shipment tracking page
- Internal shipment dashboard
- Sample intake workflow
- Document generation labels
- Shipment status labels
- Checklist labels
- Validation messages

## Recommended implementation

Use Django native internationalization:

- `USE_I18N = True`
- `LocaleMiddleware`
- `{% trans %}` and `{% blocktrans %}` in templates
- `gettext_lazy` for model labels and choices
- `/locale/pt_BR/LC_MESSAGES/django.po`
- `/locale/en/LC_MESSAGES/django.po`

## UI behavior

Add a language selector in:

- public pages header
- internal biobank navbar/sidebar

The selected language should be stored in session/cookie.
