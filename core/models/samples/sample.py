import uuid
from django.db import models
from django.contrib.auth.models import User

# Imports ajustados para a nova estrutura de diretórios
from core.models.collections.collection import Collection
from core.models.biobanks.biobank import Biobank
from core.models.tags import Tag
from core.models.keywords import KeywordValue

class Sample(models.Model):
    """
    Amostra biológica armazenada no Biobank.
    Hierarquia opcional: Biobank → Collection (opcional) → Sample
    """

    # =========================
    # LIMS / CONTROLE DE QUALIDADE
    # =========================
    STATUS_CHOICES = [
        ('pending', 'Aguardando Recebimento'),
        ('qc', 'Em Controle de Qualidade'),
        ('available', 'Disponível / Aprovada'),
        ('rejected', 'Rejeitada / Inviável'),
        ('depleted', 'Exaurida'),
    ]

    # =========================
    # IDENTIFICAÇÃO ÚNICA
    # =========================
    # UUID para rastreabilidade universal e QR Codes
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    # ID visível/etiqueta fornecido pelo usuário
    sample_id = models.CharField(max_length=100, unique=True)

    sample_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Ex: Isolado Bacteriano, Plasmídeo, Fago"
    )

    organism_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    # =========================
    # VÍNCULOS HIERÁRQUICOS
    # =========================
    collection = models.ForeignKey(
        Collection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="samples",
        help_text="Coleção à qual a amostra pertence (opcional para amostras avulsas)"
    )

    biobank = models.ForeignKey(
        Biobank,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="samples",
    )

    # =========================
    # GOVERNANÇA / PERMISSÕES
    # =========================
    owner = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="owned_samples",
        help_text="Responsável pela amostra",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    VISIBILITY_CHOICES = [
        ("private", "Privada"),
        ("group", "Grupo de pesquisa"),
        ("biobank", "Biobank"),
        ("public", "Pública"),
    ]

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="private",
    )

    # =========================
    # CICLO DE VIDA
    # =========================
    is_active = models.BooleanField(
        default=True,
        help_text="Indica se a Sample está ativa para uso",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # =========================
    # METADADOS FÍSICOS
    # =========================
    storage_location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Posição física: Freezer, Rack, Caixa, Posição"
    )

    notes = models.TextField(blank=True, null=True)

    # =========================
    # CLASSIFICAÇÃO
    # =========================
    tags = models.ManyToManyField(Tag, blank=True, related_name="samples")
    keywords = models.ManyToManyField(KeywordValue, blank=True, related_name="samples")

    # =========================
    # LÓGICA DE PERSISTÊNCIA
    # =========================
    def save(self, *args, **kwargs):
        # CORREÇÃO AQUI: Importação atualizada para o novo caminho da pasta samples
        from core.models.samples.sample_files import move_sample_files

        old_collection_id = None
        if self.pk:
            old_collection_id = (
                Sample.objects.filter(pk=self.pk)
                .values_list("collection_id", flat=True)
                .first()
            )

        # Herança automática do Biobank via Coleção
        if self.collection:
            self.biobank = self.collection.biobank

        super().save(*args, **kwargs)

        # Se a amostra acabou de ser movida para uma coleção, movemos os arquivos físicos
        if self.collection and old_collection_id is None:
            move_sample_files(self)

    # =========================
    # REPRESENTAÇÃO
    # =========================
    def __str__(self):
        return f"{self.sample_id} ({self.get_status_display()})"