import os
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from email.mime.text import MIMEText
import smtplib
import requests
import uuid
from services.dhl_shipment import (build_reference_id, create_recipient, create_order as create_dhl_order)
from services.dhl_barcode import (create_barcode, cancel_shipment)
from services.dhl_query import get_order, get_shipment_status
#from services.dhl_query import get_shipment_status
from services.dhl_exceptions import DHLAPIError, DHLShipmentError
from services.paytr_payment import (build_user_basket, format_payment_amount, request_iframe_token, verify_callback_hash)
import secrets
from urllib.parse import urlparse
import re 
from urllib.parse import quote
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Yeni sipariş oluştuğunda bilgilendirme e-postasının gönderileceği adres.
# .env dosyasında ADMIN_NOTIFICATION_EMAIL tanımlanırsa onu kullanır, yoksa
# aşağıdaki varsayılan adrese gönderir.
ADMIN_NOTIFICATION_EMAIL = os.getenv("ADMIN_NOTIFICATION_EMAIL", "meksemes612@gmail.com").strip()

_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
_DB_PATH = os.path.join(_BASE_DIR, "instance", "gaziantep.db")
os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + _DB_PATH.replace("\\", "/")
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60)

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
required_env_vars = {
    "SECRET_KEY": app.config["SECRET_KEY"],
    "ADMIN_USERNAME": ADMIN_USERNAME,
    "ADMIN_PASSWORD": ADMIN_PASSWORD,
}
missing_env_vars = [
    name
    for name, value in required_env_vars.items()
    if not value
]
if missing_env_vars:
    raise RuntimeError(
        "Eksik ortam değişkenleri: "
        + ", ".join(missing_env_vars)
    )
SITE_NAME = os.getenv("SITE_NAME", "Gaziantep Yöresel Ürünler")
SITE_URL = os.getenv("SITE_URL", "").rstrip("/")
DEFAULT_SEO_DESCRIPTION = os.getenv(
    "SITE_DESCRIPTION",
    "Gaziantep yöresel ürünleri online satış: Antep fıstığı, pestil, köy peyniri ve daha fazlası. "
    "Doğal lezzetler, güvenli alışveriş ve hızlı kargo.",
)
DEFAULT_SEO_KEYWORDS = os.getenv(
    "SITE_KEYWORDS",
    "Gaziantep yöresel ürünler, Antep fıstığı, yöresel gıda, Gaziantep lezzetleri, online alışveriş, "
    "pestil, köy peyniri, doğal ürünler",
)
DEFAULT_GRAJ_OPTIONS = "100,500,1000"
GRAMAJ_CHOICES = [
    (100, "100 Gr"),
    (250, "250 Gr"),
    (500, "500 Gr"),
    (1000, "1 Kg"),
    (2000, "2 Kg"),
    (5000, "5 Kg"),
]
VALID_GRAJ_VALUES = {value for value, _ in GRAMAJ_CHOICES}

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50))
    image = db.Column(db.String(200))
    image2 = db.Column(db.String(200))
    video = db.Column(db.String(200))
    description = db.Column(db.Text)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    gramaj_options = db.Column(db.String(100))
    comments = db.relationship('Comment', backref='product', lazy=True, cascade='all, delete-orphan')
    @property
    def gramaj_list(self):
        if self.unit != "Kg":
            return []
        return _parse_gramaj_options(self.gramaj_options)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    author_name = db.Column(db.String(80), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120))
    notify_sms = db.Column(db.Boolean, default=True)
    notify_email = db.Column(db.Boolean, default=True)
    city = db.Column(db.String(100), nullable=False)
    district = db.Column(db.String(100), nullable=False)
    neighborhood = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text, nullable=False)
    note = db.Column(db.Text)
    status = db.Column(db.String(50), default="Ödeme Bekleniyor")
    payment_status = db.Column(db.String(50), default="Beklemede")
    total_amount = db.Column(db.Float, nullable=False)
    shipping_cost = db.Column(db.Float, default=0.0)
    transaction_id = db.Column(db.String(100))
    cargo_company = db.Column(db.String(100))
    cargo_tracking_no = db.Column(db.String(100))
    cargo_tracking_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")
    public_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    admin_hidden = db.Column(db.Boolean, nullable=False, default=False)

    @property
    def total(self):
        return sum(item.price * item.quantity for item in self.items) + (self.shipping_cost or 0.0)

class Payment(db.Model):
    __tablename__ = "payment"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False, index=True)
    provider = db.Column(db.String(30), nullable=False, default="PAYTR")
    payment_order_id = db.Column(db.String(36), nullable=False, unique=True, index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency_code = db.Column(db.String(3), nullable=False, default="949")
    status = db.Column(db.String(30), nullable=False, default="CREATED")
    response_code = db.Column(db.String(20))
    host_response_code = db.Column(db.String(20))
    response_message = db.Column(db.Text)
    auth_code = db.Column(db.String(50))
    rrn = db.Column(db.String(50))
    transaction_id = db.Column(db.String(100))
    hash_verified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = db.relationship(
        "Order",
        backref=db.backref("payments", lazy=True, cascade="all, delete-orphan"),
    )

class Shipment(db.Model):
    __tablename__ = "shipment"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("order.id"),
        nullable=False,
        unique=True,
    )
    reference_id = db.Column(
        db.String(30),
        unique=True,
        nullable=False,
    )
    piece_barcode = db.Column(db.String(30))
    shipment_id = db.Column(db.String(50))
    order_invoice_id = db.Column(db.String(50))
    order_invoice_detail_id = db.Column(db.String(50))
    shipper_branch_code = db.Column(db.String(20))
    kg = db.Column(db.Integer)
    desi = db.Column(db.Integer)
    piece_count = db.Column(db.Integer,default=1)
    packaging_type = db.Column(db.Integer, default=3)
    zpl_label = db.Column(db.Text)
    status = db.Column(db.String(30))
    last_error = db.Column(db.Text)
    recipient_created = db.Column(db.Boolean, default=False)
    order_created = db.Column(db.Boolean, default=False)
    barcode_created = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    order = db.relationship("Order", backref=db.backref("shipment", uselist=False, cascade="all, delete-orphan"))

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_name = db.Column(db.String(150), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50))

class NotificationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    event_type = db.Column(db.String(50), nullable=False) 
    channel = db.Column(db.String(20), nullable=False)  
    status = db.Column(db.String(20), nullable=False) 
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship("Order", backref="notifications")

def _truncate_text(text, max_length=160):
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_length:
        return cleaned
    shortened = cleaned[: max_length - 3].rsplit(" ", 1)[0]
    return f"{shortened}..."

def _absolute_url(endpoint, **values):
    path = url_for(endpoint, **values)
    if SITE_URL:
        return f"{SITE_URL}{path}"
    return url_for(endpoint, _external=True, **values)

def _absolute_asset_url(asset_path):
    default_image = url_for("static", filename="web_pic.png")
    path = asset_path or default_image
    if path.startswith(("http://", "https://")):
        return path
    path = quote(path, safe="/%")
    if SITE_URL:
        return f"{SITE_URL}{path}"
    if path.startswith("/static/"):
        return url_for("static", filename=path.removeprefix("/static/"), _external=True)
    return url_for("static", filename="web_pic.png", _external=True)

def _product_seo_description(product):
    if product.description:
        return _truncate_text(product.description)
    return (
        f"{product.name} - {product.category}. "
        "Gaziantep yöresel ürünlerini güvenle online sipariş edin."
    )

def _product_json_ld(product):
    return {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "description": _product_seo_description(product),
        "image": _absolute_asset_url(product.image),
        "category": product.category,
        "brand": {
            "@type": "Brand",
            "name": SITE_NAME,
        },
        "offers": {
            "@type": "Offer",
            "priceCurrency": "TRY",
            "price": f"{product.price:.2f}",
            "availability": "https://schema.org/InStock",
            "url": _absolute_url("product_detail", id=product.id),
        },
    }

def _website_json_ld():
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": _absolute_url("home"),
        "description": DEFAULT_SEO_DESCRIPTION,
        "inLanguage": "tr-TR",
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{_absolute_url('product')}?q={{search_term_string}}",
            "query-input": "required name=search_term_string",
        },
    }

@app.context_processor
def inject_seo_defaults():
    def canonical_for(path=None):
        target_path = path or request.path
        if SITE_URL:
            return f"{SITE_URL}{target_path}"
        return request.base_url
    return {
        "site_name": SITE_NAME,
        "site_url": SITE_URL,
        "default_seo_description": DEFAULT_SEO_DESCRIPTION,
        "default_seo_keywords": DEFAULT_SEO_KEYWORDS,
        "default_seo_image": _absolute_asset_url(None),
        "canonical_for": canonical_for,
        "gramaj_choices": GRAMAJ_CHOICES,
        "format_gramaj": _format_gramaj_label,
    }

