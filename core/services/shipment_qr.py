import base64
from io import BytesIO

import qrcode
from django.urls import reverse


def build_internal_shipment_scan_url(request, shipment):
    path = reverse("shipment_scan", kwargs={"shipment_uuid": shipment.uuid})
    return request.build_absolute_uri(path)


def build_qr_data_uri(value):
    qr = qrcode.QRCode(
        version=None,
        box_size=8,
        border=2,
    )
    qr.add_data(value)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
