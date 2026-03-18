# core/permissions/generic.py

def _is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff)

def can_view_object(user, obj):
    """
    Regra de visualização:
    - Se o objeto for público (checkbox marcado), é visível.
    - Se não for público, apenas o dono (user que criou) ou admin podem ver.
    """
    # Checa se o objeto tem um campo booleano 'is_public' marcado como True
    # (ou se o campo antigo 'visibility' ainda estiver setado como 'public' durante a transição)
    if getattr(obj, 'is_public', False) or getattr(obj, 'visibility', '') == 'public':
        return True
        
    if not user.is_authenticated:
        return False
        
    if _is_admin(user):
        return True
        
    # Dono sempre pode ver
    return obj.owner == user

def can_edit_object(user, obj):
    """
    Regra de edição:
    - Apenas o dono ou um administrador podem editar.
    """
    if not user.is_authenticated:
        return False
        
    if _is_admin(user):
        return True
        
    return obj.owner == user

def can_delete_object(user, obj):
    """
    Regra de exclusão:
    - Apenas o dono ou um administrador podem deletar.
    """
    return can_edit_object(user, obj)