def _format_gramaj_label(grams):
    if grams >= 1000 and grams % 1000 == 0:
        kg = grams // 1000
        return f"{kg} Kg"
    return f"{grams} Gr"

def _parse_gramaj_options(value):
    if not value:
        return [int(v) for v in DEFAULT_GRAJ_OPTIONS.split(",")]
    parsed = []
    for part in str(value).split(","):
        part = part.strip()
        if part.isdigit():
            grams = int(part)
            if grams in VALID_GRAJ_VALUES:
                parsed.append(grams)
    return sorted(set(parsed)) if parsed else [int(v) for v in DEFAULT_GRAJ_OPTIONS.split(",")]

def _gramaj_options_from_form():
    selected = request.form.getlist("gramaj_options")
    parsed = sorted(
        int(value)
        for value in selected
        if value.isdigit() and int(value) in VALID_GRAJ_VALUES
    )
    return ",".join(str(value) for value in parsed) if parsed else None

def _apply_product_gramaj_options(product, unit):
    if unit == "Kg":
        stored = _gramaj_options_from_form()
        if not stored:
            return False
        product.gramaj_options = stored
    else:
        product.gramaj_options = None
    return True

def _get_cart():
    if 'cart' not in session:
        session['cart'] = {}
    return session['cart']

def _save_cart(cart):
    session['cart'] = cart
    session.modified = True

def _clear_cart():
    session['cart'] = {}
    session.modified = True

def _generate_order_number():
    """Benzersiz sipariş numarası üretir: GAZ-YYYYMMDD-XXXX"""
    from datetime import datetime
    import random
    date_str = datetime.now().strftime("%Y%m%d")
    random_str = str(random.randint(1000, 9999))
    return f"GAZ-{date_str}-{random_str}"

def _calculate_shipping_cost(subtotal, city=None, total_weight=0):
    """
    Kargo ücreti hesaplama
    2000 TL ve üzeri -> Ücretsiz
    2000 TL altı -> 128 TL
    """
    if subtotal >= 2000:
        return 0.0
    return 128.0

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}

def _send_email(to_email: str, subject: str, body: str) -> bool:
    smtp_enabled = _env_bool("SMTP_ENABLED", True)
    if not smtp_enabled:
        app.logger.info(
            "SMTP gönderimi kapalı. Alıcı=%s, konu=%s",
            to_email,
            subject,
        )
        return False
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port_text = os.getenv("SMTP_PORT", "587").strip()
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_use_ssl = _env_bool("SMTP_USE_SSL", False)
    smtp_use_tls = _env_bool("SMTP_USE_TLS", not smtp_use_ssl)
    if not to_email or "@" not in to_email:
        app.logger.warning("Geçersiz e-posta alıcısı: %r", to_email)
        return False
    if not smtp_host or not smtp_user or not smtp_pass:
        app.logger.warning("SMTP yapılandırması eksik. " "SMTP_HOST, SMTP_USER ve SMTP_PASS kontrol edilmeli.")
        return False
    if smtp_use_ssl and smtp_use_tls:
        app.logger.error("SMTP_USE_SSL ve SMTP_USE_TLS aynı anda true olamaz.")
        return False
    try:
        smtp_port = int(smtp_port_text)
    except ValueError:
        app.logger.error( "SMTP_PORT geçerli bir sayı değil: %r", smtp_port_text)
        return False
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = smtp_user
    message["To"] = to_email
    try:
        if smtp_use_ssl:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(message)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                if smtp_use_tls:
                    server.starttls()
                    server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(message)
        app.logger.info("E-posta başarıyla gönderildi. Alıcı=%s, konu=%s", to_email, subject)
        return True
    except smtplib.SMTPAuthenticationError:
        app.logger.exception("SMTP kimlik doğrulaması başarısız. " "Kullanıcı adı ve posta kutusu şifresini kontrol et.")
        return False
    except (smtplib.SMTPException, OSError):
        app.logger.exception("E-posta gönderilemedi. " "SMTP sunucusu, port ve SSL/TLS ayarlarını kontrol et.")
        return False

def _normalize_sms_phone(phone: str) -> str:
    """Türkiye cep telefonunu Netgsm'nin beklediği 10 haneli biçime getirir."""
    digits = "".join(char for char in str(phone) if char.isdigit())

    if digits.startswith("0090"):
        digits = digits[4:]
    elif digits.startswith("90") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if len(digits) != 10 or not digits.startswith("5"):
        raise ValueError("Telefon numarası 5XXXXXXXXX biçiminde olmalıdır.")

    return digits

