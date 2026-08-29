"""
Build the internal Shipment geographic tracking payload.

The map intentionally uses only coordinates explicitly stored on Biobank
records. Free-text sender/recipient addresses are never geocoded here.

A route is therefore classified as:

- mapped: both endpoints have registered coordinates;
- partial: exactly one endpoint has registered coordinates;
- unmapped: neither endpoint has registered coordinates.

The straight geographic segment represents the registered origin-to-
destination transfer relationship. It is not presented as a GPS trace.
"""

from django.urls import reverse


def _string(value):
    if value is None:
        return ""
    return str(value).strip()


def _iso(value):
    if value is None:
        return ""

    method = getattr(
        value,
        "isoformat",
        None,
    )

    if callable(method):
        return method()

    return _string(value)


def _display(instance, method_name, fallback):
    method = getattr(
        instance,
        method_name,
        None,
    )

    if callable(method):
        value = method()

        if value:
            return _string(value)

    return _string(fallback)


def shipment_endpoint_payload(
    biobank,
    *,
    fallback_name="",
    fallback_address="",
):
    """
    Serialize one Shipment endpoint without external geocoding.
    """

    if biobank is not None:
        name = (
            _string(
                getattr(
                    biobank,
                    "name",
                    "",
                )
            )
            or _string(fallback_name)
            or "Unassigned"
        )

        address = (
            _string(
                getattr(
                    biobank,
                    "location_label",
                    "",
                )
            )
            or _string(fallback_address)
        )

        latitude = getattr(
            biobank,
            "latitude",
            None,
        )

        longitude = getattr(
            biobank,
            "longitude",
            None,
        )

        biobank_id = getattr(
            biobank,
            "id",
            None,
        )
    else:
        name = (
            _string(fallback_name)
            or "Unassigned"
        )

        address = _string(
            fallback_address
        )

        latitude = None
        longitude = None
        biobank_id = None

    mapped = (
        latitude is not None
        and longitude is not None
    )

    return {
        "biobank_id": biobank_id,
        "name": name,
        "address": address,
        "latitude": (
            float(latitude)
            if mapped
            else None
        ),
        "longitude": (
            float(longitude)
            if mapped
            else None
        ),
        "mapped": mapped,
    }


def shipment_mapping_status(
    origin,
    destination,
):
    origin_mapped = bool(
        origin.get("mapped")
    )

    destination_mapped = bool(
        destination.get("mapped")
    )

    if (
        origin_mapped
        and destination_mapped
    ):
        return "mapped"

    if (
        origin_mapped
        or destination_mapped
    ):
        return "partial"

    return "unmapped"


def _actor_label(actor):
    if actor is None:
        return "System"

    get_full_name = getattr(
        actor,
        "get_full_name",
        None,
    )

    if callable(get_full_name):
        full_name = _string(
            get_full_name()
        )

        if full_name:
            return full_name

    get_username = getattr(
        actor,
        "get_username",
        None,
    )

    if callable(get_username):
        username = _string(
            get_username()
        )

        if username:
            return username

    return _string(actor) or "System"


def _event_payload(event):
    return {
        "event_type": _string(
            getattr(
                event,
                "event_type",
                "",
            )
        ),
        "label": _display(
            event,
            "get_event_type_display",
            getattr(
                event,
                "event_type",
                "",
            ),
        ),
        "actor": _actor_label(
            getattr(
                event,
                "actor",
                None,
            )
        ),
        "notes": _string(
            getattr(
                event,
                "notes",
                "",
            )
        ),
        "created_at": _iso(
            getattr(
                event,
                "created_at",
                None,
            )
        ),
    }


def _item_payload(item):
    sample = getattr(
        item,
        "sample",
        None,
    )

    sample_id = (
        _string(
            getattr(
                sample,
                "sample_id",
                "",
            )
        )
        or _string(
            getattr(
                item,
                "imported_sample_id",
                "",
            )
        )
        or _string(
            getattr(
                item,
                "material_name",
                "",
            )
        )
        or f"Item {getattr(item, 'id', '')}"
    )

    quantity = getattr(
        item,
        "quantity",
        None,
    )

    return {
        "id": getattr(
            item,
            "id",
            None,
        ),
        "sample_id": sample_id,
        "material_name": _string(
            getattr(
                item,
                "material_name",
                "",
            )
        ),
        "sample_type": _string(
            getattr(
                item,
                "sample_type",
                "",
            )
        ),
        "quantity": (
            _string(quantity)
            if quantity is not None
            else ""
        ),
        "quantity_unit": _string(
            getattr(
                item,
                "quantity_unit",
                "",
            )
        ),
        "container_count": getattr(
            item,
            "container_count",
            None,
        ),
        "container_type": _string(
            getattr(
                item,
                "container_type",
                "",
            )
        ),
        "storage_condition": _string(
            getattr(
                item,
                "storage_condition",
                "",
            )
        ),
    }


