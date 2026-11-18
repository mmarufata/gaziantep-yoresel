from typing import Any

import requests

from services.dhl_api import build_headers, get_dhl_config
from services.dhl_exceptions import DHLAuthError


def get_dhl_token() -> dict[str, Any]:
    config = get_dhl_config(require_customer_password=True)
    payload = {
        "customerNumber": config["customer_number"],
        "password": config["customer_password"],
        "identityType": 1,
    }

    try:
        response = requests.post(
            f'{config["base_url"]}/token',
            headers=build_headers(),
            json=payload,
            timeout=config["timeout"],
        )
    except requests.Timeout as exc:
        raise DHLAuthError("DHL Identity API zaman aşımına uğradı.") from exc
    except requests.RequestException as exc:
        raise DHLAuthError(f"DHL Identity API bağlantı hatası: {exc}") from exc

    try:
        data = response.json()
    except ValueError:
        data = {"raw_response": response.text}

    if response.status_code != 200:
        raise DHLAuthError(
            f"DHL token alınamadı. HTTP {response.status_code}: {data}"
        )
    if not data.get("jwt"):
        raise DHLAuthError("DHL yanıtında jwt alanı bulunamadı.")
    return data
