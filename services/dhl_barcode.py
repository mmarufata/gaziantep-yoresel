from typing import Any

from services.dhl_api import dhl_request
from services.dhl_auth import get_dhl_token
from services.dhl_shipment import build_piece_list


def create_barcode(
    reference_id: str,
    *,
    bill_of_landing_id: str,
    desi: int,
    kg: int,
    piece_count: int = 1,
    packaging_type: int = 3,
) -> Any:
    payload = {
        "referenceId": reference_id,
        "billOfLandingId": (bill_of_landing_id or "")[:30],
        "isCOD": 0,
        "codAmount": 0,
        "packagingType": int(packaging_type),
        "printReferenceBarcodeOnError": 1,
        "message": "Gaziantep Yöresel",
        "additionalContent1": "",
        "additionalContent2": "",
        "additionalContent3": "",
        "additionalContent4": "",
        "orderPieceList": build_piece_list(
            reference_id, desi=desi, kg=kg, piece_count=piece_count
        ),
    }
    jwt = get_dhl_token()["jwt"]
    return dhl_request(
        "POST",
        "barcodecmdapi/createbarcode",
        jwt=jwt,
        json_body=payload,
    )

def cancel_shipment(reference_id: str, shipment_id: str) -> Any:
    jwt = get_dhl_token()["jwt"]
    return dhl_request(
        "PUT",
        "barcodecmdapi/cancelshipment",
        jwt=jwt,
        json_body={"referenceId": reference_id, "shipmentId": shipment_id},
    )
