"""PayTR iFrame API yardımcı fonksiyonları."""

from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable
import requests

PAYTR_TOKEN_URL = "https://www.paytr.com/odeme/api/get-token"

def get_paytr_config() -> dict[str, str]:
    """
    .env içerisindeki PayTR ayarlarını döndürür.
    """
    merchant_id = (os.getenv("PAYTR_MERCHANT_ID") or "").strip()
    merchant_key = (os.getenv("PAYTR_MERCHANT_KEY") or "").strip()
    merchant_salt = (os.getenv("PAYTR_MERCHANT_SALT") or "").strip()
    missing = []
    if not merchant_id:
        missing.append("PAYTR_MERCHANT_ID")
    if not merchant_key:
        missing.append("PAYTR_MERCHANT_KEY")
    if not merchant_salt:
        missing.append("PAYTR_MERCHANT_SALT")
    if missing:
        raise RuntimeError("Eksik PayTR ortam değişkenleri: " + ", ".join(missing))
    return {
        "merchant_id": merchant_id,
        "merchant_key": merchant_key,
        "merchant_salt": merchant_salt,
    }

def format_payment_amount(value: object) -> str:
    """
    PayTR payment_amount değerini oluşturur.

    Örnek:
        34.56 TL -> "3456"
        100 TL   -> "10000"
    """
    amount = Decimal(str(value)).quantize( Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise ValueError("Ödeme tutarı sıfırdan büyük olmalıdır.")
    kuruş = (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return str(int(kuruş))

def format_basket_price(value: object) -> str:
    """
    PayTR user_basket içerisindeki ürün fiyatını
    2 ondalıklı string haline getirir.
    """
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount < 0:
        raise ValueError("Sepet ürün fiyatı negatif olamaz.")
    return format(amount, ".2f")

def build_user_basket(items: Iterable, shipping_cost: object = 0) -> str:
    """
    OrderItem kayıtlarından PayTR user_basket oluşturur.
    PayTR formatı:
    [
        ["Ürün 1", "100.00", 2],
        ["Ürün 2", "250.00", 1],
        ["Kargo", "128.00", 1]
    ]
    Çıktı Base64 encoded JSON string'dir.
    """
    basket: list[list[object]] = []
    for item in items:
        product_name = str(getattr(item, "product_name", "") or "" ).strip()
        quantity = int(getattr(item, "quantity", 0) or 0)
        price = getattr(item, "price", 0)
        if not product_name:
            raise ValueError("Sepette ürün adı boş olan bir kayıt bulundu.")
        if quantity <= 0:
            raise ValueError(f"{product_name} için ürün adedi geçersiz.")
        basket.append(
            [
                product_name,
                format_basket_price(price),
                quantity,
            ]
        )
    shipping = Decimal(str(shipping_cost or 0)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
    if shipping > 0:
        basket.append(
            [
                "Kargo",
                format(shipping, ".2f"),
                1,
            ]
        )
    if not basket:
        raise ValueError("PayTR sepeti boş olamaz.")
    basket_json = json.dumps(
        basket,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return base64.b64encode(
        basket_json.encode("utf-8")
    ).decode("ascii")

def create_iframe_token(
    *,
    merchant_id: str,
    merchant_key: str,
    merchant_salt: str,
    user_ip: str,
    merchant_oid: str,
    email: str,
    payment_amount: str,
    user_basket: str,
    no_installment: int = 0,
    max_installment: int = 0,
    currency: str = "TL",
    test_mode: int = 1,
) -> str:
    """
    PayTR iFrame API 1. Adım paytr_token değerini oluşturur.
    """
    merchant_id = str(merchant_id or "").strip()
    merchant_key = str(merchant_key or "").strip()
    merchant_salt = str(merchant_salt or "").strip()
    user_ip = str(user_ip or "").strip()
    merchant_oid = str(merchant_oid or "").strip()
    email = str(email or "").strip()
    payment_amount = str(payment_amount or "").strip()
    user_basket = str(user_basket or "").strip()
    currency = str(currency or "TL").strip()
    no_installment = int(no_installment)
    max_installment = int(max_installment)
    test_mode = int(test_mode)
    if not merchant_id:
        raise ValueError("PayTR merchant_id boş olamaz.")
    if not merchant_key:
        raise ValueError("PayTR merchant_key boş olamaz.")
    if not merchant_salt:
        raise ValueError("PayTR merchant_salt boş olamaz.")
    if not user_ip:
        raise ValueError("PayTR user_ip boş olamaz.")
    if not merchant_oid:
        raise ValueError("PayTR merchant_oid boş olamaz.")
    if len(merchant_oid) > 64:
        raise ValueError("PayTR merchant_oid en fazla 64 karakter olabilir.")
    if not merchant_oid.isalnum():
        raise ValueError("PayTR merchant_oid yalnızca alfanümerik karakter içermelidir.")
    if not email:
        raise ValueError("PayTR email boş olamaz.")
    if not payment_amount:
        raise ValueError("PayTR payment_amount boş olamaz.")
    if not user_basket:
        raise ValueError("PayTR user_basket boş olamaz.")

    hash_str = (
        merchant_id
        + user_ip
        + merchant_oid
        + email
        + payment_amount
        + user_basket
        + str(no_installment)
        + str(max_installment)
        + currency
        + str(test_mode)
    )
    digest = hmac.new(merchant_key.encode("utf-8"), (hash_str + merchant_salt).encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")

def request_iframe_token(
    *,
    user_ip: str,
    merchant_oid: str,
    email: str,
    payment_amount: str,
    user_basket: str,
    user_name: str,
    user_address: str,
    user_phone: str,
    merchant_ok_url: str,
    merchant_fail_url: str,
    no_installment: int = 0,
    max_installment: int = 0,
    currency: str = "TL",
    test_mode: int = 1,
    debug_on: int = 1,
    timeout_limit: int = 30,
    lang: str = "tr",
    request_timeout: int = 20,
) -> str:
    """
    PayTR'a server-side POST gönderir ve iframe token döndürür.
    """
    config = get_paytr_config()
    merchant_id = config["merchant_id"]
    merchant_key = config["merchant_key"]
    merchant_salt = config["merchant_salt"]
    paytr_token = create_iframe_token(
        merchant_id=merchant_id,
        merchant_key=merchant_key,
        merchant_salt=merchant_salt,
        user_ip=user_ip,
        merchant_oid=merchant_oid,
        email=email,
        payment_amount=payment_amount,
        user_basket=user_basket,
        no_installment=no_installment,
        max_installment=max_installment,
        currency=currency,
        test_mode=test_mode,
    )
    post_data = {
        "merchant_id": merchant_id,
        "user_ip": user_ip,
        "merchant_oid": merchant_oid,
        "email": email,
        "payment_amount": payment_amount,
        "paytr_token": paytr_token,
        "user_basket": user_basket,
        "debug_on": str(int(debug_on)),
        "no_installment": str(int(no_installment)),
        "max_installment": str(int(max_installment)),
        "user_name": str(user_name or "").strip(),
        "user_address": str(user_address or "").strip(),
        "user_phone": str(user_phone or "").strip(),
        "merchant_ok_url": merchant_ok_url,
        "merchant_fail_url": merchant_fail_url,
        "timeout_limit": str(int(timeout_limit)),
        "currency": currency,
        "test_mode": str(int(test_mode)),
        "lang": lang,
    }
    try:
        response = requests.post(PAYTR_TOKEN_URL, data=post_data, timeout=request_timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"PayTR bağlantı hatası: {exc}") from exc
    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError("PayTR geçerli bir JSON yanıtı döndürmedi.") from exc
    if result.get("status") != "success":
        reason = result.get("reason", "PayTR tarafından bilinmeyen hata döndürüldü.")
        raise RuntimeError(f"PayTR iframe token alınamadı: {reason}")
    iframe_token = str(result.get("token") or "").strip()
    if not iframe_token:
        raise RuntimeError("PayTR başarılı yanıt verdi ancak iframe token boş.")
    return iframe_token

def create_callback_hash(
    *,
    merchant_oid: str,
    status: str,
    total_amount: str,
    merchant_key: str,
    merchant_salt: str,
) -> str:
    """
    PayTR iFrame API 2. Adım Bildirim URL hash'ini oluşturur.
    Sıra:
        merchant_oid + merchant_salt + status + total_amount
    """
    plain_text = (
        str(merchant_oid or "")
        + str(merchant_salt or "")
        + str(status or "")
        + str(total_amount or "")
    )
    digest = hmac.new(merchant_key.encode("utf-8"), plain_text.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")

def verify_callback_hash(
    *,
    merchant_oid: str,
    status: str,
    total_amount: str,
    received_hash: str,
) -> bool:
    """
    PayTR Bildirim URL'sinden gelen hash'i doğrular.
    """
    config = get_paytr_config()
    calculated_hash = create_callback_hash(
        merchant_oid=merchant_oid,
        status=status,
        total_amount=total_amount,
        merchant_key=config["merchant_key"],
        merchant_salt=config["merchant_salt"],
    )
    return hmac.compare_digest(calculated_hash, str(received_hash or "").strip())