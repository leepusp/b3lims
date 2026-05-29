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
