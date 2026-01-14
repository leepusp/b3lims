# core/forms.py
from django import forms
from core.models import Biobank, Collection, Tag

# ----------------------------------------------------------
# BIOBANK FORM
# ----------------------------------------------------------
class BiobankForm(forms.ModelForm):
    class Meta:
        model = Biobank
        fields = [
            "name",
            "institution",
            "visibility",
            "location_label",
            "latitude",
            "longitude",
            "description", # Alterado de 'notes' para 'description'
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "institution": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Search institution or address"
            }),
            "visibility": forms.Select(attrs={"class": "form-select"}),
            "location_label": forms.HiddenInput(),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
            "description": forms.Textarea(attrs={ # Alterado de 'notes'
                "class": "form-control",
                "rows": 4,
                "placeholder": "Relevant description about this Biobank"
            }),
        }

# ----------------------------------------------------------
# COLLECTION FORM
# ----------------------------------------------------------
class CollectionForm(forms.ModelForm):
    class Meta:
        model = Collection
        fields = ["name", "biobank", "description", "visibility"]

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Collection name"
            }),
            "biobank": forms.Select(attrs={
                "class": "form-select"
            }),
            "visibility": forms.Select(attrs={
                "class": "form-select"
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Describe the collection"
            }),
        }

# ----------------------------------------------------------
# TAG FORM
# ----------------------------------------------------------
class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }
