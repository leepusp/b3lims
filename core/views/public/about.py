from django.shortcuts import render
from django.views.decorators.http import require_safe
from core.context import base_context


@require_safe
def public_about(request):
    context = {}
    context.update(base_context(request, public=True))

    return render(
        request,
        "public/about.html",
        context
    )
