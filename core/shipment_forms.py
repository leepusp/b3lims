from django import forms

from core.models import Shipment, ShipmentItem, TransportClassification


def _existing_model_fields(model, candidates):
    model_fields = {field.name for field in model._meta.fields}
    return [name for name in candidates if name in model_fields]


def _style_fields(form):
    for _name, field in form.fields.items():
        widget = field.widget

        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", "form-check-input")
        elif isinstance(widget, forms.Select):
            widget.attrs.setdefault("class", "form-select")
        elif isinstance(widget, forms.Textarea):
            widget.attrs.setdefault("class", "form-control")
            widget.attrs.setdefault("rows", 3)
        else:
            widget.attrs.setdefault("class", "form-control")


SHIPMENT_FIELDS = [
    "flow_type",
    "status",
    "origin_biobank",
    "destination_biobank",
    "sender_institution",
    "sender_name",
    "sender_email",
    "sender_phone",
    "sender_address",
    "recipient_institution",
    "recipient_name",
    "recipient_email",
    "recipient_phone",
    "recipient_address",
    "temperature",
    "transport_temperature",
    "transport_method",
    "carrier",
    "tracking_number",
    "expected_arrival",
    "notes",
]


SHIPMENT_ITEM_FIELDS = [
    "imported_sample_id",
    "material_name",
    "sample_type",
    "quantity",
    "quantity_unit",
    "container_count",
    "container_type",
    "storage_condition",
    "notes",
]


CLASSIFICATION_FIELDS = [
    "material_type",
    "risk_class",
    "biosafety_level",
    "is_ogm",
    "is_genetic_heritage",
    "is_international",
    "requires_un3373",
    "requires_triple_packaging",
]


