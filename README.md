Gaziantep Yöresel Ürünler
Gaziantep Yöresel Ürünler, Gaziantep'e özgü yöresel gıda ve ürünlerin çevrim içi olarak sergilenmesi ve satışının yönetilmesi amacıyla geliştirilmiş Flask tabanlı bir e-ticaret uygulamasıdır. Uygulama; ürün kataloğu, alışveriş sepeti, sipariş ve ödeme akışı ile yönetici işlemlerini tek bir web uygulamasında bir araya getirir. gaziantepyöresel.com.tr adresinden çalışan web sitesini inceleyebilirsiniz. 
Not: Bu README, proje arşivindeki kod ve dosya yapısına göre hazırlanmıştır. Harici servislerin (ödeme, kargo, SMS ve e-posta) kullanılabilmesi için ilgili sağlayıcılardan alınmış geçerli hesap ve API bilgilerinin ayrıca yapılandırılması gerekir.

Özellikler
- Ürünlerin listelenmesi ve ürün detay sayfaları
- Ürün görselleri ve tanıtım videolarının sunulması
- Alışveriş sepeti ve sipariş oluşturma akışı
- PayTR iFrame üzerinden ödeme entegrasyonu
- Yönetici girişi ve yönetim paneli
- Ürün ekleme, düzenleme ve silme işlemleri
- Siparişlerin görüntülenmesi ve yönetilmesi
- Sipariş ödeme durumu ve sipariş numarası takibi
- DHL eCommerce / MNG Kargo servisleri üzerinden gönderi işlemleri, barkod ve gönderi durumu sorgulama
- Netgsm üzerinden SMS bildirimi
- SMTP üzerinden e-posta gönderimi
- Ürün feed'i (/google-merchant.xml), robots.txt ve site haritası (sitemap.xml) uç noktaları
- SEO meta bilgileri ve Google etiketleri
- İletişim, hakkımızda ve yasal bilgilendirme sayfaları
- CSRF koruması ve istek sınırlandırma (rate limiting)
Kullanılan teknolojiler
- Python: Uygulamanın ana programlama dili
- Flask: Web uygulaması ve HTTP rotaları
- Flask-SQLAlchemy / SQLAlchemy: Veritabanı modelleri ve işlemleri
- SQLite: Projede varsayılan olarak kullanılan yerel veritabanı
- Flask-WTF / CSRFProtect: Form güvenliği ve CSRF koruması
- Flask-Limiter: İstek sınırlandırma
- python-dotenv: Ortam değişkenlerinin .env dosyasından yüklenmesi
- Requests: Harici servis API'leriyle HTTP iletişimi
- Gunicorn: Üretim ortamında WSGI sunucusu olarak kullanılabilir
- HTML, CSS ve JavaScript: Arayüz ve istemci tarafı işlevleri
Bağımlılıkların listesi requirements.txt dosyasındadır.
Proje yapısı
web_sitesi/
├── app.py                  # Flask uygulaması, modeller ve sayfa rotaları
├── requirements.txt        # Python bağımlılıkları
├── migrate_db.py           # Veritabanı tabloları/kolonları için yardımcı migration betiği
├── seed.py                 # Başlangıç/örnek verileri hazırlama betiği
├── services/               # Harici servis entegrasyonları
│   ├── dhl_api.py
│   ├── dhl_auth.py
│   ├── dhl_barcode.py
│   ├── dhl_cbs.py
│   ├── dhl_exceptions.py
│   ├── dhl_query.py
│   ├── dhl_shipment.py
│   └── paytr_payment.py
├── scripts/                # Yardımcı geliştirme betikleri
├── static/                 # CSS, ürün görselleri ve videolar
├── templates/              # Jinja2 HTML şablonları
└── instance/               # Yerel SQLite veritabanı (Git'e eklenmemelidir)
Arşivdeki instance/gaziantep.db yerel veritabanıdır. Gerçek sipariş veya müşteri bilgileri içerebileceğinden Git deposuna eklenmemelidir. instance/ klasörü ve veritabanı dosyaları .gitignore ile hariç tutulmalıdır.

Kurulum
1. Depoyu klonlayın
git clone <GITHUB_REPOSITORY_URL>
cd web_sitesi
2. Sanal ortam oluşturun ve etkinleştirin
Windows (PowerShell):
py -m venv .venv
.venv\Scripts\Activate.ps1
Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate
3. Bağımlılıkları yükleyin
python -m pip install --upgrade pip
pip install -r requirements.txt
4. Ortam değişkenlerini ayarlayın
Proje kök dizininde .env.example dosyasını .env adıyla kopyalayın ve kendi ortamınıza uygun değerleri girin. .env dosyası GitHub'a yüklenmemelidir.

