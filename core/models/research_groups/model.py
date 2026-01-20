from django.db import models
from django.contrib.auth.models import User


class ResearchGroup(models.Model):
    """
    Grupo de pesquisa científico.

    Usado para agrupar usuários sob um coordenador,
    permitindo permissões hierárquicas e controle de acesso
    a coleções e amostras.
    """

    # =========================
    # IDENTIDADE
    # =========================
    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Nome do grupo de pesquisa",
    )

    description = models.TextField(
        blank=True,
        null=True,
        help_text="Descrição do grupo",
    )

    # =========================
    # GOVERNANÇA
    # =========================
    coordinator = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="coordinated_research_groups",
        help_text="Coordenador do grupo (pesquisador principal)",
    )

    members = models.ManyToManyField(
        User,
        related_name="research_groups",
        blank=True,
        help_text="Membros do grupo de pesquisa",
    )

    # =========================
    # METADADOS
    # =========================
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    # =========================
    # REPRESENTAÇÃO
    # =========================
    def __str__(self):
        return self.name
