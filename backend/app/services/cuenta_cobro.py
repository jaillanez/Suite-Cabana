"""La cuenta donde cobra cada anfitrión (hoy, Mercado Pago con credencial propia).

Es el único lugar que lee o escribe la credencial: la guarda cifrada y nunca la
devuelve hacia afuera. Lo que se muestra es el nombre de la cuenta.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.models import Prestador
from app.services import cifrado
from app.services.pagos.mercadopago import (
    CredencialInvalida,
    CuentaMercadoPago,
    verificar_credencial,
)


def vincular(prestador: Prestador, token: str) -> CuentaMercadoPago:
    """Verifica la credencial con Mercado Pago y la guarda cifrada.

    En producción no se acepta una de prueba: la publicación quedaría habilitada
    y ningún pago entraría de verdad.
    """
    cuenta = verificar_credencial(token)
    if cuenta.de_prueba and get_settings().environment == "production":
        raise CredencialInvalida(
            "Esa es una credencial de prueba: con ella no se cobra de verdad. "
            "Usá la de producción."
        )
    prestador.mp_user_id = cuenta.id
    prestador.mp_cuenta = cuenta.nombre
    prestador.mp_access_token = cifrado.cifrar(token.strip())
    prestador.mp_refresh_token = None
    return cuenta


def desvincular(prestador: Prestador) -> None:
    prestador.mp_user_id = None
    prestador.mp_cuenta = None
    prestador.mp_access_token = None
    prestador.mp_refresh_token = None


def credencial(prestador: Prestador) -> str | None:
    """La credencial en claro, para cobrar. None si no hay o no se puede leer."""
    if not prestador.mp_access_token:
        return None
    try:
        return cifrado.descifrar(prestador.mp_access_token)
    except cifrado.SecretoIlegible:
        return None
