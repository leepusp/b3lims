# core/forms.py
from django import forms
from core.models import Biobank, Collection, Tag, Sample
from core.models import Bacteria, Phage, Plasmid
from core.models.samples.origin import SampleOrigin
from core.models.research_groups.model import ResearchGroup
from django.contrib.auth.models import User

from core.permissions.biobanks import editable_biobanks_for_user
from core.permissions.samples import (
    assignable_sample_owners_for_user,
    editable_sample_collections_for_user,
    sample_research_groups_for_user,
)

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
            "sample_id",
            "sample_type",
            "biosafety_level",
            "organism_name",
            "status",
            "aliquot_count",
            "is_public",
            "is_embargoed",
            "owner",
            "research_group",
            "biobank",
            "collections",
            "storage_location",
            "scientific_notes",
        ]
        labels = {
            "biosafety_level": "Biosafety Level",
            "aliquot_count": "Aliquot Count",
            "is_embargoed": "Sample Embargo",
            "research_group": "Research Group",
        }
        widgets = {
            "sample_id": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "readonly": "readonly",
                }
            ),
            "sample_type": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "readonly": "readonly",
                }
            ),
            "biosafety_level": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "organism_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "status": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "aliquot_count": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "1",
                    "step": "1",
                }
            ),
            "is_public": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
            "is_embargoed": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
            "owner": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "research_group": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "biobank": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "collections": forms.SelectMultiple(
                attrs={
                    "class": "form-select",
                    "size": "5",
                }
            ),
            "storage_location": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "scientific_notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                }
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if user is None:
            self._lock_existing_owner_field()
            return

        owner_qs = assignable_sample_owners_for_user(
            user
        )

        group_qs = sample_research_groups_for_user(
            user
        )

        biobank_qs = editable_biobanks_for_user(
            user
        )

        collection_qs = editable_sample_collections_for_user(
            user
        )

        if self.instance and self.instance.pk:
            if self.instance.owner_id:
                owner_ids = list(
                    owner_qs.values_list(
                        "pk",
                        flat=True,
                    )
                )

                if self.instance.owner_id not in owner_ids:
                    owner_ids.append(
                        self.instance.owner_id
                    )

                owner_qs = User.objects.filter(
                    pk__in=owner_ids
                )

            if self.instance.research_group_id:
                group_ids = list(
                    group_qs.values_list(
                        "pk",
                        flat=True,
                    )
                )

                if self.instance.research_group_id not in group_ids:
                    group_ids.append(
                        self.instance.research_group_id
                    )

                group_qs = ResearchGroup.objects.filter(
                    pk__in=group_ids
                )

            if self.instance.biobank_id:
                biobank_ids = list(
                    biobank_qs.values_list(
                        "pk",
                        flat=True,
                    )
                )

                if self.instance.biobank_id not in biobank_ids:
                    biobank_ids.append(
                        self.instance.biobank_id
                    )

                biobank_qs = Biobank.objects.filter(
                    pk__in=biobank_ids
                )

            current_collection_ids = list(
                self.instance.collections.values_list(
                    "pk",
                    flat=True,
                )
            )

            if current_collection_ids:
                editable_collection_ids = list(
                    collection_qs.values_list(
                        "pk",
                        flat=True,
                    )
                )

                collection_ids = list(
                    dict.fromkeys(
                        editable_collection_ids
                        + current_collection_ids
                    )
                )

                collection_qs = Collection.objects.filter(
                    pk__in=collection_ids
                )

        self.fields["owner"].queryset = owner_qs.order_by(
            "username"
        )
        self.fields["research_group"].queryset = group_qs.order_by(
            "name"
        )
        self.fields["biobank"].queryset = biobank_qs.order_by(
            "name"
        )
        self.fields["collections"].queryset = collection_qs.order_by(
            "name"
        )

        self._lock_existing_owner_field()

    def _lock_existing_owner_field(self):
        """
        Prevent implicit ownership transfer through the standard
        Sample ModelForm.

        Existing Sample files are contractually stored under the
        current owner's protected home directory. Ownership changes
        therefore require the dedicated Transfer Ownership workflow,
        which can coordinate database state, physical storage,
        integrity verification and audit logging.
        """
        if not (
            self.instance
            and self.instance.pk
        ):
            return

        owner_field = self.fields.get(
            "owner"
        )

        if owner_field is None:
            return

        # Existing Sample ownership is changed only through the dedicated transfer workflow.
        if self.instance.owner_id:
            owner_field.queryset = (
                User.objects
                .filter(
                    pk=self.instance.owner_id
                )
                .order_by(
                    "username"
                )
            )
        else:
            owner_field.queryset = (
                User.objects.none()
            )

        owner_field.disabled = True
        owner_field.help_text = (
            "Ownership cannot be changed from the standard "
            "Edit Sample form. Use the dedicated Transfer "
            "Ownership workflow."
        )


class SampleOriginForm(forms.ModelForm):
    class Meta:
        model = SampleOrigin
        fields = [
            "collection_site_name",
            "collection_date",
            "geo_loc_name",
            "country_or_ocean",
            "latitude",
            "longitude",
            "depth_m",
            "elevation_m",
            "habitat",
            "environmental_medium",
            "env_broad_scale",
            "env_local_scale",
            "collection_method",
            "notes",
            "location_visibility",
        ]
        widgets = {
            "collection_site_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Collection site or station"
                    ),
                }
            ),
            "collection_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "geo_loc_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Geographic region or locality"
                    ),
                }
            ),
            "country_or_ocean": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Brazil, Atlantic Ocean, Pacific Ocean..."
                    ),
                }
            ),
            "latitude": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.000001",
                    "min": "-90",
                    "max": "90",
                    "placeholder": "-23.550520",
                }
            ),
            "longitude": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.000001",
                    "min": "-180",
                    "max": "180",
                    "placeholder": "-46.633308",
                }
            ),
            "depth_m": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.001",
                    "min": "0",
                    "placeholder": "Depth in metres",
                }
            ),
            "elevation_m": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.001",
                    "placeholder": (
                        "Elevation relative to sea level"
                    ),
                }
            ),
            "habitat": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Marine water, sediment, soil, host..."
                    ),
                }
            ),
            "environmental_medium": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Ocean water, sediment, tissue..."
                    ),
                }
            ),
            "env_broad_scale": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "env_local_scale": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),
            "collection_method": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                }
            ),
            "location_visibility": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Geographic provenance itself is optional.
        # Do not make location visibility force creation of an empty
        # SampleOrigin record.
        self.fields["location_visibility"].required = False

        if not self.is_bound:
            self.fields[
                "location_visibility"
            ].initial = (
                SampleOrigin.LOCATION_INTERNAL
            )

    def clean_location_visibility(self):
        return (
            self.cleaned_data.get(
                "location_visibility"
            )
            or SampleOrigin.LOCATION_INTERNAL
        )


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
