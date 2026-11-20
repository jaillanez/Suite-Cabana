from decimal import Decimal
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CLAVE_INSEGURA = "cambiar-en-produccion"
LARGO_MINIMO_CLAVE = 32  # RFC 7518 §3.2 para HMAC-SHA256


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+psycopg://suite:suite@localhost:5432/suite_cabana"
    secret_key: str = CLAVE_INSEGURA
    access_token_minutes: int = 60 * 24
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # Ingreso con Google: sin client id, el endpoint responde que no está configurado.
    google_client_id: str = ""
    minutos_token_verificacion: int = 60 * 48

    # Fotos. Mientras no haya almacenamiento de objetos con CDN (docs/00 §9),
    # viven en disco y las sirve el backend.
    # Dirección pública del backend: entra en las URLs de calendario que el
    # prestador pega en Booking o Airbnb, así que no puede ser relativa.
    url_publica_api: str = "http://localhost:8000"
    media_dir: str = "media"
    media_url: str = "/media"
    foto_ancho_maximo: int = 1600
    foto_peso_maximo_mb: int = 12
    fotos_minimas: int = 5

    # --- Notificaciones (docs/01 §5 R9) ---
    # Sin SMTP configurado y en entorno local, los correos se escriben en el log
    # en vez de enviarse. El proveedor de WhatsApp está sin definir (docs/01 §9).
    smtp_host: str = ""
    smtp_puerto: int = 587
    smtp_usuario: str = ""
    smtp_password: str = ""
    smtp_desde: str = ""
    smtp_tls: bool = True
    # Bandeja de entrada de reservas: cada anfitrión reenvía los mails de las
    # plataformas a una dirección propia, y el proveedor nos los postea.
    # Sin `correo_entrante_secreto` el endpoint queda cerrado, que es lo correcto:
    # un buzón abierto al mundo deja que cualquiera te bloquee fechas.
    correo_entrante_proveedor: str = ""
    correo_entrante_secreto: str = ""
    correo_entrante_dominio: str = ""

    whatsapp_proveedor: str = ""
    whatsapp_token: str = ""

    # Términos y condiciones vigentes (docs/01 §5 R11).
    version_terminos: str = "2026-09"

    iva_comision: Decimal = Decimal("0.21")
    minutos_retencion_pago: int = 15
    horas_aprobacion_prestador: int = 24

    # --- Pasarelas de pago (docs/00 §8) ---
    # El producto no se ata a una billetera. Cada una tiene sus credenciales;
    # vacías significa que existe pero no está disponible. La predeterminada es
    # la que se ofrece primero al viajero.
    pasarela_predeterminada: str = "simulada"
    url_publica_web: str = "http://localhost:3000"

    # Mercado Pago (modo marketplace): adaptador implementado.
    mp_access_token: str = ""
    mp_client_id: str = ""
    mp_client_secret: str = ""
    mp_webhook_secret: str = ""

    # Previstas: el adaptador se escribe cuando tengamos su documentación.
    modo_client_id: str = ""
    modo_client_secret: str = ""
    modo_webhook_secret: str = ""
    uala_api_key: str = ""
    uala_webhook_secret: str = ""
    cuenta_dni_api_key: str = ""
    cuenta_dni_webhook_secret: str = ""
    naranja_x_api_key: str = ""
    naranja_x_webhook_secret: str = ""
    paypal_client_id: str = ""
    paypal_secret: str = ""


    @model_validator(mode="after")
    def clave_suficiente(self) -> "Settings":
        """Fuera de local, una clave corta o la de ejemplo no arranca.

        Con una clave débil cualquiera puede firmarse un token de sesión: es
        preferible que el servicio no levante a que levante inseguro.
        """
        if self.environment == "local":
            return self
        if self.secret_key == CLAVE_INSEGURA:
            raise ValueError("SECRET_KEY sigue siendo la de ejemplo: cambiala antes de desplegar")
        if len(self.secret_key.encode()) < LARGO_MINIMO_CLAVE:
            raise ValueError(
                f"SECRET_KEY necesita al menos {LARGO_MINIMO_CLAVE} bytes "
                f"(tiene {len(self.secret_key.encode())})"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