Windows PowerShell:
Copy-Item .env.example .env
Linux / macOS:
cp .env.example .env
Uygulama açılışta SECRET_KEY, ADMIN_USERNAME ve ADMIN_PASSWORD değişkenlerini zorunlu olarak kontrol eder. Bunlar tanımlı değilse uygulama başlatılmaz. Ödeme, kargo, SMS ve e-posta entegrasyonları için ilgili değişkenler de ilgili servis kullanılacaksa doldurulmalıdır.
5. Veritabanı ve uygulamayı başlatın
Proje SQLite veritabanını instance/gaziantep.db konumunda kullanacak şekilde yapılandırılmıştır. app.py doğrudan çalıştırıldığında uygulama bağlamında db.create_all() çağrısı yapar ve Flask geliştirme sunucusunu 5000 portunda başlatır:
python app.py
Ardından tarayıcıdan localhost adresini açın. 
python app.py içindeki debug=True ayarı geliştirme içindir. İnternete açık üretim ortamında Flask geliştirme sunucusunu veya debug modunu kullanmayın; uygun bir WSGI sunucusu (ör. Gunicorn) ve ters proxy yapılandırması kullanın.

Ortam değişkenleri
Aşağıdaki liste, proje kodunda okunduğu görülen ortam değişkenlerini içerir. .env.example dosyanızda bunları tanımlayabilirsiniz. Gizli değerleri boş bırakın veya açıklayıcı yer tutucular kullanın; gerçek değerleri Git'e eklemeyin.
Uygulama ve yönetici
SECRET_KEY=
ADMIN_USERNAME=
ADMIN_PASSWORD=
ADMIN_NOTIFICATION_EMAIL=
SITE_NAME=Gaziantep Yöresel Ürünler
SITE_URL=
SITE_DESCRIPTION=
SITE_KEYWORDS=
SESSION_COOKIE_SECURE=False
E-posta (SMTP)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
Netgsm SMS
NETGSM_USERNAME=
NETGSM_PASSWORD=
NETGSM_MSGHEADER=
DHL eCommerce / MNG Kargo
DHL_BASE_URL=https://testapi.mngkargo.com.tr/mngapi/api
DHL_CLIENT_ID=
DHL_CLIENT_SECRET=
DHL_CUSTOMER_NUMBER=
DHL_CUSTOMER_PASSWORD=
DHL_API_VERSION=
DHL_TIMEOUT_SECONDS=20
DHL_TRACKING_URL=https://www.dhlecommerce.com.tr/gonderitakip
PayTR
PAYTR_PAYMENT_ENABLED=False
PAYTR_MERCHANT_ID=
PAYTR_MERCHANT_KEY=
PAYTR_MERCHANT_SALT=
PAYTR_TEST_MODE=1
PAYTR_DEBUG_ON=1
Bu değişkenlerin tamamının her kurulumda zorunlu olduğu anlamına gelmez. İlgili entegrasyon etkinleştirildiğinde o servisin gerektirdiği bilgiler sağlanmalıdır. Üretim ortamında test/sandbox adresi ve test modu yerine sağlayıcının onaylı canlı ortam ayarları kullanılmalıdır.
Veritabanı notları
- Varsayılan veritabanı SQLite'tır ve instance/gaziantep.db dosyasında tutulur.
- Veritabanı dosyası ve gerçek kullanıcı/sipariş verileri GitHub'a yüklenmemelidir.
- migrate_db.py, mevcut veritabanı şemasını kontrol edip bazı eksik tabloları ve kolonları oluşturmak/güncellemek için hazırlanmıştır. Çalıştırmadan önce veritabanının yedeğini alın ve betiğin mevcut veritabanınız üzerindeki etkisini kontrol edin.
- Üretim veritabanında migration işlemlerini doğrudan ve yedeksiz çalıştırmayın.
Güvenlik
- .env, veritabanı dosyaları, yedekler, loglar ve kişisel veriler depoya eklenmemelidir.
- API anahtarları, parolalar, tokenlar ve ödeme sağlayıcısı gizli anahtarları kaynak koduna yazılmamalıdır.
- SECRET_KEY için tahmin edilmesi zor, benzersiz bir değer kullanın.
- Üretim ortamında HTTPS kullanın ve SESSION_COOKIE_SECURE=True ayarını yalnızca HTTPS doğru şekilde etkinleştirildiğinde açın.
- Gerçek müşteri/sipariş verilerini örnek veri veya ekran görüntüsü olarak herkese açık depoya koymayın.
Lisans
Bu depoya henüz bir lisans dosyası eklenmemiştir. Projenin kullanım ve dağıtım koşulları belirlenene kadar tüm haklar saklıdır.