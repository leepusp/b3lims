# core/permissions/samples.py
from core.permissions.generic import can_view_object, can_edit_object, can_delete_object

def _has_group_access(user, obj):
    """Verifica se o usuário é membro ou coordenador do grupo associado ao objeto."""
    if hasattr(obj, 'research_group') and obj.research_group:
        group = obj.research_group
        if group.coordinator == user or group.members.filter(id=user.id).exists():
            return True
    return False

def can_view_sample(user, sample):
    # 1. Regras genéricas (Dono, Superusuário, Público)
    if can_view_object(user, sample):
        return True
    # 2. Acesso direto via Grupo de Pesquisa na Amostra
    if _has_group_access(user, sample):
        return True
    # 3. Acesso herdado via Grupo de Pesquisa da Coleção
    for collection in sample.collections.all():
        if _has_group_access(user, collection):
            return True
    return False

def can_edit_sample(user, sample):
    # 1. Regras genéricas (Dono, Superusuário)
    if can_edit_object(user, sample):
        return True
    # 2. Acesso direto via Grupo de Pesquisa na Amostra
    if _has_group_access(user, sample):
        return True
    # 3. Acesso herdado via Grupo de Pesquisa da Coleção
    for collection in sample.collections.all():
        if _has_group_access(user, collection):
            return True
    return False

def can_delete_sample(user, sample):
    if can_delete_object(user, sample):
        return True
    
    # Apenas o Coordenador do Grupo pode apagar (membros comuns não)
    if sample.research_group and sample.research_group.coordinator == user:
        return True
        
    # Verifica coordenadores nas coleções
    for collection in sample.collections.all():
        if collection.research_group and collection.research_group.coordinator == user:
            return True
            
    return False


def visible_samples_for_user(user):
    """
    Return the active samples visible to a user.

    Visibility is intentionally centralized here so list pages, modal selectors,
    network views, and future dashboards do not expose samples outside the user's
    permissions.
    """
    from core.models.samples.sample import Sample

    qs = Sample.objects.filter(is_active=True).select_related(
        "biobank",
        "owner",
        "research_group",
    )

    if getattr(user, "is_superuser", False):
        return qs

    visible_ids = [
        sample.pk
        for sample in qs
        if can_view_sample(user, sample)
    ]

    return Sample.objects.filter(pk__in=visible_ids, is_active=True)
