from django.db import models
from django.contrib.auth.models import User

# Imports atualizados para a nova hierarquia de diretórios
from core.models.tags import Tag
from core.models.keywords import KeywordValue

# NOVO: Importação do Grupo de Pesquisa
from core.models.research_groups.model import ResearchGroup

class Collection(models.Model):
    """
    Coleção científica independente.
    Controla acesso, visibilidade e governança de amostras.
    No contexto do CEPID B3, agrupa linhagens por projeto ou laboratório,
    podendo conter amostras de MÚLTIPLOS biobancos físicos.
    """

    # =========================
    # METADADOS BÁSICOS
    # =========================
    name = models.CharField(max_length=200)
    description = models.TextField(
        blank=True, 
        null=True, 
        help_text="Finalidade científica da coleção"
    )

    # =========================
    # GOVERNANÇA / PERMISSÕES
    # =========================
    owner = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="owned_collections",
        help_text="Responsável científico/PI pela coleção",
    )

    # NOVO: Vínculo com o Laboratório/Grupo de Pesquisa (Pilar 1)
    research_group = models.ForeignKey(
        ResearchGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collections",
        help_text="Grupo de Pesquisa ao qual esta coleção pertence."
    )

    # Novo formato simplificado
    is_public = models.BooleanField(
        default=False,
        help_text="Marque para disponibilizar esta coleção publicamente"
    )

    # =========================
    # CICLO DE VIDA E AUDITORIA
    # =========================
    is_active = models.BooleanField(
        default=True,
        editable=False,
        help_text="Indica se a Collection está ativa para novos cadastros",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # =========================
    # CLASSIFICAÇÃO
    # =========================
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="collections",
    )

    keywords = models.ManyToManyField(
        KeywordValue,
        blank=True,
        related_name="collections",
    )

    # =========================
    # REPRESENTAÇÃO
    # =========================
    def __str__(self):
        return self.name


class CollectionLifecycleEvent(models.Model):
    """
    Append-only audit record for Collection lifecycle transitions.

    The Collection boolean stores the current materialized state.
    This model preserves who performed each audited transition and
    when it occurred.
    """

    class EventType(models.TextChoices):
        DEACTIVATED = (
            "deactivated",
            "Deactivated",
        )
        REACTIVATED = (
            "reactivated",
            "Reactivated",
        )

    collection = models.ForeignKey(
        Collection,
        on_delete=models.PROTECT,
        related_name="lifecycle_events",
    )

    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
    )

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collection_lifecycle_events",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    notes = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = [
            "created_at",
            "pk",
        ]
        verbose_name = (
            "Collection lifecycle event"
        )
        verbose_name_plural = (
            "Collection lifecycle events"
        )

    def __str__(self):
        return (
            f"{self.collection} - "
            f"{self.get_event_type_display()}"
        )
