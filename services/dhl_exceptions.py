class DHLAPIError(Exception):
    """DHL API ile ilgili genel hata."""


class DHLConfigurationError(DHLAPIError):
    """Eksik veya hatalı ortam değişkeni."""


class DHLAuthError(DHLAPIError):
    """DHL Identity API kimlik doğrulama hatası."""


class DHLShipmentError(DHLAPIError):
    """DHL gönderi oluşturma/güncelleme hatası."""


class DHLQueryError(DHLAPIError):
    """DHL gönderi ve CBS sorgulama hatası."""
