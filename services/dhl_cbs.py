import re
import unicodedata
from functools import lru_cache
from typing import Any

from services.dhl_api import dhl_request
from services.dhl_exceptions import DHLQueryError


def _normalize(value: str) -> str:
    value = (value or "").strip().casefold()
    value = value.replace("ı", "i")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", value)


@lru_cache(maxsize=1)
def get_cities() -> list[dict[str, Any]]:
    data = dhl_request("GET", "cbsinfoapi/getcities")
    if not isinstance(data, list):
        raise DHLQueryError(f"DHL şehir listesi beklenmeyen biçimde: {data}")
    return data


@lru_cache(maxsize=100)
def get_districts(city_code: str) -> list[dict[str, Any]]:
    data = dhl_request("GET", f"cbsinfoapi/getdistricts/{city_code}")
    if not isinstance(data, list):
        raise DHLQueryError(f"DHL ilçe listesi beklenmeyen biçimde: {data}")
    return data


def find_city_code(city_name: str) -> str:
    target = _normalize(city_name)
    for city in get_cities():
        if _normalize(str(city.get("name", ""))) == target:
            return str(city["code"])
    raise DHLQueryError(f"DHL şehir kodu bulunamadı: {city_name}")


def find_district_code(city_code: str, district_name: str) -> str:
    target = _normalize(district_name)
    for district in get_districts(city_code):
        if _normalize(str(district.get("name", ""))) == target:
            return str(district["code"])
    raise DHLQueryError(
        f"DHL ilçe kodu bulunamadı: {district_name} (şehir kodu: {city_code})"
    )

def resolve_location_codes(city_name: str, district_name: str) -> tuple[int, int]:
    return 0, 0