def _route_search_text(route):
    parts = [
        route["shipment_code"],
        route["status"]["value"],
        route["status"]["label"],
        route["flow_type"]["value"],
        route["flow_type"]["label"],
        route["carrier_name"],
        route["tracking_code"],
        route["temperature_condition"],
        route["transport_method"],
        route["origin"]["name"],
        route["origin"]["address"],
        route["destination"]["name"],
        route["destination"]["address"],
        route["mapping_status"],
    ]

    for item in route["items"]:
        parts.extend(
            [
                item["sample_id"],
                item["material_name"],
                item["sample_type"],
                item["storage_condition"],
            ]
        )

    return " ".join(
        part
        for part in parts
        if part
    ).lower()


def build_shipment_route_map_context(
    shipments,
):
    """
    Build the dashboard payload exclusively from already-authorized
    Shipment objects supplied by the caller.
    """

    routes = []

    stats = {
        "total": 0,
        "mapped": 0,
        "partial": 0,
        "unmapped": 0,
    }

    for shipment in shipments:
        origin = shipment_endpoint_payload(
            getattr(
                shipment,
                "origin_biobank",
                None,
            ),
            fallback_name=getattr(
                shipment,
                "sender_institution",
                "",
            ),
            fallback_address=getattr(
                shipment,
                "sender_address",
                "",
            ),
        )

        destination = shipment_endpoint_payload(
            getattr(
                shipment,
                "destination_biobank",
                None,
            ),
            fallback_name=getattr(
                shipment,
                "recipient_institution",
                "",
            ),
            fallback_address=getattr(
                shipment,
                "recipient_address",
                "",
            ),
        )

        mapping_status = (
            shipment_mapping_status(
                origin,
                destination,
            )
        )

        items = [
            _item_payload(item)
            for item
            in shipment.items.all()
        ]

        events = [
            _event_payload(event)
            for event
            in shipment.events.all()
        ]

        status_value = _string(
            getattr(
                shipment,
                "status",
                "",
            )
        )

        flow_value = _string(
            getattr(
                shipment,
                "flow_type",
                "",
            )
        )

        route = {
            "id": shipment.id,
            "shipment_code": _string(
                shipment.shipment_code
            ),
            "detail_url": reverse(
                "shipment_detail",
                kwargs={
                    "shipment_id":
                    shipment.id,
                },
            ),
            "status": {
                "value": status_value,
                "label": _display(
                    shipment,
                    "get_status_display",
                    status_value,
                ),
            },
            "flow_type": {
                "value": flow_value,
                "label": _display(
                    shipment,
                    "get_flow_type_display",
                    flow_value,
                ),
            },
            "origin": origin,
            "destination": destination,
            "mapping_status": (
                mapping_status
            ),
            "carrier_name": _string(
                getattr(
                    shipment,
                    "carrier_name",
                    "",
                )
            ),
            "tracking_code": _string(
                getattr(
                    shipment,
                    "tracking_code",
                    "",
                )
            ),
            "transport_method": _string(
                getattr(
                    shipment,
                    "transport_method",
                    "",
                )
            ),
            "temperature_condition": (
                _string(
                    getattr(
                        shipment,
                        "temperature_condition",
                        "",
                    )
                )
            ),
            "dates": {
                "created_at": _iso(
                    getattr(
                        shipment,
                        "created_at",
                        None,
                    )
                ),
                "expected_dispatch_date": (
                    _iso(
                        getattr(
                            shipment,
                            "expected_dispatch_date",
                            None,
                        )
                    )
                ),
                "dispatched_at": _iso(
                    getattr(
                        shipment,
                        "dispatched_at",
                        None,
                    )
                ),
                "expected_arrival_date": (
                    _iso(
                        getattr(
                            shipment,
                            "expected_arrival_date",
                            None,
                        )
                    )
                ),
                "received_at": _iso(
                    getattr(
                        shipment,
                        "received_at",
                        None,
                    )
                ),
            },
            "item_count": len(items),
            "items": items,
            "events": events,
        }

        route["search_text"] = (
            _route_search_text(route)
        )

        routes.append(route)

        stats["total"] += 1
        stats[mapping_status] += 1

    return {
        "shipment_route_map_data": {
            "routes": routes,
            "stats": stats,
        },
        "shipment_route_map_stats": stats,
    }
