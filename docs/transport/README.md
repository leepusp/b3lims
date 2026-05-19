# Transport documentation source templates

This directory stores the reference documents used to model the shipment, declaration, labeling, receipt, and intake workflows of the biobank system.

## Directory structure

- `source_templates/declarations/`: sender declaration and content declaration.
- `source_templates/labels/`: external package identification and printable labels.
- `source_templates/ogm_cibio/`: OGM/CIBio notification forms.
- `source_templates/mta_ttm/`: MTA/TTM and genetic heritage shipment documents.
- `extracted_structure/`: structured implementation notes derived from the source documents.

## Implementation rule

Files in `source_templates/` are source references and should not be edited directly for application logic.

Curated templates for automated DOCX/PDF generation should later be placed under:

`core/document_templates/shipments/`

Generated shipment documents should not be committed to Git.
