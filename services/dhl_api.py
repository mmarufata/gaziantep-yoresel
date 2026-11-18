import os
from typing import Any

import requests

from services.dhl_exceptions import DHLAPIError, DHLConfigurationError


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise DHLConfigurationError(f"{name} ortam değişkeni tanımlı değil.")
    return value


def get_dhl_config(require_customer_password: bool = True) -> dict[str, Any]:
    try:
        timeout = int(os.getenv("DHL_TIMEOUT_SECONDS", "20"))
    except ValueError as exc:
        raise DHLConfigurationError(
            "DHL_TIMEOUT_SECONDS bir tam sayı olmalıdır."
        ) from exc

    config: dict[str, Any] = {
        "base_url": os.getenv(
            "DHL_BASE_URL",
            "https://testapi.mngkargo.com.tr/mngapi/api",
        ).rstrip("/"),
        "client_id": _required_env("DHL_CLIENT_ID"),
        "client_secret": _required_env("DHL_CLIENT_SECRET"),
        "customer_number": _required_env("DHL_CUSTOMER_NUMBER"),
        "api_version": os.getenv("DHL_API_VERSION", "").strip(),
        "timeout": timeout,
    }
    if require_customer_password:
        config["customer_password"] = _required_env("DHL_CUSTOMER_PASSWORD")
    else:
        config["customer_password"] = os.getenv("DHL_CUSTOMER_PASSWORD", "").strip()
    return config


def build_headers(*, jwt: str | None = None) -> dict[str, str]:
    config = get_dhl_config(require_customer_password=False)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-IBM-Client-Id": config["client_id"],
        "X-IBM-Client-Secret": config["client_secret"],
    }
    if config["api_version"]:
        headers["x-api-version"] = config["api_version"]
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    return headers


def parse_response(response: requests.Response) -> Any:
    try:
        data: Any = response.json()
    except ValueError:
        data = {"raw_response": response.text}

    if response.ok:
        return data

    error = DHLAPIError(
        f"DHL API isteği başarısız. HTTP {response.status_code}: {data}"
    )
    error.status_code = response.status_code
    error.response_data = data
    raise error


def dhl_request(
    method: str,
    path: str,
    *,
    jwt: str | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    config = get_dhl_config(require_customer_password=False)
    url = f'{config["base_url"]}/{path.lstrip("/")}'
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=build_headers(jwt=jwt),
            json=json_body,
            timeout=config["timeout"],
        )
    except requests.Timeout as exc:
        raise DHLAPIError("DHL API isteği zaman aşımına uğradı.") from exc
    except requests.RequestException as exc:
        raise DHLAPIError(f"DHL API bağlantı hatası: {exc}") from exc
    return parse_response(response)
