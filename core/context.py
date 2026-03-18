from django.db.models import Q
from core.models import Biobank, Collection, Sample, Tag, Keyword, KeywordValue

def base_context(request, public: bool = False):
    user = request.user

    if public:
        return {"request": request, "user": user, "is_public": True}

    all_keywords = Keyword.objects.all().order_by("name")

    if user.is_superuser:
        collections = Collection.objects.all()
        samples = Sample.objects.all()
    else:
        # Nova lógica: visível se for público ou se o usuário for o dono
        collections = Collection.objects.filter(Q(owner=user) | Q(is_public=True)).distinct()
        samples = Sample.objects.filter(Q(owner=user) | Q(is_public=True)).distinct()

    biobanks = Biobank.objects.filter(is_active=True)

    # Verifica se o usuário é OWNER de alguma collection diretamente
    is_owner_of_any = Collection.objects.filter(owner=user).exists()
    can_manage_permissions = user.is_superuser or is_owner_of_any

    return {
        "request": request, "user": user, "is_public": False,
        "biobanks": biobanks, "collections": collections, "samples": samples,
        "all_keywords": all_keywords,
        "biobank_form": None, "collection_form": None, "sample_form": None,
        "can_manage_permissions": can_manage_permissions,
        "selected_collection": None,
    }
