from django.db import models
from django.contrib.auth.models import User

# Imports atualizados para a nova estrutura de diretórios
from core.models.tags import Tag
from core.models.keywords import KeywordValue


class Biobank(models.Model):
    """
    Entidade máxima do sistema. Representa uma unidade física ou 
    consórcio de guarda de material biológico.
    """

    # =========================
    # METADADOS BÁSICOS
    # =========================
    name = models.CharField(max_length=200)
    institution = models.CharField(max_length=255)
    description = models.TextField(
        blank=True, 
        null=True, 
        help_text="Descrição institucional do Biobanco"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

    VISIBILITY_CHOICES = [
        ("private", "Privado"),
        ("biobank", "Restrito ao Biobank"),
        ("public", "Público"),
    ]

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="biobank",
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