def _send_sms(to_phone: str, message: str) -> bool:
    try:
        api_url = os.getenv(
            "NETGSM_API_URL",
            "https://api.netgsm.com.tr/sms/rest/v2/send",
        )
        username = os.getenv("NETGSM_USERNAME")
        password = os.getenv("NETGSM_PASSWORD")
        msgheader = os.getenv("NETGSM_MSGHEADER")
        if not all([username, password, msgheader]):
            app.logger.error(
                "Netgsm yapılandırması eksik: "
                "NETGSM_USERNAME, NETGSM_PASSWORD veya NETGSM_MSGHEADER."
            )
            return False
        normalized_phone = _normalize_sms_phone(to_phone)
        cleaned_message = " ".join(str(message).split())
        payload = {
            "msgheader": msgheader,
            "messages": [{"msg": cleaned_message, "no": normalized_phone}],
            "encoding": "TR",
            "iysfilter": "0",
            "appname": "GaziantepYoresel",
        }
        response = requests.post(
            api_url,
            json=payload,
            auth=(username, password),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        try:
            response_data = response.json()
        except ValueError:
            app.logger.error("Netgsm JSON olmayan cevap döndürdü. HTTP=%s, cevap=%s", response.status_code, response.text[:500])
            return False
        response_code = str(response_data.get("code", "")).strip()
        job_id = response_data.get("jobid")
        description = response_data.get("description")
        if response_code != "00":
            app.logger.error("Netgsm SMS reddedildi. code=%s, description=%s, cevap=%s", response_code, description, response_data)
            return False
        app.logger.info("Netgsm SMS kuyruğa alındı. telefon=%s, jobid=%s", normalized_phone, job_id)
        return True
    except ValueError as exc:
        app.logger.warning("Geçersiz SMS telefon numarası: %s", exc)
        return False
    except requests.Timeout:
        app.logger.exception("Netgsm SMS isteği zaman aşımına uğradı.")
        return False
    except requests.RequestException:
        app.logger.exception("Netgsm SMS isteğinde bağlantı/HTTP hatası oluştu.")
        return False
    except Exception:
        app.logger.exception("Beklenmeyen SMS gönderim hatası oluştu.")
        return False

def _notification_already_sent(order_id: int, event_type: str, channel: str) -> bool:
    return NotificationLog.query.filter_by(
        order_id=order_id,
        event_type=event_type,
        channel=channel,
        status="success",
    ).first() is not None

def _order_products(query):
    """Küçük display_order değeri listede üstte görünür."""
    return query.order_by(Product.display_order.asc(), Product.id.asc())

def _featured_products_ordered():
    """Ana sayfa: belirlenen 6 ürün (display_order'dan bağımsız)."""
    # def first(q):
    #     return q.order_by(Product.id).first()
    def by_exact(name: str):
        return Product.query.filter(Product.name == name).order_by(Product.id).first()
    candidates = [
        by_exact("Tuzlu Antep Fıstığı "),
        by_exact("İpek Biber (acı)"),
        by_exact("Acı Biber Salçası"),
        by_exact("Patlıcan Kurusu (50 adet)"),
        by_exact("Pekmezli Kelebek Sucuk"),
        by_exact("Atom Karışık"),
    ]
    seen = set()
    out = []
    for p in candidates:
        if p is not None and p.id not in seen:
            seen.add(p.id)
            out.append(p)
    return out

def _parse_display_order(value, fallback: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback

def _next_display_order() -> int:
    current_max = db.session.query(db.func.max(Product.display_order)).scalar()
    return (current_max or 0) + 10

def _log_notification(order_id: int, event_type: str, channel: str, success: bool, error: str | None = None):
    log = NotificationLog(
        order_id=order_id,
        event_type=event_type,
        channel=channel,
        status="success" if success else "fail",
        error_message=error,
    )
    db.session.add(log)
    db.session.commit()

def _build_payment_received_messages(order: Order):
    subject = f"Gaziantep Yöresel - Siparişiniz Alındı ({order.order_number})"
    body = (
        f"Merhaba {order.customer_name},\n\n"
        f"{order.order_number} numaralı siparişiniz için ödemeniz başarıyla alınmıştır.\n"
        f"Sipariş durumunuz: Ödeme Alındı / Hazırlanıyor.\n\n"
        f"Teşekkür ederiz.\n"
    )
    sms_text = (
        f"{order.order_number} nolu siparişiniz için ödemeniz alındı. "
        f"Teşekkürler - Gaziantep Yöresel"
    )
    return subject, body, sms_text

def _build_shipped_messages(order: Order, cargo_name: str, tracking_no: str, tracking_url: str | None = None):
    base_text = (
        f"Merhaba {order.customer_name},\n\n"
        f"{order.order_number} numaralı siparişiniz kargoya verilmiştir.\n"
        f"Kargo firması: {cargo_name}\n"
        f"Takip numarası: {tracking_no}\n"
    )
    if tracking_url:
        base_text += f"Kargo takip linki: {tracking_url}\n"
    base_text += (
        "\nDağıtım ve teslimat bildirimleri kargo firması tarafından yapılacaktır.\n\n"
        "Teşekkür ederiz.\n"
    )
    subject = f"Gaziantep Yöresel - Siparişiniz Kargoya Verildi ({order.order_number})"
    email_body = base_text
    sms_text = (
        f"{order.order_number} nolu siparişiniz kargoya verildi. "
        f"Kargo: {cargo_name}, Takip No: {tracking_no}. "
        f"Dağıtım ve teslimat bildirimleri kargo firması tarafından yapılacaktır."
    )
    return subject, email_body, sms_text

def notify_payment_received(order: Order):
    event_type = "payment_received"
    if order.notify_email and order.email:
        channel = "email"
        if not _notification_already_sent(order.id, event_type, channel):
            subject, body, _ = _build_payment_received_messages(order)
            ok = _send_email(order.email, subject, body)
            _log_notification(order.id, event_type, channel, ok)
    if order.notify_sms and order.phone:
        channel = "sms"
        if not _notification_already_sent(order.id, event_type, channel):
            _, _, sms_text = _build_payment_received_messages(order)
            ok = _send_sms(order.phone, sms_text)
            _log_notification(order.id, event_type, channel, ok)

def notify_shipped(order: Order):
    if not order.cargo_company or not order.cargo_tracking_no:
        return
    shipment = order.shipment
    if shipment and shipment.shipment_id:
        order.cargo_company = "DHL eCommerce"
        order.cargo_tracking_no = shipment.shipment_id
        order.cargo_tracking_url = os.getenv("DHL_TRACKING_URL", "https://www.dhlecommerce.com.tr/gonderitakip")
    event_type = "shipped"
    subject, email_body, sms_text = _build_shipped_messages(
        order,
        cargo_name=order.cargo_company,
        tracking_no=order.cargo_tracking_no,
        tracking_url=order.cargo_tracking_url,
    )
    if order.notify_email and order.email:
        channel = "email"
        if not _notification_already_sent(order.id, event_type, channel):
            ok = _send_email(order.email, subject, email_body)
            _log_notification(order.id, event_type, channel, ok)
    if order.notify_sms and order.phone:
        channel = "sms"
        if not _notification_already_sent(order.id, event_type, channel):
            ok = _send_sms(order.phone, sms_text)
            _log_notification(order.id, event_type, channel, ok)

def _build_admin_new_order_message(order: Order):
    lines = [
        f"Ödemesi tamamlanan yeni bir sipariş var: {order.order_number}",
        "",
        f"Müşteri: {order.customer_name}",
        f"Telefon: {order.phone}",
        f"E-posta: {order.email or '-'}",
        f"Adres: {order.neighborhood}, {order.district}/{order.city}",
        f"Adres Detayı: {order.address}",
    ]
    if order.note:
        lines.append(f"Sipariş Notu: {order.note}")
    lines.append("")
    lines.append("Ürünler:")
    for item in order.items:
        unit = f" {item.unit}" if item.unit else ""
        lines.append(f"  - {item.product_name} x{item.quantity}{unit} - {item.price * item.quantity:.2f} TL")
    lines.append("")
    lines.append(f"Kargo Ücreti: {order.shipping_cost:.2f} TL")
    lines.append(f"Toplam Tutar: {order.total_amount:.2f} TL")
    lines.append(f"Sipariş Durumu: {order.status}")
    lines.append(f"Ödeme Durumu: {order.payment_status}")
    subject = f"Yeni Sipariş (Ödeme Alındı) - {order.order_number}"
    body = "\n".join(lines)
    return subject, body

def notify_admin_new_order(order: Order):
    event_type = "new_order_admin"
    channel = "email"
    if not ADMIN_NOTIFICATION_EMAIL:
        return
    if _notification_already_sent(order.id, event_type, channel):
        return
    subject, body = _build_admin_new_order_message(order)
    ok = _send_email(ADMIN_NOTIFICATION_EMAIL, subject, body)
    _log_notification(order.id, event_type, channel, ok)

@app.route('/robots.txt')
def robots_txt():
    sitemap_url = _absolute_url("sitemap_xml")
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /cart",
        "Disallow: /checkout",
        "Disallow: /payment/",
        "Disallow: /order-success/",
        "Disallow: /create-order",
        "",
        f"Sitemap: {sitemap_url}",
    ]
    return Response("\n".join(lines), mimetype="text/plain")

@app.route('/google-merchant.xml')
def google_merchant_feed():
    """Google Merchant Center için RSS 2.0 XML ürün veri kaynağı."""
    products = Product.query.order_by(Product.id.asc()).all()
    response = Response(
        render_template(
            "google_merchant.xml",
            products=products,
            generated_at=datetime.utcnow(),
            merchant_title=SITE_NAME,
            merchant_link=_absolute_url("home"),
            merchant_description=DEFAULT_SEO_DESCRIPTION,
            product_url=lambda product: _absolute_url("product_detail", id=product.id),
            product_image_url=lambda product: _absolute_asset_url(product.image),
            product_description=_product_seo_description,
        ),
        mimetype="application/xml",
    )
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.route('/sitemap.xml')
def sitemap_xml():
    urls = [
        {"loc": _absolute_url("home"), "changefreq": "daily", "priority": "1.0"},
        {"loc": _absolute_url("product"), "changefreq": "daily", "priority": "0.9"},
        {"loc": _absolute_url("about"), "changefreq": "monthly", "priority": "0.7"},
        {"loc": _absolute_url("contact"), "changefreq": "monthly", "priority": "0.7"},
        {"loc": _absolute_url("mesafeli_satis"), "changefreq": "yearly", "priority": "0.3"},
        {"loc": _absolute_url("on_bilgilendirme"), "changefreq": "yearly", "priority": "0.3"},
        {"loc": _absolute_url("gizlilik_politikasi"), "changefreq": "yearly", "priority": "0.3"},
        {"loc": _absolute_url("cerez_politikasi"), "changefreq": "yearly", "priority": "0.3"},
        {"loc": _absolute_url("kullanim_kosullari"), "changefreq": "yearly", "priority": "0.3"},
        {"loc": _absolute_url("kvkk_aydinlatma"), "changefreq": "yearly", "priority": "0.3"},
    ]
    for product in Product.query.order_by(Product.id.asc()).all():
        urls.append(
            {
                "loc": _absolute_url("product_detail", id=product.id),
                "changefreq": "weekly",
                "priority": "0.8",
            }
        )
    return Response(
        render_template("sitemap.xml", urls=urls),
        mimetype="application/xml",
    )

@app.route('/')
def home():
    featured_products = _featured_products_ordered()
    return render_template(
        "anasayfa.html",
        featured_products=featured_products,
        seo_title=f"{SITE_NAME} | Gaziantep Yöresel Ürünler Online Satış",
        seo_description=DEFAULT_SEO_DESCRIPTION,
        seo_json_ld=[_website_json_ld()],
    )

@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            session.permanent = True
            flash("Hoş geldiniz, yönetici!", "success")
            return redirect(url_for('admin_panel'))
        else:
            flash("Hatalı kullanıcı adı veya şifre!", "danger")
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash("Çıkış yapıldı.", "info")
    return redirect(url_for('admin_login'))
    
@app.route('/admin/panel')
def admin_panel():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    return render_template('admin_panel.html')

@app.route('/admin/manage_products')
def manage_products():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    products = _order_products(Product.query).all()
    return render_template('manage_products.html', products=products)

#test için eklendi silinecek 
@app.post("/admin/test-email")
@limiter.limit("5 per hour")
def admin_test_email():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    recipient = os.getenv("SMTP_USER", "").strip()
    if not recipient:
        flash(
            "SMTP_USER ortam değişkeni tanımlanmamış.","danger")
        return redirect(url_for("admin_panel"))
    subject = "Gaziantep Yöresel E-posta Testi"
    body = (
        "Merhaba,\n\n"
        "Gaziantep Yöresel e-posta entegrasyonu başarıyla çalışıyor.\n\n"
        f"Test zamanı: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        "Gaziantep Yöresel"
    )
    if _send_email(recipient, subject, body):
        flash(f"Test e-postası {recipient} adresine gönderildi.", "success")
    else:
        flash("Test e-postası gönderilemedi. Sunucu loglarını kontrol edin.", "danger")

    return redirect(url_for("admin_panel"))
#silinecek 

@app.route('/admin/add_product', methods=['GET', 'POST'])
def add_product():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))   
    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category')
        price = float(request.form.get('price'))
        unit = request.form.get('unit', '')
        image = request.form.get('image', '/static/images/placeholder.png')
        image2 = request.form.get('image2', '').strip()
        video = request.form.get('video', '').strip()
        description = request.form.get('description', '').strip()
        raw_order = request.form.get('display_order', '').strip()
        display_order = (
            _parse_display_order(raw_order, _next_display_order())
            if raw_order
            else _next_display_order()
        )
        if name and category and price:
            new_product = Product(
                name=name,
                category=category,
                price=price,
                unit=unit,
                image=image,
                image2=image2 or None,
                video=video or None,
                description=description or None,
                display_order=display_order,
            )
            if not _apply_product_gramaj_options(new_product, unit):
                flash("Kg birimli ürünler için en az bir gramaj seçeneği işaretleyin.", "danger")
                return render_template('add_product.html')
            db.session.add(new_product)
            db.session.commit()
            flash("Ürün başarıyla eklendi!", "success")
            return redirect(url_for('manage_products'))
        else:
            flash("Lütfen tüm gerekli alanları doldurun!", "danger")  
    return render_template('add_product.html')

