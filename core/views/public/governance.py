from django.shortcuts import render
from django.views.decorators.http import require_safe
from core.context import base_context


@require_safe
def public_governance(request):
    context = {}
    context.update(base_context(request, public=True))

    return render(
        request,
        "public/governance.html",
        context
    )
