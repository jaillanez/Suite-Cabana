"""Adaptador de Mercado Pago (docs/00 §8).

En cualquier modo el pago se crea con el token del prestador, así que entra en
su cuenta: la plataforma nunca custodia el dinero ajeno.

- **Cobro directo** (`MP_COBRO_DIRECTO`): el anfitrión carga su propia
  credencial. Mercado Pago no deja retener `marketplace_fee` con una credencial
  que no salió del OAuth de una aplicación marketplace, así que la comisión
  queda en el snapshot de la reserva y se liquida aparte.
- **Marketplace** (OAuth, pendiente): con el token obtenido por OAuth la
  plataforma retiene su parte con `marketplace_fee` en el mismo pago.

Las notificaciones de la cuenta de la plataforma se validan con `x-signature`.
Las de cobro directo llegan sin una firma que podamos verificar (el secreto es
de la aplicación del anfitrión), y no hace falta: del aviso solo se toma el id
del pago, y el estado se consulta a Mercado Pago con la credencial del
anfitrión. Un aviso inventado no puede dar por pagada una reserva.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.pagos.base import (
    Cobro,
    ErrorDePasarela,
    EstadoPago,
    Notificacion,
    NotificacionInvalida,
    Pasarela,
    PasarelaNoDisponible,
    Preferencia,
)

API = "https://api.mercadopago.com"
TIEMPO_LIMITE = 20.0

# Estados de Mercado Pago traducidos a los nuestros.
ESTADOS = {
    "approved": EstadoPago.APROBADO,
    "authorized": EstadoPago.APROBADO,
    "pending": EstadoPago.PENDIENTE,
    "in_process": EstadoPago.PENDIENTE,
    "in_mediation": EstadoPago.EN_DISPUTA,
    "rejected": EstadoPago.RECHAZADO,
    "cancelled": EstadoPago.CANCELADO,
    "refunded": EstadoPago.DEVUELTO,
    "charged_back": EstadoPago.DEVUELTO,
}


class MercadoPago(Pasarela):
    codigo = "mercadopago"
    nombre = "Mercado Pago"
    reparte_automaticamente = True

    def __init__(self, token: str | None = None, secreto_webhook: str | None = None):
        s = get_settings()
        self._token = token if token is not None else s.mp_access_token
        self._secreto = secreto_webhook if secreto_webhook is not None else s.mp_webhook_secret
        self._cobro_directo = s.mp_cobro_directo

    @property
    def disponible(self) -> bool:
        # En cobro directo la credencial es de cada anfitrión: se ofrece siempre,
        # y al pagar se exige la del anfitrión de esa reserva.
        return bool(self._token) or self._cobro_directo

    @property
    def motivo_no_disponible(self) -> str:
        return (
            "Falta MP_ACCESS_TOKEN para operar con Mercado Pago "
            "(o MP_COBRO_DIRECTO para que cada anfitrión cobre con su cuenta)."
        )

    def _cliente(self, token: str | None = None) -> httpx.Client:
        return httpx.Client(
            base_url=API,
            timeout=TIEMPO_LIMITE,
            headers={"Authorization": f"Bearer {token or self._token}"},
        )

    def crear_preferencia(self, cobro: Cobro) -> Preferencia:
        self.exigir_disponible()
        # Con la cuenta del prestador el cobro entra en su cuenta. Sin ella va a
        # la de la plataforma, que es el modo de prueba.
        token = cobro.cuenta_prestador or self._token
        if not token:
            raise PasarelaNoDisponible(
                "Este anfitrión todavía no vinculó su cuenta de Mercado Pago."
            )

        cuerpo: dict[str, Any] = {
            "items": [
                {
                    "title": cobro.descripcion[:250],
                    "quantity": 1,
                    "unit_price": float(cobro.total),
                    "currency_id": cobro.moneda,
                }
            ],
            "external_reference": cobro.codigo_reserva,
            "marketplace_fee": (
                float(cobro.comision_plataforma) if cobro.retener_comision else None
            ),
            "notification_url": cobro.url_notificacion,
            "metadata": {"codigo_reserva": cobro.codigo_reserva, **cobro.metadatos},
            "back_urls": {
                k: v
                for k, v in (
                    ("success", cobro.url_exito),
                    ("failure", cobro.url_fallo),
                    ("pending", cobro.url_pendiente),
                )
                if v
            },
            "auto_return": "approved" if cobro.url_exito else None,
        }
        if cobro.email_pagador:
            cuerpo["payer"] = {"email": cobro.email_pagador}
        cuerpo = {k: v for k, v in cuerpo.items() if v is not None}

        try:
            with self._cliente(token) as c:
                r = c.post("/checkout/preferences", json=cuerpo)
                r.raise_for_status()
                datos = r.json()
        except httpx.HTTPError as e:
            raise ErrorDePasarela(f"Mercado Pago rechazó el cobro: {e}") from e

        return Preferencia(
            id_externo=str(datos["id"]),
            url_pago=datos.get("init_point") or datos.get("sandbox_init_point", ""),
            pasarela=self.codigo,
            datos=datos,
        )

    def _firma_valida(self, cuerpo: bytes, cabeceras: dict[str, str]) -> bool:
        """Verifica `x-signature` según el esquema de Mercado Pago.

        Sin secreto configurado no se puede verificar: se rechaza en vez de
        confiar, porque una notificación falsa da una reserva por pagada.
        """
        if not self._secreto:
            return False
        firma = cabeceras.get("x-signature") or cabeceras.get("X-Signature") or ""
        peticion = cabeceras.get("x-request-id") or cabeceras.get("X-Request-Id") or ""
        partes = dict(
            p.strip().split("=", 1) for p in firma.split(",") if "=" in p
        )
        ts, hash_recibido = partes.get("ts"), partes.get("v1")
        if not ts or not hash_recibido:
            return False

        try:
            datos = json.loads(cuerpo or b"{}")
        except json.JSONDecodeError:
            return False
        id_pago = str((datos.get("data") or {}).get("id") or datos.get("id") or "")

        plantilla = f"id:{id_pago};request-id:{peticion};ts:{ts};"
        esperado = hmac.new(
            self._secreto.encode(), plantilla.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(esperado, hash_recibido)

    def leer_notificacion_sin_firma(self, id_pago: str) -> Notificacion:
        """Aviso de cobro directo: el estado se toma de Mercado Pago, no del aviso.

        Solo sirve con la credencial del anfitrión: con ella, un id inventado o
        de otra cuenta no se encuentra, y uno real trae su estado verdadero.
        """
        if not id_pago:
            raise NotificacionInvalida("La notificación no trae el id del pago")
        return self.consultar(id_pago)

    def leer_notificacion(self, cuerpo: bytes, cabeceras: dict[str, str]) -> Notificacion:
        self.exigir_disponible()
        if not self._firma_valida(cuerpo, cabeceras):
            raise NotificacionInvalida("La firma de la notificación no coincide")

        datos = json.loads(cuerpo or b"{}")
        id_pago = str((datos.get("data") or {}).get("id") or datos.get("id") or "")
        if not id_pago:
            raise NotificacionInvalida("La notificación no trae el id del pago")
        # El webhook solo avisa que algo pasó: el estado se consulta a la fuente.
        return self.consultar(id_pago)

    def consultar(self, id_externo: str) -> Notificacion:
        self.exigir_disponible()
        try:
            with self._cliente() as c:
                r = c.get(f"/v1/payments/{id_externo}")
                r.raise_for_status()
                pago = r.json()
        except httpx.HTTPError as e:
            raise ErrorDePasarela(f"No pudimos consultar el pago {id_externo}: {e}") from e

        return Notificacion(
            id_externo=str(pago["id"]),
            codigo_reserva=pago.get("external_reference"),
            estado=ESTADOS.get(pago.get("status", ""), EstadoPago.PENDIENTE),
            monto=Decimal(str(pago.get("transaction_amount") or 0)),
            pasarela=self.codigo,
            datos=pago,
        )

    def reintegrar(self, id_externo: str, monto: Decimal | None = None) -> Notificacion:
        self.exigir_disponible()
        cuerpo = {"amount": float(monto)} if monto is not None else {}
        try:
            with self._cliente() as c:
                r = c.post(f"/v1/payments/{id_externo}/refunds", json=cuerpo)
                r.raise_for_status()
        except httpx.HTTPError as e:
            raise ErrorDePasarela(f"No pudimos reintegrar el pago {id_externo}: {e}") from e
        return self.consultar(id_externo)


@dataclass(frozen=True)
class CuentaMercadoPago:
    """La cuenta a la que pertenece una credencial."""

    id: str
    nombre: str
    de_prueba: bool


class CredencialInvalida(Exception):
    """Mercado Pago no reconoce la credencial."""


def verificar_credencial(token: str) -> CuentaMercadoPago:
    """Pregunta a Mercado Pago de quién es la credencial antes de guardarla.

    Guardar una credencial sin probarla dejaría la publicación habilitada y el
    viajero se enteraría al pagar.
    """
    token = token.strip()
    if not token or " " in token:
        raise CredencialInvalida("Pegá el Access Token completo, sin espacios.")
    try:
        with httpx.Client(
            base_url=API, timeout=TIEMPO_LIMITE, headers={"Authorization": f"Bearer {token}"}
        ) as c:
            r = c.get("/users/me")
    except httpx.HTTPError as e:
        raise ErrorDePasarela(f"No pudimos comunicarnos con Mercado Pago: {e}") from e
    if r.status_code in (400, 401, 403, 404):
        raise CredencialInvalida(
            "Mercado Pago no reconoce esa credencial. Revisá que sea el Access Token "
            "de producción de tu cuenta."
        )
    if r.is_error:
        raise ErrorDePasarela(f"Mercado Pago respondió {r.status_code}")
    datos = r.json()
    nombre = datos.get("nickname") or datos.get("email") or str(datos.get("id", ""))
    etiquetas = datos.get("tags") or []
    return CuentaMercadoPago(
        id=str(datos["id"]),
        nombre=str(nombre)[:200],
        de_prueba=token.startswith("TEST-") or "test_user" in etiquetas,
    )
