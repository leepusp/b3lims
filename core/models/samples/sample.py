import uuid
from django.db import models
from django.contrib.auth.models import User

# Imports mantidos para integridade
from core.models.collections.collection import Collection
from core.models.biobanks.biobank import Biobank
from core.models.tags.model import Tag
from core.models.keywords.model import KeywordValue

class Sample(models.Model):
    """
    Amostra biológica CEPIDB3. 
    Modelo Base com herança Polimórfica.
    """
    STATUS_CHOICES = [
        ('pending', 'Aguardando Recebimento'),
        ('qc', 'Em Controle de Qualidade'),
        ('available', 'Disponível / Aprovada'),
        ('rejected', 'Rejeitada / Inviável'),
        ('depleted', 'Exaurida'),
    ]

    # Identificação
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    sample_id = models.CharField(max_length=100, unique=True)
    sample_type = models.CharField(max_length=100, blank=True, null=True)
    organism_name = models.CharField(max_length=255, blank=True, null=True)

    # ==========================================
    # ORGANIZAÇÃO (ATUALIZADO PARA MANY-TO-MANY)
    # ==========================================
    biobank = models.ForeignKey(Biobank, on_delete=models.SET_NULL, null=True, blank=True, related_name="samples")
    # Trocado de ForeignKey(collection) para ManyToManyField(collections)
    collections = models.ManyToManyField(Collection, blank=True, related_name="samples")
    
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="owned_samples")

    # Status e Governança
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_public = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # NOVOS CAMPOS (ELN e Dados Técnicos)
    scientific_notes = models.TextField(blank=True, null=True)

    # Metadados Físicos (Preenchido dinamicamente pelo construtor de caminho no frontend)
    storage_location = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    # CLASSIFICAÇÃO Genérica
    tags = models.ManyToManyField(Tag, blank=True, related_name="samples")
    keywords = models.ManyToManyField(KeywordValue, blank=True, related_name="samples")

    # FILOGENIA / REDE BIOLÓGICA
    lineage = models.ManyToManyField(
        'self',
        through='core.SampleRelationship',
        through_fields=('source_sample', 'target_sample'),
        symmetrical=False,
        blank=True,
        related_name='derived_from_lineage'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        from core.models.samples.sample_files import move_sample_files
        
        # REMOVIDO: A regra que forçava o biobank a ser igual ao da coleção.
        # Agora o Biobanco e as Coleções operam de forma independente.

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sample_id} - {self.organism_name or 'Sem organismo'}"


# ========================================================================
# ARMAZENAMENTO FÍSICO (O Caminho do Meio / Híbrido)
# ========================================================================
class SampleStorageLevel(models.Model):
    """
    Tabela relacional para guardar fatias da localização física de uma amostra.
    Exemplo para "Freezer 1 > Prateleira 2 > Caixa A":
    - level_index 0: "Freezer 1" (Tipo Principal)
    - level_index 1: "Prateleira 2" (Subtipo 1)
    - level_index 2: "Caixa A" (Subtipo 2)
    """
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, related_name='storage_levels')
    name = models.CharField(max_length=150, help_text="Nome do nível (Ex: Freezer 1)")
    level_index = models.PositiveIntegerField(help_text="0 é o nível mais alto/principal")

    class Meta:
        ordering = ['level_index']
        # Garante que uma amostra não tenha dois "Nível 0"
        unique_together = ('sample', 'level_index')
        verbose_name = "Nível de Armazenamento"
        verbose_name_plural = "Níveis de Armazenamento"

    def __str__(self):
        return f"[{self.level_index}] {self.name} (Amostra: {self.sample.sample_id})"
