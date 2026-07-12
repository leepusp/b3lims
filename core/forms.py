# core/forms.py
from django import forms
from core.models import Biobank, Collection, Tag, Sample
from core.models import Bacteria, Phage, Plasmid

# ----------------------------------------------------------
# BIOBANK, COLLECTION & TAG FORMS
# ----------------------------------------------------------
class BiobankForm(forms.ModelForm):
    class Meta:
        model = Biobank
        fields = ["name", "is_public", "location_label", "latitude", "longitude", "description"]
        labels = {
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "is_public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "location_label": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Ex: Universidade de São Paulo, USP", "autocomplete": "off"
            }),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

class CollectionForm(forms.ModelForm):
    class Meta:
        model = Collection
        fields = ["name", "description", "is_public"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Collection name"}),
            "is_public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

# ----------------------------------------------------------
# 1. SAMPLE FORM (Base Form)
# ----------------------------------------------------------
class SampleForm(forms.ModelForm):
    class Meta:
        model = Sample
        fields = [
            "sample_id", "sample_type",
            "biosafety_level", "organism_name", 
            "status", "is_public", "storage_location",
            "biobank", "collections", "scientific_notes"
        ]
        labels = {
        }
        labels = {
            "biosafety_level": "Biosafety Level",
        }
        widgets = {
            "sample_id": forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}), 
            "biosafety_level": forms.Select(attrs={"class": "form-select"}),
            "sample_type": forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}),
            "organism_name": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "is_public": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "storage_location": forms.TextInput(attrs={"class": "form-control"}),
            "biobank": forms.Select(attrs={"class": "form-select"}),
            "collections": forms.SelectMultiple(attrs={"class": "form-select"}),
            "scientific_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

# ----------------------------------------------------------
# 2. BACTERIA FORM
# ----------------------------------------------------------
class BacteriaForm(SampleForm):
    resistance_markers_text = forms.CharField(
        required=False, label="Resistance Markers", 
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Ap100, Km50"})
    )

    class Meta(SampleForm.Meta):
        model = Bacteria
        fields = SampleForm.Meta.fields + ["official_name", "aliases", "genus", "species", "strain", "genotype", "isolation_source", "additional_info"]
        widgets = {
            **SampleForm.Meta.widgets,
            "official_name": forms.TextInput(attrs={"class": "form-control"}),
            "aliases": forms.TextInput(attrs={"class": "form-control"}),
            "genus": forms.TextInput(attrs={"class": "form-control"}),
            "species": forms.TextInput(attrs={"class": "form-control"}),
            "strain": forms.TextInput(attrs={"class": "form-control"}),
            "genotype": forms.TextInput(attrs={"class": "form-control"}),
            "isolation_source": forms.TextInput(attrs={"class": "form-control"}),
            "additional_info": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            markers = self.instance.resistance_markers
            if isinstance(markers, list):
                self.initial['resistance_markers_text'] = ", ".join(markers)

    def save(self, commit=True):
        instance = super().save(commit=False)
        markers_text = self.cleaned_data.get('resistance_markers_text', '')
        instance.resistance_markers = [m.strip() for m in markers_text.split(',') if m.strip()]
        if commit: instance.save()
        return instance

# ----------------------------------------------------------
# 3. PHAGE FORM
# ----------------------------------------------------------
class PhageForm(SampleForm):
    class Meta(SampleForm.Meta):
        model = Phage
        fields = SampleForm.Meta.fields + [
            "official_name", "aliases", "phage_name", "genus", "morphotype", 
            "taxonomy", "lifestyle", "isolation_source", "isolation_method", 
            "genome_type", "genome_size_bp", "temp_C", "ncbi_accession"
        ]
        widgets = {
            **SampleForm.Meta.widgets,
            "official_name": forms.TextInput(attrs={"class": "form-control"}),
            "aliases": forms.TextInput(attrs={"class": "form-control"}),
            "phage_name": forms.TextInput(attrs={"class": "form-control"}),
            "genus": forms.TextInput(attrs={"class": "form-control"}),
            "morphotype": forms.Select(attrs={"class": "form-select"}),
            "taxonomy": forms.TextInput(attrs={"class": "form-control"}),
            "lifestyle": forms.Select(attrs={"class": "form-select"}),
            "isolation_source": forms.TextInput(attrs={"class": "form-control"}),
            "isolation_method": forms.TextInput(attrs={"class": "form-control"}),
            "genome_type": forms.Select(attrs={"class": "form-select"}),
            "genome_size_bp": forms.NumberInput(attrs={"class": "form-control"}),
            "temp_C": forms.NumberInput(attrs={"class": "form-control", "step": "0.1"}),
            "ncbi_accession": forms.TextInput(attrs={"class": "form-control"}),
        }

# ----------------------------------------------------------
# 4. PLASMID FORM (Unified Vector + Insert)
# ----------------------------------------------------------
class PlasmidForm(SampleForm):
    backbone_resistance_markers_text = forms.CharField(
        required=False, label="Backbone Resistance Markers", 
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Ap100, Km50"})
    )
    insert_resistance_markers_text = forms.CharField(
        required=False, label="Insert Resistance Markers", 
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: Ap100, Km50"})
    )

    class Meta(SampleForm.Meta):
        model = Plasmid
        fields = SampleForm.Meta.fields + [
            "backbone_name", "backbone_aliases", "vector_type", "induction_system",
            "origin_of_replication", "backbone_size_bp", "is_empty_vector",
            "insert_name", "purpose", "insert_size_bp", "construction_name"
        ]
        widgets = {
            **SampleForm.Meta.widgets,
            "backbone_name": forms.TextInput(attrs={"class": "form-control"}),
            "backbone_aliases": forms.TextInput(attrs={"class": "form-control"}),
            "vector_type": forms.Select(attrs={"class": "form-select"}),
            "induction_system": forms.TextInput(attrs={"class": "form-control"}),
            "origin_of_replication": forms.TextInput(attrs={"class": "form-control"}),
            "backbone_size_bp": forms.NumberInput(attrs={"class": "form-control"}),
            "is_empty_vector": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "insert_name": forms.TextInput(attrs={"class": "form-control"}),
            "purpose": forms.TextInput(attrs={"class": "form-control"}),
            "insert_size_bp": forms.NumberInput(attrs={"class": "form-control"}),
            "construction_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Suggested: Backbone-Insert"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            b_markers = self.instance.backbone_resistance_markers
            i_markers = self.instance.insert_resistance_markers
            if isinstance(b_markers, list):
                self.initial['backbone_resistance_markers_text'] = ", ".join(b_markers)
            if isinstance(i_markers, list):
                self.initial['insert_resistance_markers_text'] = ", ".join(i_markers)

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        b_markers_text = self.cleaned_data.get('backbone_resistance_markers_text', '')
        i_markers_text = self.cleaned_data.get('insert_resistance_markers_text', '')
        
        instance.backbone_resistance_markers = [m.strip() for m in b_markers_text.split(',') if m.strip()]
        instance.insert_resistance_markers = [m.strip() for m in i_markers_text.split(',') if m.strip()]
        
        if commit: instance.save()
        return instance

# ----------------------------------------------------------
# DYNAMIC FORM SELECTOR
# ----------------------------------------------------------
def get_form_class_for_sample(sample_instance):
    if hasattr(sample_instance, 'bacteria'): return BacteriaForm
    if hasattr(sample_instance, 'phage'): return PhageForm
    if hasattr(sample_instance, 'plasmid'): return PlasmidForm
    return SampleForm
