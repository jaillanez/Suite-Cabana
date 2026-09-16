from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+psycopg://suite:suite@localhost:5432/suite_cabana"
    secret_key: str = "cambiar-en-produccion"
    access_token_minutes: int = 60 * 24
    cors_origins: list[str] = ["http://localhost:3000"]

    iva_comision: Decimal = Decimal("0.21")
    minutos_retencion_pago: int = 15
    horas_aprobacion_prestador: int = 24

    mp_access_token: str = ""
    mp_client_id: str = ""
    mp_client_secret: str = ""
    mp_webhook_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
