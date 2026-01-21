from django.db import models
from django.conf import settings


class MolecularSequence(models.Model):
    """
    Armazena sequências (FASTA) ou estruturas (PDB).
    Agora parte do app Core.
    """
    TYPE_CHOICES = (
        ('DNA', 'Sequência DNA (FASTA)'),
        ('PROTEIN', 'Proteína (FASTA)'),
        ('PDB', 'Estrutura 3D (PDB)'),
    )

    name = models.CharField(max_length=255)
    seq_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='PDB')
    sequence_data = models.TextField()
    description = models.TextField(blank=True)

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Molecular Sequence"

    def __str__(self):
        return self.name