import uuid
from django.db import models
from django.contrib.auth.models import User

# Imports mantidos para integridade
from core.models.collections.collection import Collection
from core.models.biobanks.biobank import Biobank
from core.models.tags import Tag
from core.models.keywords import KeywordValue

class Sample(models.Model):
    """
    Amostra biológica CEPIDB3. 
    Lógica de Tags e Keywords preservada para funcionamento com samples.js
    """
    STATUS_CHOICES = [
        ('pending', 'Aguardando Recebimento'),
        ('qc', 'Em Controle de Qualidade'),
        ('available', 'Disponível / Aprovada'),
        ('rejected', 'Rejeitada / Inviável'),
        ('depleted', 'Exaurida'),
    ]

    VISIBILITY_CHOICES = [
        ("private", "Privada"),
        ("group", "Grupo de pesquisa"),
        ("biobank", "Biobank"),
        ("public", "Pública"),
    ]

    # Identificação
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    sample_id = models.CharField(max_length=100, unique=True)
    sample_type = models.CharField(max_length=100, blank=True, null=True)
    organism_name = models.CharField(max_length=255, blank=True, null=True)

    # Hierarquia
    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, null=True, blank=True, related_name="samples")
    biobank = models.ForeignKey(Biobank, on_delete=models.SET_NULL, null=True, blank=True, related_name="samples")
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="owned_samples")

    # Status e Governança
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default="private")
    is_active = models.BooleanField(default=True)
    
    # NOVOS CAMPOS (ELN e Dados Técnicos)
    scientific_notes = models.TextField(blank=True, null=True)
    spectrometry_data = models.JSONField(blank=True, null=True)

    # Metadados Físicos
    storage_location = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    # CLASSIFICAÇÃO (As ManyToMany que você mencionou)
    tags = models.ManyToManyField(Tag, blank=True, related_name="samples")
    keywords = models.ManyToManyField(KeywordValue, blank=True, related_name="samples")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        from core.models.samples.sample_files import move_sample_files
        
        # Herança de Biobank via Collection
        if self.collection:
            self.biobank = self.collection.biobank

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sample_id} ({self.get_status_display()})"