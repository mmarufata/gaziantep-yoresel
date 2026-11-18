import re
from typing import Any

from services.dhl_api import dhl_request
from services.dhl_auth import get_dhl_token
from services.dhl_cbs import resolve_location_codes
from services.dhl_exceptions import DHLShipmentError


def _clean_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("90") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10:
        raise DHLShipmentError(
            "Telefon numarası 10 haneli olmalıdır."
        )
    return digits


def build_reference_id(order_id: int) -> str:
    return f"SIPARIS{order_id}".upper()


def build_piece_list(reference_id: str, *, desi: int, kg: int, piece_count: int = 1) -> list[dict[str, Any]]:
    if desi <= 0 or kg <= 0 or piece_count <= 0:
        raise DHLShipmentError("Desi, kg ve parça sayısı sıfırdan büyük olmalıdır.")
    pieces = []
    for index in range(1, piece_count + 1):
        pieces.append(
            {
                "barcode": f"{reference_id}_PARCA{index}",
                "desi": int(desi),
                "kg": int(kg),
                "content": "Kuruyemiş ve yöresel ürünler",
            }
        )
    return pieces


def build_create_order_payload(
    order,
    *,
    city_code: int,
    district_code: int,
    desi: int,
    kg: int,
    piece_count: int = 1,
    packaging_type: int = 3,
) -> dict[str, Any]:
    reference_id = build_reference_id(order.id)
    return {
        "order": {
            "referenceId": reference_id,
            "barcode": reference_id,
            "billOfLandingId": (order.order_number or reference_id)[:30],
            "isCOD": 0,
            "codAmount": 0,
            "shipmentServiceType": 1,
            "packagingType": int(packaging_type),
            "content": "Kuruyemiş ve yöresel ürünler",
            "smsPreference1": 1,
            "smsPreference2": 1,
            "smsPreference3": 0,
            "paymentType": 1,
            "deliveryType": 1,
            "description": (f"Gaziantep Yöresel siparişi {order.order_number}")[:150],
            "marketPlaceShortCode": "",
            "marketPlaceSaleCode": "",
        },
        "orderPieceList": build_piece_list(
            reference_id, desi=desi, kg=kg, piece_count=piece_count
        ),
        "recipient": {
            "customerId": "",
            "refCustomerId": str(order.id),
            "cityName": order.city.upper(),
            "districtName": order.district.upper(),
            "cityCode": int(city_code),
            "districtCode": int(district_code),
            "address": f"{order.neighborhood}, {order.address}"[:200],
            "bussinessPhoneNumber": "",
            "email": order.email or "",
            "taxOffice": "",
            "taxNumber": "",
            "fullName": order.customer_name[:150],
            "homePhoneNumber": "",
            "mobilePhoneNumber": _clean_phone(order.phone),
        },
    }

def create_recipient(order) -> Any:
    city_code, district_code = resolve_location_codes(
        order.city,
        order.district,
    )

    payload = {
        "recipient": {
            "customerId": "",
            "refCustomerId": str(order.id),
            "cityName": order.city.upper(),
            "districtName": order.district.upper(),
            "cityCode": int(city_code),
            "districtCode": int(district_code),
            "address": f"{order.neighborhood}, {order.address}"[:200],
            "bussinessPhoneNumber": "",
            "email": order.email or "",
            "taxOffice": "",
            "taxNumber": "",
            "fullName": order.customer_name[:150],
            "homePhoneNumber": "",
            "mobilePhoneNumber": _clean_phone(order.phone),
        }
    }

    jwt = get_dhl_token()["jwt"]

    return dhl_request(
        "POST",
        "pluscmdapi/createRecipient",
        jwt=jwt,
        json_body=payload,
    )

def create_order(order, *, desi: int, kg: int, piece_count: int = 1, packaging_type: int = 3) -> Any:
    city_code, district_code = resolve_location_codes(order.city, order.district)
    payload = build_create_order_payload(
        order,
        city_code=city_code,
        district_code=district_code,
        desi=desi,
        kg=kg,
        piece_count=piece_count,
        packaging_type=packaging_type,
    )
    jwt = get_dhl_token()["jwt"]
    return dhl_request(
        "POST",
        "standardcmdapi/createOrder",
        jwt=jwt,
        json_body=payload,
    )


def cancel_order(reference_id: str) -> Any:
    jwt = get_dhl_token()["jwt"]
    return dhl_request(
        "PUT",
        f"standardcmdapi/cancelorder/{reference_id}",
        jwt=jwt,
    )
