"""Conectar la cuenta de Mercado Pago del anfitrión con un botón (OAuth), en vez
de pedirle que pegue un Access Token.

El recorrido:
1. El anfitrión toca "Conectar con Mercado Pago" y va a la página de
   autorización de Mercado Pago con un `state` firmado que dice quién es y vence
   en 15 minutos (sin él, cualquiera podría colgarle su cuenta a otro).
2. Autoriza y Mercado Pago lo devuelve a `/cuenta/mercadopago` con un `code`.
3. Acá se cambia el `code` por su credencial y la de renovación, se pregunta de
   quién es la cuenta y se guarda todo cifrado.

Con una credencial salida de este OAuth, Mercado Pago deja que la plataforma
retenga su comisión en el mismo pago (`marketplace_fee`): el resto entra en la
cuenta del anfitrión y la plataforma nunca tiene en su poder plata ajena.

La credencial dura 180 días; la tarea periódica la renueva antes de que venza.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.security import TokenInvalido, crear_token, leer_token
from app.services.pagos.base import ErrorDePasarela
from app.services.pagos.mercadopago import API, TIEMPO_LIMITE

log = logging.getLogger(__name__)

AUTORIZACION = "https://auth.mercadopago.com.ar/authorization"
TIPO_ESTADO = "mp_oauth"
MINUTOS_ESTADO = 15
#: Se renueva cuando faltan menos de estos días para que venza.
DIAS_ANTES_DE_RENOVAR = 30


class ConexionInvalida(Exception):
    """El pedido de conexión no es válido: vencido, de otro usuario, rechazado."""


@dataclass(frozen=True)
class Credenciales:
    access_token: str
    refresh_token: str | None
    user_id: str
    vence_en: datetime
    de_prueba: bool


def disponible() -> bool:
    """Si la plataforma tiene su aplicación de Mercado Pago configurada."""
    s = get_settings()
    return bool(s.mp_client_id and s.mp_client_secret)


def url_de_vuelta() -> str:
    return f"{get_settings().url_publica_web.rstrip('/')}/cuenta/mercadopago"


def url_autorizacion(usuario_id: str) -> str:
    """A dónde mandar al anfitrión para que autorice."""
    if not disponible():
        raise ConexionInvalida("La conexión con Mercado Pago todavía no está configurada")
    estado = crear_token(usuario_id, tipo=TIPO_ESTADO, minutos=MINUTOS_ESTADO)
    return f"{AUTORIZACION}?" + urlencode(
        {
            "client_id": get_settings().mp_client_id,
            "response_type": "code",
            "platform_id": "mp",
            "state": estado,
            "redirect_uri": url_de_vuelta(),
        }
    )


def validar_estado(estado: str, usuario_id: str) -> None:
    """El `state` que volvió tiene que ser nuestro, vigente y del mismo usuario:
    si no, alguien podría hacer que otro conecte la cuenta del atacante."""
    try:
        sujeto = leer_token(estado, tipo=TIPO_ESTADO)
    except TokenInvalido as e:
        raise ConexionInvalida(
            "El pedido de conexión venció o no es válido. Volvé a tocar el botón."
        ) from e
    if sujeto != usuario_id:
        raise ConexionInvalida("Ese pedido de conexión es de otra cuenta.")


def _pedir_token(datos: dict) -> Credenciales:
    s = get_settings()
    try:
        with httpx.Client(base_url=API, timeout=TIEMPO_LIMITE) as c:
            r = c.post(
                "/oauth/token",
                data={"client_id": s.mp_client_id, "client_secret": s.mp_client_secret, **datos},
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as e:
        raise ErrorDePasarela(f"No pudimos comunicarnos con Mercado Pago: {e}") from e
    if r.status_code in (400, 401, 403):
        raise ConexionInvalida(
            "Mercado Pago no aceptó la conexión. Volvé a intentarlo desde el botón."
        )
    if r.is_error:
        raise ErrorDePasarela(f"Mercado Pago respondió {r.status_code}")
    try:
        j = r.json()
        token = str(j["access_token"])
        usuario = str(j["user_id"])
        segundos = int(j.get("expires_in") or 15_552_000)  # 180 días
    except (ValueError, KeyError, TypeError) as e:
        raise ErrorDePasarela("Mercado Pago devolvió una respuesta que no entendemos") from e
    return Credenciales(
        access_token=token,
        refresh_token=j.get("refresh_token"),
        user_id=usuario,
        vence_en=datetime.now(UTC) + timedelta(seconds=segundos),
        de_prueba=j.get("live_mode") is False or token.startswith("TEST-"),
    )


def intercambiar(codigo: str) -> Credenciales:
    """El `code` de la vuelta, por la credencial del anfitrión."""
    if not codigo or len(codigo) > 400:
        raise ConexionInvalida("Mercado Pago no mandó el código de autorización.")
    return _pedir_token(
        {"grant_type": "authorization_code", "code": codigo, "redirect_uri": url_de_vuelta()}
    )


def renovar(refresh_token: str) -> Credenciales:
    return _pedir_token({"grant_type": "refresh_token", "refresh_token": refresh_token})
