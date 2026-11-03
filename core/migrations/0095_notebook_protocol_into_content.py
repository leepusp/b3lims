import re

from django.db import migrations
from django.utils.html import escape


def fold_protocol_into_content(apps, schema_editor):
    """The classic page kept a separate protocol text; the entry page has one
    document. Append it as a "Protocol" section so nothing is hidden."""
    NotebookEntry = apps.get_model("core", "NotebookEntry")
    for entry in NotebookEntry.objects.exclude(protocol_content="").iterator():
        protocol = (entry.protocol_content or "").strip()
        if not protocol:
            continue
        marker = "<h2>Protocol</h2>"
        if re.search(r"</?[a-zA-Z][a-zA-Z0-9]*(\s[^>]*)?>", protocol):
            body = protocol  # already HTML; sanitised on render and on save
        else:
            body = "".join(
                f"<p>{escape(line)}</p>" for line in protocol.splitlines() if line.strip()
            )
        if marker + body in (entry.content or ""):
            continue  # already folded in (re-run safe)
        entry.content = (entry.content or "") + marker + body
        entry.save(update_fields=["content"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0094_notebook_spreadsheets"),
    ]

    operations = [
        migrations.RunPython(fold_protocol_into_content, migrations.RunPython.noop),
    ]
