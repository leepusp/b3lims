from django import forms
from django.db.models import Q

from bench.models import BookableResource
from core.models import ResearchGroup


def groups_managed_by(user):
    if user.is_superuser:
        return ResearchGroup.objects.all()
    return ResearchGroup.objects.filter(coordinator=user)


class ResourceForm(forms.ModelForm):
    class Meta:
        model = BookableResource
        fields = (
            "name", "description", "research_group", "color", "is_bookable",
            "max_minutes", "max_slots", "booking_window_days", "can_overlap",
            "users_can_book_in_past", "requires_note", "is_cancellable", "cancel_minutes",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "color": forms.TextInput(attrs={"type": "color", "class": "form-control form-control-color"}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = groups_managed_by(user)
        if self.instance.pk and self.instance.research_group_id:
            allowed = ResearchGroup.objects.filter(Q(pk__in=allowed) | Q(pk=self.instance.research_group_id))
        self.fields["research_group"].queryset = allowed
        self.fields["research_group"].required = True
        self.fields["research_group"].empty_label = "Choose a group"
        for name, field in self.fields.items():
            css = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else ("form-select" if isinstance(field.widget, forms.Select) else field.widget.attrs.get("class", "form-control"))
            field.widget.attrs["class"] = css
        if self.instance.pk and self.instance.research_group_id and self.instance.research_group_id not in set(
            groups_managed_by(user).values_list("pk", flat=True)
        ):
            self.fields["research_group"].disabled = True

    def clean_color(self):
        value = self.cleaned_data["color"]
        if not (len(value) == 7 and value.startswith("#")):
            raise forms.ValidationError("Use a colour like #0b66b2.")
        return value