class ShipmentSetupForm(forms.ModelForm):
    class Meta:
        model = Shipment
        fields = _existing_model_fields(Shipment, SHIPMENT_FIELDS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class ShipmentItemSetupForm(forms.ModelForm):
    class Meta:
        model = ShipmentItem
        fields = _existing_model_fields(ShipmentItem, SHIPMENT_ITEM_FIELDS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class TransportClassificationSetupForm(forms.ModelForm):
    class Meta:
        model = TransportClassification
        fields = _existing_model_fields(TransportClassification, CLASSIFICATION_FIELDS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


# ---------------------------------------------------------------------
# Transport classification UI standardization
# ---------------------------------------------------------------------
# The transport workflow uses user-facing labels consistently:
# Risk Class 1/2/3/4 and NB1/NB2/NB3/NB4. These labels are normalized by
# the requirements engine, so the UI can store either existing legacy values
# or the standardized labels below.

STANDARD_RISK_CLASS_CHOICES = [
    ("", "Not defined"),
    ("Risk Class 1", "Risk Class 1"),
    ("Risk Class 2", "Risk Class 2"),
    ("Risk Class 3", "Risk Class 3"),
    ("Risk Class 4", "Risk Class 4"),
]

STANDARD_BIOSAFETY_LEVEL_CHOICES = [
    ("", "Not defined"),
    ("NB1", "NB1"),
    ("NB2", "NB2"),
    ("NB3", "NB3"),
    ("NB4", "NB4"),
]

STANDARD_OGM_CHOICES = [
    ("false", "No"),
    ("true", "Yes"),
]


def _standardize_risk_value(value):
    raw = str(value or "").strip()
    low = raw.lower()

    if not raw:
        return ""

    if "4" in low:
        return "Risk Class 4"
    if "3" in low:
        return "Risk Class 3"
    if "2" in low:
        return "Risk Class 2"
    if "1" in low:
        return "Risk Class 1"

    return raw


def _standardize_nb_value(value):
    raw = str(value or "").strip()
    low = raw.lower()

    if not raw:
        return ""

    if "4" in low:
        return "NB4"
    if "3" in low:
        return "NB3"
    if "2" in low:
        return "NB2"
    if "1" in low:
        return "NB1"

    return raw


def _coerce_bool_or_false(value):
    if isinstance(value, bool):
        return value

    raw = str(value or "").strip().lower()

    return raw in {"true", "1", "yes", "sim", "s", "y"}


def _standardize_transport_classification_form_fields(form):
    if "risk_class" in form.fields:
        form.fields["risk_class"] = forms.ChoiceField(
            label="Risk Class",
            choices=STANDARD_RISK_CLASS_CHOICES,
            required=False,
        )

        if getattr(form, "instance", None) is not None:
            form.fields["risk_class"].initial = _standardize_risk_value(
                getattr(form.instance, "risk_class", "")
            )

    for field_name in ["biosafety_level", "nb_level", "containment_level"]:
        if field_name in form.fields:
            form.fields[field_name] = forms.ChoiceField(
                label="Nível de biossegurança",
                choices=STANDARD_BIOSAFETY_LEVEL_CHOICES,
                required=False,
            )

            if getattr(form, "instance", None) is not None:
                form.fields[field_name].initial = _standardize_nb_value(
                    getattr(form.instance, field_name, "")
                )

    if "is_ogm" in form.fields:
        form.fields["is_ogm"] = forms.TypedChoiceField(
            label="OGM",
            choices=STANDARD_OGM_CHOICES,
            coerce=_coerce_bool_or_false,
            empty_value=False,
            required=True,
        )

        if getattr(form, "instance", None) is not None:
            current = getattr(form.instance, "is_ogm", None)
            if current is True:
                form.fields["is_ogm"].initial = "true"
            elif current is False:
                form.fields["is_ogm"].initial = "false"
            else:
                form.fields["is_ogm"].initial = "false"


try:
    _original_transport_classification_setup_form_init = TransportClassificationSetupForm.__init__

    def _patched_transport_classification_setup_form_init(self, *args, **kwargs):
        _original_transport_classification_setup_form_init(self, *args, **kwargs)
        _standardize_transport_classification_form_fields(self)

    TransportClassificationSetupForm.__init__ = _patched_transport_classification_setup_form_init
except NameError:
    pass


# ---------------------------------------------------------------------
# Transport classification validation fallback
# ---------------------------------------------------------------------
# Prevent empty material_type and empty BooleanField values from reaching
# model.save() during shipment editing.

def _normalize_material_type_value(value, instance=None):
    raw = str(value or "").strip()

    if raw:
        return raw

    if instance is not None:
        current = str(getattr(instance, "material_type", "") or "").strip()
        if current:
            return current

    return "biological_material"


try:
    _original_transport_classification_setup_form_clean = TransportClassificationSetupForm.clean

    def _patched_transport_classification_setup_form_clean(self):
        cleaned_data = _original_transport_classification_setup_form_clean(self)

        if "material_type" in self.fields:
            cleaned_data["material_type"] = _normalize_material_type_value(
                cleaned_data.get("material_type"),
                instance=getattr(self, "instance", None),
            )

        for field in self.instance._meta.fields:
            if field.get_internal_type() != "BooleanField":
                continue

            name = field.name

            if name in cleaned_data and cleaned_data.get(name) in ["", None]:
                cleaned_data[name] = False

        return cleaned_data

    TransportClassificationSetupForm.clean = _patched_transport_classification_setup_form_clean
except NameError:
    pass


# ---------------------------------------------------------------------
# Final transport classification form hardening
# ---------------------------------------------------------------------
# material_type is required by the model/form, but the shipment workflow can
# derive a safe fallback from the existing classification or the generic
# biological material category.

def _final_transport_material_type_fallback(value, instance=None):
    raw = str(value or "").strip()

    if raw:
        return raw

    if instance is not None:
        current = str(getattr(instance, "material_type", "") or "").strip()
        if current:
            return current

    return "biological_material"


try:
    _previous_transport_classification_form_init = TransportClassificationSetupForm.__init__

    def _final_transport_classification_form_init(self, *args, **kwargs):
        _previous_transport_classification_form_init(self, *args, **kwargs)

        if "material_type" in self.fields:
            self.fields["material_type"].required = False

            current = _final_transport_material_type_fallback(
                getattr(getattr(self, "instance", None), "material_type", ""),
                instance=getattr(self, "instance", None),
            )
            self.fields["material_type"].initial = current

    TransportClassificationSetupForm.__init__ = _final_transport_classification_form_init
except NameError:
    pass


try:
    _previous_transport_classification_form_clean = TransportClassificationSetupForm.clean

    def _final_transport_classification_form_clean(self):
        cleaned_data = _previous_transport_classification_form_clean(self)

        if "material_type" in self.fields:
            cleaned_data["material_type"] = _final_transport_material_type_fallback(
                cleaned_data.get("material_type"),
                instance=getattr(self, "instance", None),
            )

        if getattr(self, "instance", None) is not None:
            for field in self.instance._meta.fields:
                if field.get_internal_type() != "BooleanField":
                    continue

                name = field.name

                if name in cleaned_data and cleaned_data.get(name) in ["", None]:
                    cleaned_data[name] = False

        return cleaned_data

    TransportClassificationSetupForm.clean = _final_transport_classification_form_clean
except NameError:
    pass


# ---------------------------------------------------------------------
# Final transport classification UI standardization
# ---------------------------------------------------------------------
# User-facing classification order:
# Material type -> Risk Class -> NB level -> OGM.
#
# Derived requirement flags are hidden from manual editing. They are
# recalculated by the shipment requirements engine after saving.

RISK_TO_NB_HELP_TEXT = (
    "Risk Class 1 → NB1; Risk Class 2 → NB2; "
    "Risk Class 3 → NB3; Risk Class 4 → NB4."
)

DERIVED_REQUIREMENT_FIELDS = {
    "requires_cibio_notification",
    "requires_ctnbio_authorization",
    "requires_mta_ttm",
    "requires_sisgen",
    "requires_triple_packaging",
    "requires_biohazard_label",
    "requires_un3373_label",
    "requires_external_package_identification",
    "is_category_b_un3373",
    "is_exempt_biological_material",
}


try:
    _previous_transport_classification_ui_init = TransportClassificationSetupForm.__init__

    def _classification_material_risk_nb_init(self, *args, **kwargs):
        _previous_transport_classification_ui_init(self, *args, **kwargs)

        if "material_type" in self.fields:
            self.fields["material_type"].label = "Material type"
            self.fields["material_type"].required = False
            self.fields["material_type"].help_text = (
                "Main material category used as the basis for transport classification."
            )

        if "risk_class" in self.fields:
            self.fields["risk_class"].label = "Risk Class"
            self.fields["risk_class"].help_text = RISK_TO_NB_HELP_TEXT
            self.fields["risk_class"].required = False

        for nb_field in ["biosafety_level", "nb_level", "containment_level"]:
            if nb_field in self.fields:
                self.fields[nb_field].label = "Nível de biossegurança"
                self.fields[nb_field].help_text = (
                    "Automatically associated with Risk Class; adjust only when technically justified."
                )
                self.fields[nb_field].required = False

        if "is_ogm" in self.fields:
            self.fields["is_ogm"].label = "OGM"
            self.fields["is_ogm"].help_text = (
                "Marque Sim apenas para Organismo Geneticamente Modificado."
            )
            self.fields["is_ogm"].required = True

        for field_name in DERIVED_REQUIREMENT_FIELDS:
            if field_name in self.fields:
                self.fields[field_name].widget = forms.HiddenInput()
                self.fields[field_name].required = False

    TransportClassificationSetupForm.__init__ = _classification_material_risk_nb_init
except NameError:
    pass


# ---------------------------------------------------------------------
# Final shipment transport classification form contract
# ---------------------------------------------------------------------
# UI contract:
# - Material type
# - Risk Class, with embedded NB mapping:
#     Risk 1 - NB1
#     Risk 2 - NB2
#     Risk 3 - NB3
#     Risk 4 - NB4
# - OGM
# - Is genetic heritage
# - Is international
#
# The NB/biosafety field and derived requirement flags are hidden and are
# filled/recalculated automatically.

FINAL_RISK_NB_CHOICES = [
    ("Risk Class 1", "Risk 1 - NB1"),
    ("Risk Class 2", "Risk 2 - NB2"),
    ("Risk Class 3", "Risk 3 - NB3"),
    ("Risk Class 4", "Risk 4 - NB4"),
]

FINAL_BOOLEAN_CHOICES = [
    ("false", "No"),
    ("true", "Yes"),
]

FINAL_RISK_TO_NB = {
    "Risk Class 1": "NB1",
    "Risk Class 2": "NB2",
    "Risk Class 3": "NB3",
    "Risk Class 4": "NB4",
}

FINAL_VISIBLE_BOOLEAN_HELP = {
    "is_ogm": "Indicates whether the material contains a genetically modified organism. If Yes, CIBio authorization/approval and traceability are required.",
    "is_genetic_heritage": "Indicates whether the shipment involves Brazilian genetic heritage or material subject to registration/control obligations.",
    "is_international": "Indicates whether this is an international transfer. If Yes, the document workflow may require additional transfer terms.",
}

FINAL_DERIVED_CLASSIFICATION_FIELDS = {
    "biosafety_level",
    "nb_level",
    "containment_level",
    "is_category_b_un3373",
    "is_exempt_biological_material",
    "requires_cibio_notification",
    "requires_ctnbio_authorization",
    "requires_mta_ttm",
    "requires_sisgen",
    "requires_triple_packaging",
    "requires_biohazard_label",
    "requires_un3373_label",
    "requires_external_package_identification",
}


def _final_bool_coerce(value):
    if isinstance(value, bool):
        return value

    raw = str(value or "").strip().lower()

    return raw in {"true", "1", "yes", "sim", "s", "y"}


def _final_normalize_risk(value):
    raw = str(value or "").strip()
    low = raw.lower()

    if "4" in low:
        return "Risk Class 4"
    if "3" in low:
        return "Risk Class 3"
    if "2" in low:
        return "Risk Class 2"
    if "1" in low:
        return "Risk Class 1"

    return "Risk Class 1"


def _final_nb_from_risk(risk_value):
    risk = _final_normalize_risk(risk_value)
    return FINAL_RISK_TO_NB.get(risk, "NB1")


def _final_material_type(value, instance=None):
    raw = str(value or "").strip()

    if raw:
        return raw

    if instance is not None:
        current = str(getattr(instance, "material_type", "") or "").strip()
        if current:
            return current

    return "biological_material"


def _final_set_select_class(field):
    css = field.widget.attrs.get("class", "")
    classes = set(css.split())
    classes.add("form-select")
    field.widget.attrs["class"] = " ".join(sorted(classes))


try:
    _classification_final_previous_init = TransportClassificationSetupForm.__init__

    def _classification_final_init(self, *args, **kwargs):
        _classification_final_previous_init(self, *args, **kwargs)

        instance = getattr(self, "instance", None)

        if "material_type" in self.fields:
            field = self.fields["material_type"]
            field.label = "Material type"
            field.required = False
            field.help_text = "Selecione a categoria principal do material transportado."
            _final_set_select_class(field)

            field.initial = _final_material_type(
                getattr(instance, "material_type", "") if instance is not None else "",
                instance=instance,
            )

        if "risk_class" in self.fields:
            field = self.fields["risk_class"]
            field.label = "Risk Class"
            field.choices = FINAL_RISK_NB_CHOICES
            field.required = True
            field.help_text = "Selecione a classe de risco já associada ao nível de biossegurança correspondente."
            field.widget = forms.Select(
                choices=FINAL_RISK_NB_CHOICES,
                attrs={"class": "form-select"},
            )
            field.initial = _final_normalize_risk(
                getattr(instance, "risk_class", "") if instance is not None else ""
            )

        for nb_field in ["biosafety_level", "nb_level", "containment_level"]:
            if nb_field in self.fields:
                field = self.fields[nb_field]
                field.required = False
                field.widget = forms.HiddenInput()
                field.initial = _final_nb_from_risk(
                    getattr(instance, "risk_class", "") if instance is not None else ""
                )

        for bool_field in ["is_ogm", "is_genetic_heritage", "is_international"]:
            if bool_field in self.fields:
                field = self.fields[bool_field]
                field.choices = FINAL_BOOLEAN_CHOICES
                field.required = True
                field.help_text = FINAL_VISIBLE_BOOLEAN_HELP.get(bool_field, "")
                field.widget = forms.Select(
                    choices=FINAL_BOOLEAN_CHOICES,
                    attrs={"class": "form-select"},
                )

                current = getattr(instance, bool_field, False) if instance is not None else False
                field.initial = "true" if current else "false"

        for field_name in FINAL_DERIVED_CLASSIFICATION_FIELDS:
            if field_name in self.fields:
                self.fields[field_name].required = False
                self.fields[field_name].widget = forms.HiddenInput()

    TransportClassificationSetupForm.__init__ = _classification_final_init
except NameError:
    pass


try:
    _classification_final_previous_clean = TransportClassificationSetupForm.clean

    def _classification_final_clean(self):
        cleaned_data = _classification_final_previous_clean(self)

        risk_class = _final_normalize_risk(cleaned_data.get("risk_class"))
        nb_level = _final_nb_from_risk(risk_class)

        cleaned_data["risk_class"] = risk_class

        if "material_type" in self.fields:
            cleaned_data["material_type"] = _final_material_type(
                cleaned_data.get("material_type"),
                instance=getattr(self, "instance", None),
            )

        for nb_field in ["biosafety_level", "nb_level", "containment_level"]:
            if nb_field in self.fields:
                cleaned_data[nb_field] = nb_level

        for bool_field in ["is_ogm", "is_genetic_heritage", "is_international"]:
            if bool_field in self.fields:
                cleaned_data[bool_field] = _final_bool_coerce(cleaned_data.get(bool_field))

        is_ogm = bool(cleaned_data.get("is_ogm"))
        is_genetic_heritage = bool(cleaned_data.get("is_genetic_heritage"))
        is_international = bool(cleaned_data.get("is_international"))
        risk_is_2_or_higher = risk_class in {"Risk Class 2", "Risk Class 3", "Risk Class 4"}

        derived_values = {
            "is_category_b_un3373": risk_is_2_or_higher,
            "is_exempt_biological_material": False,
            "requires_cibio_notification": is_ogm,
            "requires_ctnbio_authorization": False,
            "requires_mta_ttm": True,
            "requires_sisgen": is_genetic_heritage,
            "requires_triple_packaging": risk_is_2_or_higher,
            "requires_biohazard_label": is_ogm or risk_is_2_or_higher,
            "requires_un3373_label": risk_is_2_or_higher,
            "requires_external_package_identification": True,
        }

        for field_name, value in derived_values.items():
            if field_name in self.fields:
                cleaned_data[field_name] = value

        if getattr(self, "instance", None) is not None:
            for field in self.instance._meta.fields:
                if field.get_internal_type() != "BooleanField":
                    continue

                name = field.name

                if name in cleaned_data and cleaned_data.get(name) in ["", None]:
                    cleaned_data[name] = False

        return cleaned_data

    TransportClassificationSetupForm.clean = _classification_final_clean
except NameError:
    pass


# ---------------------------------------------------------------------
# Absolute final override for transport classification form fields
# ---------------------------------------------------------------------
# This block replaces problematic ModelForm-generated fields with explicit
# controlled UI fields. It prevents invalid_choice and BooleanField required
# errors during shipment editing.

FINAL_MATERIAL_TYPE_CHOICES = [
    ("Bacteria", "Bacteria"),
    ("Phage", "Phage"),
    ("Plasmid", "Plasmid"),
    ("Protein", "Protein"),
    ("DNA", "DNA"),
    ("RNA", "RNA"),
    ("Biological material", "Biological material"),
    ("Other", "Other"),
]

FINAL_RISK_CHOICES = [
    ("Risk Class 1", "Risk 1 - NB1"),
    ("Risk Class 2", "Risk 2 - NB2"),
    ("Risk Class 3", "Risk 3 - NB3"),
    ("Risk Class 4", "Risk 4 - NB4"),
]

FINAL_YES_NO_CHOICES = [
    ("false", "No"),
    ("true", "Yes"),
]

FINAL_BOOLEAN_HELP_TEXTS = {
    "is_ogm": (
        "Indica se o material contém Organismo Geneticamente Modificado. "
        "Quando Sim, o sistema exige autorização/anuência CIBio e traceability."
    ),
    "is_genetic_heritage": (
        "Indicates whether the shipment involves Brazilian genetic heritage or material subject to "
        "registration, control, or traceability obligations."
    ),
    "is_international": (
        "Indica se a transferência é internacional. Quando Sim, o fluxo documental pode "
        "exigir termos adicionais de transferência."
    ),
}

FINAL_HIDDEN_DERIVED_FIELDS = {
    "biosafety_level",
    "nb_level",
    "containment_level",
    "is_category_b_un3373",
    "is_exempt_biological_material",
    "requires_cibio_notification",
    "requires_ctnbio_authorization",
    "requires_mta_ttm",
    "requires_sisgen",
    "requires_triple_packaging",
    "requires_biohazard_label",
    "requires_un3373_label",
    "requires_external_package_identification",
}


def _final_bool(value):
    if isinstance(value, bool):
        return value

    raw = str(value or "").strip().lower()

    return raw in {"true", "1", "yes", "sim", "s", "y"}


def _final_risk(value):
    raw = str(value or "").strip().lower()

    if "4" in raw:
        return "Risk Class 4"
    if "3" in raw:
        return "Risk Class 3"
    if "2" in raw:
        return "Risk Class 2"
    if "1" in raw:
        return "Risk Class 1"

    return "Risk Class 1"


def _final_nb(value):
    risk = _final_risk(value)

    return {
        "Risk Class 1": "NB1",
        "Risk Class 2": "NB2",
        "Risk Class 3": "NB3",
        "Risk Class 4": "NB4",
    }.get(risk, "NB1")


def _final_material(value, instance=None):
    raw = str(value or "").strip()

    if raw:
        low = raw.lower()

        if low == "bacteria":
            return "Bacteria"
        if low == "phage":
            return "Phage"
        if low == "plasmid":
            return "Plasmid"
        if low == "protein":
            return "Protein"
        if low == "dna":
            return "DNA"
        if low == "rna":
            return "RNA"

        return raw

    if instance is not None:
        current = str(getattr(instance, "material_type", "") or "").strip()
        if current:
            return _final_material(current)

    return "Biological material"


def _select_attrs():
    return {"class": "form-select"}


try:
    _absolute_previous_tcf_init = TransportClassificationSetupForm.__init__

    def _absolute_tcf_init(self, *args, **kwargs):
        _absolute_previous_tcf_init(self, *args, **kwargs)

        instance = getattr(self, "instance", None)

        if "material_type" in self.fields:
            initial_material = _final_material(
                getattr(instance, "material_type", "") if instance is not None else "",
                instance=instance,
            )

            self.fields["material_type"] = forms.ChoiceField(
                label="Material type",
                choices=FINAL_MATERIAL_TYPE_CHOICES,
                required=True,
                initial=initial_material,
                help_text="Selecione a categoria principal do material transportado.",
                widget=forms.Select(attrs=_select_attrs()),
            )

        if "risk_class" in self.fields:
            initial_risk = _final_risk(
                getattr(instance, "risk_class", "") if instance is not None else ""
            )

            self.fields["risk_class"] = forms.ChoiceField(
                label="Risk Class",
                choices=FINAL_RISK_CHOICES,
                required=True,
                initial=initial_risk,
                help_text=(
                    "Selecione a classe de risco já associada ao nível de biossegurança: "
                    "Risk 1 - NB1, Risk 2 - NB2, Risk 3 - NB3, Risk 4 - NB4."
                ),
                widget=forms.Select(attrs=_select_attrs()),
            )

        for field_name in ["is_ogm", "is_genetic_heritage", "is_international"]:
            if field_name in self.fields:
                current = getattr(instance, field_name, False) if instance is not None else False

                self.fields[field_name] = forms.TypedChoiceField(
                    label=self.fields[field_name].label,
                    choices=FINAL_YES_NO_CHOICES,
                    coerce=_final_bool,
                    empty_value=False,
                    required=True,
                    initial="true" if current else "false",
                    help_text=FINAL_BOOLEAN_HELP_TEXTS.get(field_name, ""),
                    widget=forms.Select(attrs=_select_attrs()),
                )

        for field_name in FINAL_HIDDEN_DERIVED_FIELDS:
            if field_name in self.fields:
                self.fields[field_name].required = False
                self.fields[field_name].widget = forms.HiddenInput()

    TransportClassificationSetupForm.__init__ = _absolute_tcf_init
except NameError:
    pass


try:
    _absolute_previous_tcf_clean = TransportClassificationSetupForm.clean

    def _absolute_tcf_clean(self):
        cleaned_data = _absolute_previous_tcf_clean(self)

        risk = _final_risk(cleaned_data.get("risk_class"))
        nb = _final_nb(risk)

        if "material_type" in self.fields:
            cleaned_data["material_type"] = _final_material(
                cleaned_data.get("material_type"),
                instance=getattr(self, "instance", None),
            )

        if "risk_class" in self.fields:
            cleaned_data["risk_class"] = risk

        for field_name in ["biosafety_level", "nb_level", "containment_level"]:
            if field_name in self.fields:
                cleaned_data[field_name] = nb

        for field_name in ["is_ogm", "is_genetic_heritage", "is_international"]:
            if field_name in self.fields:
                cleaned_data[field_name] = _final_bool(cleaned_data.get(field_name))

        is_ogm = bool(cleaned_data.get("is_ogm"))
        is_genetic_heritage = bool(cleaned_data.get("is_genetic_heritage"))
        risk_is_2_or_higher = risk in {"Risk Class 2", "Risk Class 3", "Risk Class 4"}

        derived = {
            "is_category_b_un3373": risk_is_2_or_higher,
            "is_exempt_biological_material": False,
            "requires_cibio_notification": is_ogm,
            "requires_ctnbio_authorization": False,
            "requires_mta_ttm": True,
            "requires_sisgen": is_genetic_heritage,
            "requires_triple_packaging": risk_is_2_or_higher,
            "requires_biohazard_label": is_ogm or risk_is_2_or_higher,
            "requires_un3373_label": risk_is_2_or_higher,
            "requires_external_package_identification": True,
        }

        for field_name, value in derived.items():
            if field_name in self.fields:
                cleaned_data[field_name] = value

        if getattr(self, "instance", None) is not None:
            for field in self.instance._meta.fields:
                if field.get_internal_type() == "BooleanField":
                    name = field.name
                    if name in cleaned_data and cleaned_data.get(name) in ["", None]:
                        cleaned_data[name] = False

        return cleaned_data

    TransportClassificationSetupForm.clean = _absolute_tcf_clean
except NameError:
    pass



# ---------------------------------------------------------------------
# Compatibility layer for transport classification choices
# ---------------------------------------------------------------------
# The UI shows standardized labels, but the database model may store legacy
# values such as "phage", "plasmid", "risk_class_2", etc. This layer maps
# visible labels and aliases to the model-compatible choice values.

class FlexibleTransportChoiceField(forms.ChoiceField):
    def __init__(self, *args, aliases=None, **kwargs):
        self.aliases = set(str(value) for value in (aliases or []))
        super().__init__(*args, **kwargs)

    def valid_value(self, value):
        return super().valid_value(value) or str(value) in self.aliases


def _model_field_choices(model, field_name):
    try:
        field = model._meta.get_field(field_name)
    except Exception:
        return []

    return [(value, label) for value, label in (field.choices or [])]


def _find_model_choice(model, field_name, targets, fallback):
    choices = _model_field_choices(model, field_name)

    if not choices:
        return fallback

    for target in targets:
        target = str(target).lower()

        for value, label in choices:
            combined = f"{value} {label}".lower()

            if target in combined:
                return value

    values = [value for value, _label in choices]

    if fallback in values:
        return fallback

    return values[0]


def _build_material_choice_maps(model):
    specs = [
        ("Bacteria", "Bacteria", ["bacteria"]),
        ("Phage", "Phage", ["phage", "bacteriophage"]),
        ("Plasmid", "Plasmid", ["plasmid"]),
        ("Protein", "Protein", ["protein"]),
        ("DNA", "DNA", ["dna"]),
        ("RNA", "RNA", ["rna"]),
        ("Biological material", "Biological material", ["biological", "material"]),
        ("Other", "Other", ["other"]),
    ]

    choices = []
    aliases = {}
    seen = set()

    for alias, label, targets in specs:
        model_value = _find_model_choice(
            model,
            "material_type",
            targets=targets,
            fallback=alias,
        )

        if model_value not in seen:
            choices.append((model_value, label))
            seen.add(model_value)

        aliases[alias] = model_value
        aliases[label] = model_value
        aliases[str(model_value)] = model_value

    return choices, aliases


def _build_risk_choice_maps(model):
    specs = [
        ("Risk Class 1", "Risk 1 - NB1", ["risk_class_1", "risk class 1", "risk 1", "class 1", "1"]),
        ("Risk Class 2", "Risk 2 - NB2", ["risk_class_2", "risk class 2", "risk 2", "class 2", "2"]),
        ("Risk Class 3", "Risk 3 - NB3", ["risk_class_3", "risk class 3", "risk 3", "class 3", "3"]),
        ("Risk Class 4", "Risk 4 - NB4", ["risk_class_4", "risk class 4", "risk 4", "class 4", "4"]),
    ]

    choices = []
    aliases = {}
    seen = set()

    for alias, label, targets in specs:
        model_value = _find_model_choice(
            model,
            "risk_class",
            targets=targets,
            fallback=alias,
        )

        if model_value not in seen:
            choices.append((model_value, label))
            seen.add(model_value)

        aliases[alias] = model_value
        aliases[label] = model_value
        aliases[str(model_value)] = model_value

    return choices, aliases


def _risk_number(value):
    raw = str(value or "").lower()

    if "4" in raw:
        return "4"
    if "3" in raw:
        return "3"
    if "2" in raw:
        return "2"
    return "1"


def _nb_from_any_risk(value):
    return {
        "1": "NB1",
        "2": "NB2",
        "3": "NB3",
        "4": "NB4",
    }.get(_risk_number(value), "NB1")


def _bool_from_choice(value):
    if isinstance(value, bool):
        return value

    raw = str(value or "").strip().lower()

    return raw in {"true", "1", "yes", "sim", "s", "y"}


def _yes_no_field(label, initial=False, help_text=""):
    return forms.TypedChoiceField(
        label=label,
        choices=[("false", "No"), ("true", "Yes")],
        coerce=_bool_from_choice,
        empty_value=False,
        required=True,
        initial="true" if initial else "false",
        help_text=help_text,
        widget=forms.Select(attrs={"class": "form-select"}),
    )


try:
    _compat_previous_tcf_init = TransportClassificationSetupForm.__init__

    def _compat_tcf_init(self, *args, **kwargs):
        _compat_previous_tcf_init(self, *args, **kwargs)

        model = self._meta.model
        instance = getattr(self, "instance", None)

        self._material_aliases = {}
        self._risk_aliases = {}

        if "material_type" in self.fields:
            choices, aliases = _build_material_choice_maps(model)
            self._material_aliases = aliases

            current = getattr(instance, "material_type", "") if instance is not None else ""
            current = aliases.get(str(current), current)

            self.fields["material_type"] = FlexibleTransportChoiceField(
                label="Material type",
                choices=choices,
                aliases=aliases.keys(),
                required=True,
                initial=current or choices[0][0],
                help_text="Selecione a categoria principal do material transportado.",
                widget=forms.Select(attrs={"class": "form-select"}),
            )

        if "risk_class" in self.fields:
            choices, aliases = _build_risk_choice_maps(model)
            self._risk_aliases = aliases

            current = getattr(instance, "risk_class", "") if instance is not None else ""
            current = aliases.get(str(current), current)

            self.fields["risk_class"] = FlexibleTransportChoiceField(
                label="Risk Class",
                choices=choices,
                aliases=aliases.keys(),
                required=True,
                initial=current or choices[0][0],
                help_text="Risk Class já associado ao nível: Risk 1 - NB1, Risk 2 - NB2, Risk 3 - NB3, Risk 4 - NB4.",
                widget=forms.Select(attrs={"class": "form-select"}),
            )

        boolean_help = {
            "is_ogm": "Indicates whether the material contains a genetically modified organism. If Yes, CIBio authorization/approval and traceability are required.",
            "is_genetic_heritage": "Indicates whether the shipment involves Brazilian genetic heritage or material subject to registration, control, or traceability obligations.",
            "is_international": "Indicates whether this is an international transfer. If Yes, the document workflow may require additional transfer terms.",
        }

        for field_name in ["is_ogm", "is_genetic_heritage", "is_international"]:
            if field_name in self.fields:
                current = getattr(instance, field_name, False) if instance is not None else False
                label = self.fields[field_name].label or field_name.replace("_", " ").title()

                self.fields[field_name] = _yes_no_field(
                    label=label,
                    initial=current,
                    help_text=boolean_help.get(field_name, ""),
                )

        hidden_fields = {
            "biosafety_level",
            "nb_level",
            "containment_level",
            "is_category_b_un3373",
            "is_exempt_biological_material",
            "requires_cibio_notification",
            "requires_ctnbio_authorization",
            "requires_mta_ttm",
            "requires_sisgen",
            "requires_triple_packaging",
            "requires_biohazard_label",
            "requires_un3373_label",
            "requires_external_package_identification",
        }

        for field_name in hidden_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False
                self.fields[field_name].widget = forms.HiddenInput()

    TransportClassificationSetupForm.__init__ = _compat_tcf_init
except NameError:
    pass


try:
    def _compat_tcf_clean(self):
        cleaned_data = super(TransportClassificationSetupForm, self).clean()

        material_value = cleaned_data.get("material_type")
        risk_value = cleaned_data.get("risk_class")

        material_aliases = getattr(self, "_material_aliases", {})
        risk_aliases = getattr(self, "_risk_aliases", {})

        if "material_type" in self.fields:
            cleaned_data["material_type"] = material_aliases.get(
                str(material_value),
                material_value,
            )

        if "risk_class" in self.fields:
            risk_model_value = risk_aliases.get(str(risk_value), risk_value)
            cleaned_data["risk_class"] = risk_model_value
        else:
            risk_model_value = risk_value

        nb_value = _nb_from_any_risk(risk_value or risk_model_value)

        for field_name in ["biosafety_level", "nb_level", "containment_level"]:
            if field_name in self.fields:
                cleaned_data[field_name] = nb_value

        for field_name in ["is_ogm", "is_genetic_heritage", "is_international"]:
            if field_name in self.fields:
                cleaned_data[field_name] = _bool_from_choice(cleaned_data.get(field_name))

        risk_is_2_or_higher = _risk_number(risk_value or risk_model_value) in {"2", "3", "4"}
        is_ogm = bool(cleaned_data.get("is_ogm"))
        is_genetic_heritage = bool(cleaned_data.get("is_genetic_heritage"))

        derived_values = {
            "is_category_b_un3373": risk_is_2_or_higher,
            "is_exempt_biological_material": False,
            "requires_cibio_notification": is_ogm,
            "requires_ctnbio_authorization": False,
            "requires_mta_ttm": True,
            "requires_sisgen": is_genetic_heritage,
            "requires_triple_packaging": risk_is_2_or_higher,
            "requires_biohazard_label": is_ogm or risk_is_2_or_higher,
            "requires_un3373_label": risk_is_2_or_higher,
            "requires_external_package_identification": True,
        }

        for field_name, value in derived_values.items():
            if field_name in self.fields:
                cleaned_data[field_name] = value

        if getattr(self, "instance", None) is not None:
            for field in self.instance._meta.fields:
                if field.get_internal_type() == "BooleanField":
                    name = field.name
                    if name in cleaned_data and cleaned_data.get(name) in ["", None]:
                        cleaned_data[name] = False

        return cleaned_data

    TransportClassificationSetupForm.clean = _compat_tcf_clean
except NameError:
    pass
