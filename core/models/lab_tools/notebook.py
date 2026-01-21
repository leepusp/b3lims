from django.db import models
from django.conf import settings
from core.models.samples.sample import Sample


class NotebookEntry(models.Model):
    """
    Entradas de caderno de laboratório (ELN).
    Agora parte do app Core.
    """
    title = models.CharField(max_length=255, default="Sem título")
    content = models.TextField(blank=True)

    # Relacionamento com Samples do Core
    mentions = models.ManyToManyField(Sample, related_name='notebook_mentions', blank=True)

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='core_notebook_entries')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Notebook Entry"
        verbose_name_plural = "Notebook Entries"
        # Opcional: define a tabela no banco explicitamente se quiser manter padrão
        # db_table = 'core_notebook_entry'

    def __str__(self):
        return f"{self.title} - {self.author.username}"