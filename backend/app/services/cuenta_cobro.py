"""La cuenta donde cobra cada anfitrión: Mercado Pago, conectada con el botón
(OAuth, `mp_oauth`) o con una credencial pegada a mano.

Es el único lugar que lee o escribe la credencial: la guarda cifrada y nunca la
devuelve hacia afuera. Lo que se muestra es el nombre de la cuenta.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Prestador
from app.services import cifrado, mp_oauth
from app.services.pagos.base import ErrorDePasarela
from app.services.pagos.mercadopago import (
    CredencialInvalida,
    CuentaMercadoPago,
    verificar_credencial,
)

log = logging.getLogger(__name__)


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
    # Pegada a mano: cobra, pero Mercado Pago no deja retener la comisión.
    prestador.mp_oauth = False
    prestador.mp_token_vence_en = None
    return cuenta


def vincular_oauth(prestador: Prestador, codigo: str) -> CuentaMercadoPago:
    """Cierra la conexión con el botón: cambia el `code` por la credencial, se
    fija de quién es la cuenta y la guarda cifrada, con la de renovación."""
    cred = mp_oauth.intercambiar(codigo)
    if cred.de_prueba and get_settings().environment == "production":
        raise CredencialInvalida(
            "Esa es una cuenta de prueba de Mercado Pago: con ella no se cobra de verdad."
        )
    cuenta = verificar_credencial(cred.access_token)
    if cuenta.id != cred.user_id:
        # Mercado Pago dice que la credencial es de una cuenta y /users/me de otra:
        # no se guarda nada antes de entender qué pasó.
        raise CredencialInvalida("Mercado Pago devolvió datos que no coinciden. Probá de nuevo.")
    _guardar(prestador, cred)
    prestador.mp_user_id = cuenta.id
    prestador.mp_cuenta = cuenta.nombre
    return cuenta


def _guardar(prestador: Prestador, cred: mp_oauth.Credenciales) -> None:
    prestador.mp_access_token = cifrado.cifrar(cred.access_token)
    prestador.mp_refresh_token = (
        cifrado.cifrar(cred.refresh_token) if cred.refresh_token else None
    )
    prestador.mp_oauth = True
    prestador.mp_token_vence_en = cred.vence_en


def renovar_por_vencer(db: Session, ahora: datetime | None = None) -> dict[str, int]:
    """Para la tarea periódica: renueva las credenciales del botón que vencen en
    menos de 30 días. Una que no se puede renovar se deja como está y se reintenta
    en la próxima vuelta; si vence, el anfitrión tiene que volver a conectar."""
    ahora = ahora or datetime.now(UTC)
    limite = ahora + timedelta(days=mp_oauth.DIAS_ANTES_DE_RENOVAR)
    renovadas = fallidas = 0
    for p in db.scalars(
        select(Prestador).where(
            Prestador.mp_oauth.is_(True),
            Prestador.mp_refresh_token.is_not(None),
            Prestador.mp_token_vence_en < limite,
        )
    ):
        try:
            cred = mp_oauth.renovar(cifrado.descifrar(p.mp_refresh_token))
        except (mp_oauth.ConexionInvalida, ErrorDePasarela, cifrado.SecretoIlegible) as e:
            log.warning("No se pudo renovar la credencial de %s: %s", p.id, e.__class__.__name__)
            fallidas += 1
            continue
        if cred.user_id != p.mp_user_id:
            log.warning("La renovación de %s devolvió otra cuenta: no se guarda", p.id)
            fallidas += 1
            continue
        _guardar(p, cred)
        renovadas += 1
    db.flush()
    return {"mp_renovadas": renovadas, "mp_sin_renovar": fallidas}


def desvincular(prestador: Prestador) -> None:
    prestador.mp_user_id = None
    prestador.mp_cuenta = None
    prestador.mp_access_token = None
    prestador.mp_refresh_token = None
    prestador.mp_oauth = False
    prestador.mp_token_vence_en = None


def credencial(prestador: Prestador) -> str | None:
    """La credencial en claro, para cobrar. None si no hay o no se puede leer."""
    if not prestador.mp_access_token:
        return None
    try:
        return cifrado.descifrar(prestador.mp_access_token)
    except cifrado.SecretoIlegible:
        return None
