from django.db import models
from django.contrib.auth.models import User

from core.models.tags.model import Tag
from core.models.keywords.model import KeywordValue
from core.models.research_groups.model import ResearchGroup

class Biobank(models.Model):
    """
    Entidade máxima do sistema. Representa uma unidade física ou
    consórcio de guarda de material biológico.
    """

    # =========================
    # METADADOS BÁSICOS
    # =========================
    name = models.CharField(max_length=200)

    description = models.TextField(
        blank=True,
        null=True,
        help_text="Descrição institucional do Biobanco"
    )

    # =========================
    # LOCALIZAÇÃO
    # =========================
    location_label = models.CharField(
        max_length=255,
        blank=True,
        help_text="Endereço legível (Ex: Prédio da Manutenção - IQ-USP)"
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    # =========================
    # GOVERNANÇA / PERMISSÕES
    # =========================
    owner = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="owned_biobanks",
        help_text="Gestor principal do Biobanco"
    )

    research_group = models.ForeignKey(
        ResearchGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="biobanks",
        help_text="Grupo de pesquisa responsável pelo Biobanco"
    )

    # Novo formato simplificado
    is_public = models.BooleanField(
        default=False,
        help_text="Marque para disponibilizar este biobanco publicamente"
    )

    # =========================
    # CICLO DE VIDA
    # =========================
    is_active = models.BooleanField(
        default=True,
        help_text="Indica se o Biobanco está operacional"
    )

    # =========================
    # CLASSIFICAÇÃO
    # =========================
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="biobanks",
    )

    keywords = models.ManyToManyField(
        KeywordValue,
        blank=True,
        related_name="biobanks",
    )

    # =========================
    # REPRESENTAÇÃO
    # =========================
    def __str__(self):
        return self.name
