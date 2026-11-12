from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from core.models.samples.sample_type import SampleType
from core.services import sample_types


@login_required
def sample_types_view(request, type_id=None):
    """List the Sample types of this installation and let an administrator add or change them."""
    can_edit = request.user.is_staff or request.user.is_superuser
    editing = get_object_or_404(SampleType, pk=type_id) if type_id else None

    if request.method == "POST":
        if not can_edit:
            return HttpResponseForbidden("Only administrators can change Sample types.")

        name = request.POST.get("name", "").strip()
        editing = get_object_or_404(SampleType, pk=request.POST["type_id"]) if request.POST.get("type_id") else None

        try:
            if not name:
                raise sample_types.SampleTypeError("Give the type a name.")

            if name.casefold() in {n.casefold() for n in sample_types.BUILTIN_TYPES}:
                raise sample_types.SampleTypeError(f"'{name}' is a built-in type; choose another name.")

            if SampleType.objects.filter(name__iexact=name).exclude(pk=editing.pk if editing else None).exists():
                raise sample_types.SampleTypeError(f"A type called '{name}' already exists.")

            fields = sample_types.parse_fields(request.POST.get("fields", ""))
            prefix = (request.POST.get("id_prefix") or "SMP-").strip().upper()[:12]
            obj = editing or SampleType(name=name)
            obj.name = name
            obj.slug = obj.slug or slugify(name)[:60] or f"type-{SampleType.objects.count() + 1}"
            obj.id_prefix = prefix if prefix.endswith("-") else prefix + "-"
            obj.has_organism = request.POST.get("has_organism") == "on"
            obj.default_biosafety = request.POST.get("default_biosafety", "").strip()
            obj.description = request.POST.get("description", "").strip()[:300]
            obj.is_active = request.POST.get("is_active", "on") == "on"
            obj.fields = fields

            if not editing and SampleType.objects.filter(slug=obj.slug).exists():
                obj.slug = f"{obj.slug}-{SampleType.objects.count() + 1}"

            obj.save()
            messages.success(request, f"Sample type '{obj.name}' saved.")

            return redirect("sample_types")
        except sample_types.SampleTypeError as exc:
            messages.error(request, str(exc))

    return render(request, "internal/samples/sample_types.html", {
        "types": SampleType.objects.all(),
        "editing": editing,
        "fields_text": sample_types.fields_to_text(editing.fields) if editing else "",
        "field_rows": [{**f, "choices_text": ", ".join(f.get("choices") or [])} for f in (editing.fields if editing else [])],
        "field_help": sample_types.FIELD_HELP,
        "can_edit": can_edit,
        "builtin_types": sample_types.BUILTIN_TYPES,
        "kinds": sample_types.KINDS,
    })
