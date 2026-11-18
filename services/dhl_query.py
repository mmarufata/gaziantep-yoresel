from typing import Any

from services.dhl_api import dhl_request
from services.dhl_auth import get_dhl_token
from services.dhl_shipment import build_piece_list


def get_order(reference_id: str) -> Any:
    jwt = get_dhl_token()["jwt"]
    return dhl_request("GET", f"standardqueryapi/getorder/{reference_id}", jwt=jwt)


def get_shipment(reference_id: str) -> Any:
    jwt = get_dhl_token()["jwt"]
    return dhl_request("GET", f"standardqueryapi/getshipment/{reference_id}", jwt=jwt)


def get_shipment_status(reference_id: str) -> Any:
    jwt = get_dhl_token()["jwt"]
    return dhl_request(
        "GET", f"standardqueryapi/getshipmentstatus/{reference_id}", jwt=jwt
    )


def track_shipment(reference_id: str) -> list[dict[str, Any]]:
    jwt = get_dhl_token()["jwt"]
    data = dhl_request(
        "GET", f"standardqueryapi/trackshipment/{reference_id}", jwt=jwt
    )
    return data if isinstance(data, list) else []


def calculate_shipping(
    *,
    city_code: int,
    district_code: int,
    address: str,
    reference_id: str,
    desi: int,
    kg: int,
    piece_count: int = 1,
    packaging_type: int = 3,
) -> dict[str, Any]:
    payload = {
        "shipmentServiceType": 1,
        "packagingType": int(packaging_type),
        "paymentType": 1,
        "pickUpType": 1,
        "deliveryType": 1,
        "cityCode": int(city_code),
        "districtCode": int(district_code),
        "address": address,
        "smsPreference1": 1,
        "smsPreference2": 1,
        "smsPreference3": 0,
        "orderPieceList": build_piece_list(
            reference_id, desi=desi, kg=kg, piece_count=piece_count
        ),
    }
    jwt = get_dhl_token()["jwt"]
    return dhl_request(
        "POST",
        "standardqueryapi/calculate",
        jwt=jwt,
        json_body=payload,
    )
