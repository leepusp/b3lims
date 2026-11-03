"""Retired ELN Experimental entry point.

The synthetic DEMO-* preview was retired: the canonical ELN is the
Notebook. The URL is kept so bookmarks and old links still work.
Private drafts keep their own routes under this prefix.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_GET


@login_required
@require_GET
def eln_experimental_index(request):
    return redirect("notebook_index")