@app.route('/admin/products/edit/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))   
    product = Product.query.get_or_404(id)  
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.category = request.form.get('category')
        product.price = float(request.form.get('price'))
        product.unit = request.form.get('unit', '')
        product.image = request.form.get('image', product.image)
        image2 = request.form.get('image2', '').strip()
        product.image2 = image2 or None
        video = request.form.get('video', '').strip()
        product.video = video or None
        description = request.form.get('description', '').strip()
        product.description = description or None
        product.display_order = _parse_display_order(
            request.form.get('display_order'),
            product.display_order,
        )
        unit = product.unit
        if not _apply_product_gramaj_options(product, unit):
            flash("Kg birimli ürünler için en az bir gramaj seçeneği işaretleyin.", "danger")
            return render_template('edit_product.html', product=product)
        db.session.commit()
        flash("Ürün başarıyla güncellendi!", "success")
        return redirect(url_for('manage_products'))  
    return render_template('edit_product.html', product=product)

@app.route('/admin/products/delete/<int:id>')
def delete_product(id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))  
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash("Ürün başarıyla silindi!", "success")
    return redirect(url_for('manage_products'))

@app.route('/admin/products/<int:product_id>/comments')
def product_comments(product_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    product = Product.query.get_or_404(product_id)
    comments = (
        Comment.query.filter_by(product_id=product_id)
        .order_by(Comment.created_at.desc())
        .all()
    )
    return render_template('product_comments.html', product=product, comments=comments)

@app.route('/admin/comments/delete/<int:id>')
def delete_comment(id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    comment = Comment.query.get_or_404(id)
    product_id = comment.product_id
    db.session.delete(comment)
    db.session.commit()
    flash("Yorum silindi!", "success")
    return redirect(url_for('product_comments', product_id=product_id))

@app.route('/admin/orders')
def admin_orders():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    orders = (
        Order.query
        .filter(Order.admin_hidden.is_(False))
        .filter(Order.payment_status == "Tamamlandı")
        .order_by(Order.created_at.desc())
        .all()
    )
    return render_template('admin_orders.html', orders=orders)

@app.post('/admin/orders/<int:order_id>/status')
def update_order_status(order_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    new_status = request.form.get('status')
    allowed = {"Hazırlanıyor", "Kargolandı", "Teslim Edildi", "İptal"}
    order = Order.query.get_or_404(order_id)
    if new_status in allowed:
        order.status = new_status
        cargo_company = request.form.get("cargo_company", "").strip()
        cargo_tracking_no = request.form.get("cargo_tracking_no", "").strip()
        cargo_tracking_url = request.form.get("cargo_tracking_url", "").strip()
        # if new_status == "Kargolandı":
        #     if cargo_company and cargo_tracking_no:
        #         order.cargo_company = cargo_company
        #         order.cargo_tracking_no = cargo_tracking_no
        #         order.cargo_tracking_url = cargo_tracking_url or None
        if new_status == "Kargolandı":
            shipment = order.shipment
            if shipment and shipment.shipment_id:
                order.cargo_company = "DHL eCommerce"
                order.cargo_tracking_no = shipment.shipment_id
                order.cargo_tracking_url = os.getenv("DHL_TRACKING_URL", "https://www.dhlecommerce.com.tr/gonderitakip")
            elif cargo_company and cargo_tracking_no:
                # Manuel girilen diğer kargo firmaları
                order.cargo_company = cargo_company
                order.cargo_tracking_no = cargo_tracking_no
                order.cargo_tracking_url = cargo_tracking_url or None
            else:
                flash("Sipariş Kargolandı yapılamadı: geçerli takip numarası bulunamadı.", "danger")
                return redirect(url_for("admin_orders"))
        db.session.commit()
        if new_status == "Kargolandı":
            try:
                notify_shipped(order)
            except Exception:
                app.logger.exception("Kargo bildirimi gönderilemedi")
        flash("Sipariş durumu güncellendi.", "success")
    else:
        flash("Geçersiz durum seçimi.", "danger")
    return redirect(url_for('admin_orders'))

@app.post('/admin/orders/<int:order_id>/hide')
def hide_order_from_admin(order_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    order = Order.query.get_or_404(order_id)
    if order.status != "İptal":
        flash("Yalnızca iptal edilen siparişler listeden kaldırılabilir.", "danger")
        return redirect(url_for('admin_orders'))
    order.admin_hidden = True
    db.session.commit()
    flash(
        "Sipariş admin listesinden kaldırıldı. Veritabanındaki kayıt korunuyor.",
        "success",
    )
    return redirect(url_for('admin_orders'))

@app.post("/admin/orders/<int:order_id>/dhl/create")
def admin_create_dhl_order(order_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    order = Order.query.get_or_404(order_id)
    try:
        kg = int(request.form.get("kg", "0"))
        desi = int(request.form.get("desi", "0"))
        piece_count = int(request.form.get("piece_count", "1"))
        packaging_type = int(request.form.get("packaging_type", "3"))
        if kg <= 0:
            raise ValueError("Kg değeri sıfırdan büyük olmalıdır.")
        if desi <= 0:
            raise ValueError("Desi değeri sıfırdan büyük olmalıdır.")
        if piece_count <= 0:
            raise ValueError("Parça sayısı sıfırdan büyük olmalıdır.")
        if packaging_type not in {1, 2, 3}:
            raise ValueError("Geçersiz paket türü.")
        shipment = order.shipment
        if shipment is None:
            reference_id = build_reference_id(order.id)
            shipment = Shipment(order=order, reference_id=reference_id, piece_barcode=f"{reference_id}_PARCA1", kg=kg, desi=desi, piece_count=piece_count, packaging_type=packaging_type, status="DHL kaydı hazırlanıyor")
            db.session.add(shipment)
        else:
            shipment.kg = kg
            shipment.desi = desi
            shipment.piece_count = piece_count
            shipment.packaging_type = packaging_type
        shipment.last_error = None
        db.session.commit()
        create_recipient(order)
        shipment.recipient_created = True
        db.session.commit()
        result = create_dhl_order(order, desi=desi, kg=kg, piece_count=piece_count, packaging_type=packaging_type)
        if isinstance(result, list):
            if not result:
                raise DHLShipmentError("DHL CreateOrder yanıtı boş döndü.")
            result_data = result[0]
        elif isinstance(result, dict):
            result_data = result
        else:
            raise DHLShipmentError("DHL CreateOrder yanıt biçimi geçersiz.")
        shipment.order_invoice_id = str(result_data.get("orderInvoiceId", "")) or None
        shipment.order_invoice_detail_id = str(result_data.get("orderInvoiceDetailId", "")) or None
        shipment.shipper_branch_code = str(result_data.get("shipperBranchCode", "")) or None
        shipment.order_created = True
        shipment.status = "DHL siparişi oluşturuldu"
        shipment.last_error = None
        db.session.commit()
        flash("Alıcı ve DHL sipariş kaydı başarıyla oluşturuldu.", "success")
    except (ValueError, DHLAPIError, DHLShipmentError) as exc:
        db.session.rollback()
        shipment = order.shipment
        error_text = str(exc)
        if (isinstance(exc, DHLAPIError) and ("3002" in error_text or "BU SİPARİŞ NUMARASINA AİT KAYIT ZATEN VAR" in error_text.upper())):
            try:
                existing_result = get_order(shipment.reference_id)
                if isinstance(existing_result, list):
                    existing_data = existing_result[0] if existing_result else {}
                elif isinstance(existing_result, dict):
                    existing_data = existing_result
                else:
                    existing_data = {}
                order_data = existing_data.get("order", {})
                shipment_id = (order_data.get("shipmentId") or order_data.get("shipmentID") or order_data.get("shipmentNumber"))
                if shipment_id:
                    shipment.shipment_id = str(shipment_id)
                    order.cargo_company = "DHL eCommerce"
                    order.cargo_tracking_no = str(shipment_id)
                    order.cargo_tracking_url = os.getenv("DHL_TRACKING_URL", "https://www.dhlecommerce.com.tr/gonderitakip")
                shipment.order_created = True
                shipment.last_error = None
                if order_data.get("isTransformedToShipment") == 1:
                    shipment.status = "DHL gönderisi mevcut"
                else:
                    shipment.status = "DHL siparişi mevcut"
                db.session.commit()
                flash("Sipariş DHL sisteminde zaten mevcut. " "DHL bilgileri sistemimize senkronize edildi.", "success")
            except Exception as sync_exc:
                db.session.rollback()
                shipment = order.shipment
                if shipment:
                    shipment.status = "DHL senkronizasyon hatası"
                    shipment.last_error = str(sync_exc)
                    db.session.commit()
                app.logger.exception("Mevcut DHL siparişi senkronize edilemedi. order_id=%s", order_id)
                flash(f"Sipariş DHL'de mevcut ancak bilgiler alınamadı: {sync_exc}", "danger")
        else:
            if shipment:
                shipment.status = "DHL sipariş hatası"
                shipment.last_error = error_text
                db.session.commit()
            app.logger.exception("DHL siparişi oluşturulamadı. order_id=%s", order_id)
            flash(f"DHL siparişi oluşturulamadı: {exc}", "danger")

    except Exception as exc:
        db.session.rollback()
        shipment = order.shipment
        if shipment:
            shipment.status = "Beklenmeyen hata"
            shipment.last_error = str(exc)
            db.session.commit()
        app.logger.exception("Beklenmeyen DHL hatası. order_id=%s", order_id)
        flash("DHL işlemi sırasında beklenmeyen bir hata oluştu.", "danger")
    return redirect(url_for("admin_orders"))

@app.post("/admin/orders/<int:order_id>/dhl/barcode")
def admin_create_dhl_barcode(order_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    order = Order.query.get_or_404(order_id)
    shipment = order.shipment
    if shipment is None:
        flash("Önce DHL sipariş kaydı oluşturulmalıdır.", "danger")
        return redirect(url_for("admin_orders"))
    if not shipment.reference_id:
        flash("DHL referans numarası bulunamadı.", "danger")
        return redirect(url_for("admin_orders"))
    if not shipment.order_created:
        flash("Önce DHL sipariş kaydı oluşturulmalıdır.", "danger")
        return redirect(url_for("admin_orders"))
    try:
        kg = int(request.form.get("kg", shipment.kg or 0))
        desi = int(request.form.get("desi", shipment.desi or 0))
        piece_count = int(request.form.get("piece_count",shipment.piece_count or 1))
        packaging_type = int(request.form.get("packaging_type",shipment.packaging_type or 3))
        if kg <= 0:
            raise ValueError("Kg değeri sıfırdan büyük olmalıdır.")
        if desi <= 0:
            raise ValueError("Desi değeri sıfırdan büyük olmalıdır.")
        if piece_count <= 0:
            raise ValueError("Parça sayısı sıfırdan büyük olmalıdır.")
        if packaging_type not in {1, 2, 3}:
            raise ValueError("Geçersiz paket türü.")
        shipment.kg = kg
        shipment.desi = desi
        shipment.piece_count = piece_count
        shipment.packaging_type = packaging_type
        shipment.status = "DHL barkodu hazırlanıyor"
        shipment.last_error = None
        db.session.commit()
        result = create_barcode(
            shipment.reference_id,
            bill_of_landing_id=(order.order_number or shipment.reference_id),
            desi=desi,
            kg=kg,
            piece_count=piece_count,
            packaging_type=packaging_type,
        )
        if isinstance(result, list):
            if not result:
                raise DHLShipmentError("DHL CreateBarcode yanıtı boş döndü.")
            result_data = result[0]
        elif isinstance(result, dict):
            result_data = result
        else:
            raise DHLShipmentError("DHL CreateBarcode yanıt biçimi geçersiz.")
        shipment_id = (
            result_data.get("shipmentId") 
            or result_data.get("shipmentID")
            or result_data.get("shipmentNumber")
            #or result_data.get("referenceId")
        )
        barcodes = result_data.get("barcodes") or []
        if not barcodes:
            raise DHLShipmentError("DHL yanıtında barkod verisi bulunamadı.")
        first_barcode = barcodes[0]
        if isinstance(first_barcode, dict):
            zpl_value = first_barcode.get("value", "")
        else:
            zpl_value = str(first_barcode)
        if not zpl_value:
            raise DHLShipmentError("DHL yanıtında ZPL barkod değeri bulunamadı.")
        shipment.shipment_id = (
            str(shipment_id)
            if shipment_id
            else None
        )
        shipment.zpl_label = zpl_value
        shipment.barcode_created = True
        shipment.status = "DHL barkodu oluşturuldu"
        shipment.last_error = None
        order.cargo_company = "DHL eCommerce"
        if not shipment.shipment_id:
            raise DHLShipmentError("DHL gerçek gönderi numarası döndürmedi. " "Müşteriye takip numarası gönderilmedi.")
        order.cargo_tracking_no = shipment.shipment_id
        order.cargo_tracking_url = os.getenv("DHL_TRACKING_URL","https://www.dhlecommerce.com.tr/gonderitakip")
        db.session.commit()
        flash("DHL gönderi barkodu başarıyla oluşturuldu.","success")
    except (ValueError,DHLAPIError,DHLShipmentError) as exc:
        db.session.rollback()
        shipment = order.shipment
        if shipment:
            shipment.status = "DHL barkod hatası"
            shipment.last_error = str(exc)
            db.session.commit()
        app.logger.exception("DHL barkodu oluşturulamadı. order_id=%s",order_id)
        flash(f"DHL barkodu oluşturulamadı: {exc}","danger")
    except Exception as exc:
        db.session.rollback()
        shipment = order.shipment
        if shipment:
            shipment.status = "Beklenmeyen barkod hatası"
            shipment.last_error = str(exc)
            db.session.commit()
        app.logger.exception("Beklenmeyen DHL barkod hatası. order_id=%s",order_id)
        flash("DHL barkodu oluşturulurken beklenmeyen bir hata oluştu.","danger")
    return redirect(url_for("admin_orders"))

@app.get("/admin/orders/<int:order_id>/dhl/zpl")
def admin_download_dhl_zpl(order_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    order = Order.query.get_or_404(order_id)
    shipment = order.shipment
    if shipment is None or not shipment.zpl_label:
        flash("Bu sipariş için indirilebilir DHL barkodu bulunamadı.", "danger")
        return redirect(url_for("admin_orders"))
    filename = f"{shipment.reference_id or order.order_number}.zpl"
    return Response(
        shipment.zpl_label,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.post("/admin/orders/<int:order_id>/dhl/status")
def admin_update_dhl_status(order_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    order = Order.query.get_or_404(order_id)
    shipment = order.shipment
    if shipment is None or not shipment.reference_id:
        flash("Bu sipariş için DHL kaydı bulunamadı.","danger",)
        return redirect(url_for("admin_orders"))
    try:
        result = get_shipment_status(shipment.reference_id)
        if isinstance(result, list):
            result_data = result[0] if result else {}
        elif isinstance(result, dict):
            result_data = result
        else:
            raise DHLShipmentError("DHL durum yanıtı geçersiz biçimde döndü.")
        status_value = (
            result_data.get("status")
            or result_data.get("shipmentStatus")
            or result_data.get("statusDescription")
            or result_data.get("description")
        )
        if status_value:
            shipment.status = str(status_value)
        else:
            shipment.status = "DHL durumu alındı"
        shipment.last_error = None
        db.session.commit()
        flash("DHL gönderi durumu güncellendi.","success")
    except (DHLAPIError,DHLShipmentError) as exc:
        db.session.rollback()
        shipment.last_error = str(exc)
        shipment.status = "Durum sorgulama hatası"
        db.session.commit()
        app.logger.exception("DHL durumu sorgulanamadı. order_id=%s",order_id)
        flash(f"DHL durumu sorgulanamadı: {exc}","danger")
    except Exception as exc:
        db.session.rollback()
        shipment.last_error = str(exc)
        shipment.status = "Beklenmeyen durum hatası"
        db.session.commit()
        app.logger.exception("Beklenmeyen DHL durum hatası. order_id=%s",order_id)
        flash("DHL durumu sorgulanırken beklenmeyen bir hata oluştu.","danger")
    return redirect(url_for("admin_orders"))

@app.post("/admin/orders/<int:order_id>/dhl/cancel")
def admin_cancel_dhl_shipment(order_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    order = Order.query.get_or_404(order_id)
    shipment = order.shipment
    if shipment is None:
        flash("Bu sipariş için DHL kaydı bulunamadı.","danger")
        return redirect(url_for("admin_orders"))
    if not shipment.shipment_id:
        flash("Henüz iptal edilebilecek bir DHL gönderisi yok.","danger")
        return redirect(url_for("admin_orders"))
    try:
        cancel_shipment(shipment.reference_id,shipment.shipment_id)
        shipment.status = "İptal edildi"
        shipment.last_error = None
        order.cargo_tracking_no = None
        db.session.commit()
        flash("DHL gönderisi başarıyla iptal edildi.","success")
    except (DHLAPIError,DHLShipmentError) as exc:
        db.session.rollback()
        shipment.last_error = str(exc)
        shipment.status = "İptal hatası"
        db.session.commit()
        app.logger.exception("DHL iptal hatası. order_id=%s",order_id)
        flash(f"DHL iptal edilemedi: {exc}","danger")
    except Exception as exc:
        db.session.rollback()
        shipment.last_error = str(exc)
        shipment.status = "Beklenmeyen iptal hatası"
        db.session.commit()
        app.logger.exception("Beklenmeyen DHL iptal hatası. order_id=%s",order_id)
        flash("DHL iptal edilirken beklenmeyen bir hata oluştu.","danger")
    return redirect(url_for("admin_orders"))

@app.route('/product')
def product():
    category = request.args.get('category', '')
    q = request.args.get('q', '').strip()
    query = Product.query
    if category:
        query = query.filter_by(category=category)
    if q:
        like = f'%{q}%'
        query = query.filter(
            or_(Product.name.ilike(like), Product.description.ilike(like))
        )
    all_products = _order_products(query).all()
    categories = db.session.query(Product.category).distinct().all()
    categories = [cat[0] for cat in categories]
    seo_description = DEFAULT_SEO_DESCRIPTION
    if category:
        seo_description = (
            f"{category} kategorisindeki Gaziantep yöresel ürünlerini keşfedin. "
            "Doğal lezzetler, güvenli online alışveriş."
        )
    if q:
        seo_description = f"'{q}' araması için Gaziantep yöresel ürün sonuçları."
    return render_template(
        'product.html',
        products=all_products,
        categories=categories,
        selected_category=category,
        search_query=q,
        seo_title=f"Ürünler | {SITE_NAME}",
        seo_description=seo_description,
        seo_noindex=bool(q),
        seo_canonical=_absolute_url("product"),
    )

@app.route('/product/<int:id>')
def product_detail(id):
    product = Product.query.get_or_404(id)
    comments = Comment.query.filter_by(product_id=id).order_by(Comment.created_at.desc()).all()
    return render_template(
        'product_detail.html',
        product=product,
        comments=comments,
        seo_title=f"{product.name} | {SITE_NAME}",
        seo_description=_product_seo_description(product),
        seo_image=_absolute_asset_url(product.image),
        seo_type="product",
        seo_json_ld=[_product_json_ld(product)],
    )

@app.route('/about')
def about():
    return render_template(
        'about.html',
        seo_title=f"Hakkımızda | {SITE_NAME}",
        seo_description=(
            "Gaziantep Yöresel Ürünler hakkında bilgi alın. "
            "Yöresel lezzetleri sofranıza taşıyan güvenilir online mağaza."
        ),
    )

@app.route('/product/<int:product_id>/comment', methods=['POST'])
def add_comment(product_id):
    author_name = request.form.get('author_name', '').strip()
    content = request.form.get('content', '').strip()
    if not author_name:
        flash("Lütfen adınızı yazın.", "danger")
        return redirect(url_for('product_detail', id=product_id))
    if not content:
        flash("Yorum boş olamaz.", "danger")
        return redirect(url_for('product_detail', id=product_id))
    comment = Comment(
        product_id=product_id,
        author_name=author_name[:80],
        content=content
    )
    db.session.add(comment)
    db.session.commit()
    flash("Yorumunuz eklendi!", "success")
    return redirect(url_for('product_detail', id=product_id))

@app.route('/contact', methods=['GET', 'POST'])
@csrf.exempt
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        if name and email and message:
            new_msg = ContactMessage(name=name, email=email, message=message)
            db.session.add(new_msg)
            db.session.commit()
            flash("Mesajınız başarıyla gönderildi!", "success")
            return redirect(url_for('contact'))
        else:
            flash("Lütfen tüm alanları doldurun.", "danger")
    return render_template(
        'contact.html',
        seo_title=f"İletişim | {SITE_NAME}",
        seo_description=(
            "Gaziantep Yöresel Ürünler iletişim bilgileri. "
            "Sipariş, ürün ve destek talepleriniz için bize ulaşın."
        ),
    )

@app.route('/cart')
def cart():
    cart = _get_cart()
    items = []
    subtotal = 0
    for cart_key, item in cart.items():
        total = item['price'] * item['qty']
        subtotal += total
        # cart_key'den product_id'yi çıkar
        product_id = cart_key.split('_')[0]
        items.append({
            "id": product_id,
            "cart_key": cart_key,
            "name": item['name'],
            "price": item['price'],
            "unit": item['unit'],
            "qty": item['qty'],
            "total": total,
            "gramaj": item.get('gramaj'),
            "base_price": item.get('base_price', item['price'])
        })
    return render_template(
        "cart.html",
        items=items,
        subtotal=subtotal,
        seo_title=f"Sepetim | {SITE_NAME}",
        seo_noindex=True,
    )

@app.post("/cart/add")
@csrf.exempt
def cart_add():
    try:
        product_id = request.form.get("product_id")
        qty = int(request.form.get("qty", 1))
        gramaj = request.form.get("gramaj", "")  # 100, 500, 1000 veya boş       
        if not product_id:
            flash("Ürün bulunamadı!", "danger")
            return redirect(url_for("product"))       
        if qty <= 0:
            flash("Adet 1'den küçük olamaz!", "danger")
            return redirect(url_for("product_detail", id=product_id))
        product = Product.query.get_or_404(product_id)
        allowed_gramaj = product.gramaj_list
        if product.unit == "Kg":
            if not gramaj:
                flash("Lütfen gramaj seçin!", "danger")
                return redirect(url_for("product_detail", id=product_id))
            gramaj_value = int(gramaj)
            if gramaj_value not in allowed_gramaj:
                flash("Geçersiz gramaj seçimi!", "danger")
                return redirect(url_for("product_detail", id=product_id))
            calculated_price = product.price * (gramaj_value / 1000.0)
            display_unit = _format_gramaj_label(gramaj_value)
        else:
            calculated_price = product.price
            display_unit = product.unit or ""
            gramaj_value = None
        product_id_str = str(product_id)  # Sepet için string olarak sakla
        cart = _get_cart()
        cart_key = f"{product_id_str}_{gramaj_value}" if gramaj_value else product_id_str
        if cart_key in cart:
            cart[cart_key]['qty'] += qty
            flash(f"{product.name} sepete eklendi! (Toplam: {cart[cart_key]['qty']} adet)", "success")
        else:
            cart[cart_key] = {
                "name": product.name,
                "price": calculated_price,
                "unit": display_unit,
                "qty": qty,
                "base_price": product.price,  # Kilogram fiyatı sakla
                "gramaj": gramaj_value  # Gramaj bilgisini sakla
            }
            flash(f"{product.name} sepete eklendi!", "success")
        _save_cart(cart)
    except ValueError:
        flash("Geçersiz değer!", "danger")
    except Exception as e:
        flash("Bir hata oluştu!", "danger")
    return redirect(url_for("cart"))

@app.post("/cart/update")
@csrf.exempt
def cart_update():
    try:
        cart_key = request.form.get("cart_key")
        qty = int(request.form.get("qty", 1))
        if qty <= 0:
            flash("Adet 1'den küçük olamaz!", "danger")
            return redirect(url_for("cart"))
        cart = _get_cart()
        if cart_key and cart_key in cart:
            cart[cart_key]['qty'] = qty
            _save_cart(cart)
            flash(f"{cart[cart_key]['name']} adeti güncellendi!", "success")
        else:
            flash("Ürün sepette bulunamadı!", "danger")
    except ValueError:
        flash("Geçersiz adet değeri!", "danger")
    except Exception as e:
        flash("Bir hata oluştu!", "danger")
    return redirect(url_for("cart"))

@app.post("/cart/remove")
@csrf.exempt
def cart_remove():
    try:
        cart_key = request.form.get("cart_key")
        cart = _get_cart()
        if cart_key and cart_key in cart:
            product_name = cart[cart_key]['name']
            del cart[cart_key]
            _save_cart(cart)
            flash(f"{product_name} sepetten kaldırıldı!", "success")
        else:
            flash("Ürün sepette bulunamadı!", "danger")
    except Exception as e:
        flash("Bir hata oluştu!", "danger")

    return redirect(url_for("cart"))

@app.route('/checkout', methods=['GET'])
def checkout():
    cart = _get_cart()
    if not cart:
        flash("Sepetiniz boş. Önce ürün ekleyin.", "danger")
        return redirect(url_for("product"))
    items = []
    subtotal = 0
    for cart_key, item in cart.items():
        line_total = item['price'] * item['qty']
        subtotal += line_total
        items.append({
            "name": item['name'],
            "unit": item['unit'],
            "qty": item['qty'],
            "price": item['price'],
            "total": line_total,
            "gramaj": item.get('gramaj')
        })
    shipping_cost = _calculate_shipping_cost(subtotal)
    total = subtotal + shipping_cost
    return render_template(
        "checkout.html",
        items=items,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total=total,
        seo_title=f"Sipariş Tamamla | {SITE_NAME}",
        seo_noindex=True,
    )

@app.route('/create-order', methods=['POST'])
def create_order():
    cart = _get_cart()
    if not cart:
        flash("Sepetiniz boş. Önce ürün ekleyin.", "danger")
        return redirect(url_for("product"))
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    city = request.form.get("city", "").strip()
    district = request.form.get("district", "").strip()
    neighborhood = request.form.get("neighborhood", "").strip()
    address = request.form.get("address", "").strip()
    note = request.form.get("note", "").strip()
    legal_consent = request.form.get("legal_consent")
    notify_channel = request.form.get("notify_channel", "both")
    if not name or not phone or not email or not city or not district or not neighborhood or not address:
        flash("İsim, telefon, e-posta ve adres bilgileri zorunludur.", "danger")
        return redirect(url_for("checkout"))
    if not legal_consent:
        flash("Devam etmek için yasal sözleşmeleri onaylamanız gerekmektedir.", "danger")
        return redirect(url_for("checkout"))
    items = []
    subtotal = 0
    for cart_key, item in cart.items():
        line_total = item['price'] * item['qty']
        subtotal += line_total
        items.append({
            "name": item['name'],
            "unit": item['unit'],
            "qty": item['qty'],
            "price": item['price'],
            "total": line_total,
            "gramaj": item.get('gramaj')
        })
    shipping_cost = _calculate_shipping_cost(subtotal, city=city)
    total_amount = subtotal + shipping_cost
    order_number = _generate_order_number()
    while Order.query.filter_by(order_number=order_number).first():
        order_number = _generate_order_number()
    notify_sms = notify_channel in ["sms", "both"]
    notify_email = notify_channel in ["email", "both"]
    order = Order(
        order_number=order_number,
        customer_name=name,
        phone=phone,
        email=email,
        city=city,
        district=district,
        neighborhood=neighborhood,
        address=address,
        note=note,
        status="Ödeme Bekleniyor",
        payment_status="Beklemede",
        total_amount=total_amount,
        shipping_cost=shipping_cost,
        notify_sms=notify_sms,
        notify_email=notify_email,
        public_token=secrets.token_urlsafe(32)
    )
    for item in items:
        order.items.append(
            OrderItem(
                product_name=item["name"],
                quantity=item["qty"],
                price=item["price"],
                unit=item["unit"]
            )
        )
    db.session.add(order)
    db.session.commit()
    _clear_cart()
    return redirect(url_for("payment", public_token=order.public_token))

@app.route('/payment/<string:public_token>')
def payment(public_token):
    order = Order.query.filter_by(public_token=public_token).first_or_404()
    if order.payment_status == "Tamamlandı":
        return redirect(url_for("order_success", public_token=order.public_token))
    if order.status not in {"Ödeme Bekleniyor", "Ödeme Başarısız"}:
        flash("Bu sipariş için ödeme yapılamaz.", "danger")
        return redirect(url_for("home"))
    return render_template(
        "payment.html",
        order=order,
        paytr_enabled=os.getenv("PAYTR_PAYMENT_ENABLED", "False").lower() == "true",
        seo_title=f"Ödeme | {SITE_NAME}",
        seo_noindex=True,
    )

@app.post('/payment/paytr/start/<string:public_token>')
@limiter.limit("10 per hour")
def start_paytr_payment(public_token):
    order = Order.query.filter_by(public_token=public_token).first_or_404()
    if order.payment_status == "Tamamlandı":
        return redirect(url_for("order_success", public_token=order.public_token))
    if order.status not in {"Ödeme Bekleniyor", "Ödeme Başarısız",}:
        flash("Bu sipariş için yeni ödeme başlatılamaz.","danger")
        return redirect( url_for( "payment", public_token=order.public_token ))
    if (os.getenv("PAYTR_PAYMENT_ENABLED", "False").strip().lower() != "true"):
        flash("PayTR ödeme sistemi henüz etkinleştirilmedi.", "warning")
        return redirect( url_for( "payment", public_token=order.public_token))

    try:
        payment_amount_decimal = Decimal(str(order.total_amount)).quantize(Decimal("0.01"))
        payment_amount = format_payment_amount(payment_amount_decimal)
    except (TypeError, ValueError, InvalidOperation, ArithmeticError):
        app.logger.exception("PayTR sipariş tutarı doğrulanamadı: order=%s",order.id)
        flash("Sipariş tutarı doğrulanamadı.", "danger")
        return redirect(url_for("payment", public_token=order.public_token))

    if payment_amount_decimal <= Decimal("0.00"):
        app.logger.error("Geçersiz PayTR ödeme tutarı: " "order=%s amount=%s", order.id, payment_amount_decimal)
        flash("Sipariş tutarı ödeme için geçerli değil.","danger")

        return redirect(url_for("payment", public_token=order.public_token))

    merchant_oid = (f"PAYTR{order.id}{uuid.uuid4().hex[:16]}")

    try:
        user_basket = build_user_basket(order.items, shipping_cost=order.shipping_cost or 0)
    except (TypeError, ValueError, ArithmeticError):
        app.logger.exception("PayTR sepeti oluşturulamadı: order=%s", order.id)
        flash("Ödeme sepeti hazırlanamadı.", "danger")
        return redirect( url_for( "payment", public_token=order.public_token))

    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        user_ip = (forwarded_for.split(",")[0].strip())
    else:
        user_ip = (request.remote_addr or "").strip()

    if not user_ip:
        app.logger.error("PayTR müşteri IP adresi alınamadı: order=%s", order.id)
        flash("Ödeme için IP adresiniz alınamadı.", "danger")
        return redirect(url_for("payment", public_token=order.public_token))

    user_name = (order.customer_name or "").strip()[:60]
    user_address = " ".join(
        [
            str(order.address or "").strip(),
            str(order.neighborhood or "").strip(),
            str(order.district or "").strip(),
            str(order.city or "").strip(),
        ]
    ).strip()[:400]

    user_phone = (order.phone or "").strip()[:20]
    email = (order.email or "").strip()
    if not email:
        app.logger.error("PayTR ödeme için e-posta eksik: order=%s", order.id)
        flash("Ödeme işlemi için e-posta adresi gereklidir.", "danger")
        return redirect(url_for("payment", public_token=order.public_token))

    merchant_ok_url = _absolute_url("paytr_payment_success", public_token=order.public_token)
    merchant_fail_url = _absolute_url("paytr_payment_fail", public_token=order.public_token)
    test_mode = (1 if os.getenv("PAYTR_TEST_MODE", "1").strip() == "1" else 0)
    debug_on = (1 if os.getenv("PAYTR_DEBUG_ON", "1").strip() == "1" else 0)

    payment_attempt = Payment(
        order_id=order.id,
        provider="PAYTR",
        payment_order_id=merchant_oid,
        amount=payment_amount_decimal,
        currency_code="TL",
        status="CREATED",
    )

    try:
        db.session.add(payment_attempt)
        db.session.flush()
        iframe_token = request_iframe_token(
            user_ip=user_ip,
            merchant_oid=merchant_oid,
            email=email,
            payment_amount=payment_amount,
            user_basket=user_basket,
            user_name=user_name,
            user_address=user_address,
            user_phone=user_phone,
            merchant_ok_url=merchant_ok_url,
            merchant_fail_url=merchant_fail_url,
            no_installment=0,
            max_installment=0,
            currency="TL",
            test_mode=test_mode,
            debug_on=debug_on,
            timeout_limit=30,
            lang="tr",
        )
        payment_attempt.status = "IFRAME_CREATED"
        order.payment_status = "Beklemede"
        order.status = "Ödeme Bekleniyor"
        db.session.commit()

    except Exception as exc:
        db.session.rollback()
        app.logger.exception("PayTR ödeme başlatılamadı: " "order=%s merchant_oid=%s", order.id, merchant_oid)
        if debug_on:
            flash(f"PayTR ödeme isteği oluşturulamadı: {exc}", "danger")
        else:
            flash("Ödeme işlemi başlatılamadı. " "Lütfen tekrar deneyin.", "danger")
        return redirect(url_for("payment", public_token=order.public_token))

    app.logger.info("PayTR ödeme başlatıldı. " "order=%s merchant_oid=%s", order.id, merchant_oid)
    return render_template(
        "paytr_iframe.html",
        order=order,
        iframe_token=iframe_token,
        seo_title=f"Güvenli Ödeme | {SITE_NAME}",
        seo_noindex=True,
    )

@app.get("/payment/paytr/success/<string:public_token>")
def paytr_payment_success(public_token):
    order = Order.query.filter_by(public_token=public_token).first_or_404()
    if order.payment_status == "Tamamlandı":
        return redirect(url_for("order_success", public_token=order.public_token))
    return render_template(
        "paytr_success_wait.html",
        order=order,
        seo_title=f"Ödeme Kontrol Ediliyor | {SITE_NAME}",
        seo_noindex=True,
    )

@app.get("/payment/paytr/fail/<string:public_token>")
def paytr_payment_fail(public_token):
    order = Order.query.filter_by(public_token=public_token).first_or_404()
    return render_template(
        "paytr_fail.html",
        order=order,
        seo_title=f"Ödeme Tamamlanamadı | {SITE_NAME}",
        seo_noindex=True,
    )

@app.post("/payment/paytr/callback")
@csrf.exempt
def paytr_callback():
    merchant_oid = (request.form.get("merchant_oid") or "").strip()
    status = (request.form.get("status") or "").strip()
    total_amount = (request.form.get("total_amount") or "").strip()
    received_hash = (request.form.get("hash") or "").strip()
    if status not in {"success", "failed"}:
        app.logger.warning("PayTR callback geçersiz status: " "merchant_oid=%s status=%s", merchant_oid, status)
        return Response("PAYTR notification failed", status=400, mimetype="text/plain",)
    if not all([merchant_oid, status, total_amount, received_hash]):
        app.logger.error("PayTR callback eksik alanlar: " "merchant_oid=%s status=%s total_amount=%s", merchant_oid, status, total_amount)
        return Response("PAYTR notification failed", status=400, mimetype="text/plain")

    try:
        hash_ok = verify_callback_hash(merchant_oid=merchant_oid, status=status, total_amount=total_amount, received_hash=received_hash,)
    except Exception:
        app.logger.exception("PayTR callback hash hesaplama hatası: merchant_oid=%s", merchant_oid)
        return Response("PAYTR notification failed", status=400, mimetype="text/plain")
    if not hash_ok:
        app.logger.warning("PayTR callback bad hash: merchant_oid=%s", merchant_oid)
        return Response("PAYTR notification failed: bad hash", status=400, mimetype="text/plain")

    payment_attempt = Payment.query.filter_by(provider="PAYTR", payment_order_id=merchant_oid).first()
    if payment_attempt is None:
        app.logger.error("PayTR callback ödeme kaydı bulunamadı: merchant_oid=%s", merchant_oid)
        return Response("PAYTR notification failed", status=404, mimetype="text/plain")
    order = payment_attempt.order
    if order is None:
        app.logger.error( "PayTR callback sipariş bulunamadı: merchant_oid=%s", merchant_oid)
        return Response("PAYTR notification failed", status=404, mimetype="text/plain")
    if payment_attempt.status in {"SUCCESS", "FAILED"}:
        app.logger.info("PayTR tekrar callback alındı: " "merchant_oid=%s status=%s", merchant_oid, payment_attempt.status)
        return Response("OK", mimetype="text/plain")
    successful_payment = Payment.query.filter(
        Payment.order_id == order.id,
        Payment.provider == "PAYTR",
        Payment.status == "SUCCESS",
        Payment.id != payment_attempt.id,
    ).first()
    if successful_payment is not None:
        app.logger.info(
            "PayTR callback göz ardı edildi; sipariş başka bir "
            "ödeme denemesiyle zaten tamamlanmış. "
            "order=%s merchant_oid=%s successful_payment=%s",
            order.id,
            merchant_oid,
            successful_payment.payment_order_id,
        )
        return Response("OK", mimetype="text/plain")

    try:
        callback_payment_amount = (request.form.get("payment_amount") or "").strip()
        expected_payment_amount = format_payment_amount(payment_attempt.amount)
    except (InvalidOperation, TypeError, ValueError, ArithmeticError):
        app.logger.exception("PayTR callback tutar kontrolü yapılamadı: " "merchant_oid=%s", merchant_oid)
        return Response( "PAYTR notification failed", status=400, mimetype="text/plain")
    if callback_payment_amount != expected_payment_amount:
        app.logger.error("PayTR callback sipariş tutarı uyuşmuyor: " "merchant_oid=%s expected=%s received=%s", merchant_oid, expected_payment_amount, callback_payment_amount,)
        return Response("PAYTR notification failed", status=400, mimetype="text/plain")

    failed_reason_code = (request.form.get("failed_reason_code") or "").strip()
    failed_reason_msg = (request.form.get("failed_reason_msg") or "").strip()
    payment_type = (request.form.get("payment_type") or "").strip()
    currency = (request.form.get("currency") or "").strip()
    test_mode = (request.form.get("test_mode") or "").strip()

    if payment_type != "card":
        app.logger.error("PayTR callback beklenmeyen ödeme tipi: " "merchant_oid=%s payment_type=%s", merchant_oid, payment_type)
        return Response("PAYTR notification failed", status=400, mimetype="text/plain")
    if currency not in {"TL", "TRY"}:
        app.logger.error("PayTR callback beklenmeyen para birimi: " "merchant_oid=%s currency=%s", merchant_oid, currency)
        return Response("PAYTR notification failed", status=400, mimetype="text/plain")

    if status == "success":
        payment_attempt.status = "SUCCESS"
        payment_attempt.hash_verified = True
        payment_attempt.response_code = "success"
        payment_attempt.response_message = (
            f"PayTR ödeme başarılı. "
            f"payment_type={payment_type}, "
            f"currency={currency}, "
            f"test_mode={test_mode}, "
            f"total_amount={total_amount}"
        )
        order.payment_status = "Tamamlandı"
        order.status = "Ödeme Alındı"

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception("PayTR başarılı ödeme DB commit hatası: " "merchant_oid=%s", merchant_oid)
            return Response("PAYTR notification failed", status=500, mimetype="text/plain")
        app.logger.info("PayTR ödeme başarılı: " "order=%s merchant_oid=%s", order.id, merchant_oid)
        try:
            notify_payment_received(order)
        except Exception:
            app.logger.exception("PayTR ödeme sonrası müşteri bildirimi başarısız: " "order=%s", order.id)
        try:
            notify_admin_new_order(order)
        except Exception:
            app.logger.exception("PayTR ödeme sonrası admin bildirimi başarısız: " "order=%s", order.id)
        return Response("OK", mimetype="text/plain")

    payment_attempt.status = "FAILED"
    payment_attempt.hash_verified = True
    payment_attempt.response_code = (failed_reason_code or status)
    payment_attempt.response_message = (failed_reason_msg or "PayTR ödeme işlemi başarısız.")
    order.payment_status = "Başarısız"
    order.status = "Ödeme Başarısız"
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("PayTR başarısız ödeme DB commit hatası: " "merchant_oid=%s", merchant_oid)
        return Response("PAYTR notification failed", status=500, mimetype="text/plain")
    app.logger.info("PayTR ödeme başarısız: " "order=%s merchant_oid=%s reason_code=%s reason=%s", order.id, merchant_oid, failed_reason_code, failed_reason_msg,)
    return Response("OK", mimetype="text/plain")

@app.route('/order-success/<string:public_token>')
def order_success(public_token):
    order = Order.query.filter_by(public_token=public_token).first_or_404()
    if order.payment_status != "Tamamlandı":
        flash("Bu sipariş için ödeme tamamlanmamış.", "warning")
        return redirect(url_for("home"))
    return render_template(
        "order_success.html",
        order=order,
        seo_title=f"Sipariş Alındı | {SITE_NAME}",
        seo_noindex=True,
    )

@app.route('/mesafeli-satis-sozlesmesi')
def mesafeli_satis():
    return render_template("legal/mesafeli_satis.html")

@app.route('/on-bilgilendirme-formu')
def on_bilgilendirme():
    return render_template("legal/on_bilgilendirme.html")

@app.route('/gizlilik-politikasi')
def gizlilik_politikasi():
    return render_template("legal/gizlilik.html")

@app.route('/cerez-politikasi')
def cerez_politikasi():
    return render_template("legal/cerez_politikasi.html")

@app.route('/kullanim-kosullari')
def kullanim_kosullari():
    return render_template("legal/kullanim_kosullari.html")

@app.route('/kvkk-aydinlatma-metni')
def kvkk_aydinlatma():
    return render_template("legal/kvkk_aydinlatma.html")

if __name__ == '__main__': 
    with app.app_context(): 
        db.create_all() 
    app.run(host="0.0.0.0", port=5000, debug=True)