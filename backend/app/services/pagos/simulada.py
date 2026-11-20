"""Pasarela simulada para desarrollo y pruebas.

Existe para poder recorrer el circuito completo de reserva y pago sin credenciales
de ninguna billetera: se crea la reserva, se "paga", llega la notificación y la
reserva se confirma. Es la única forma de probar la lógica de negocio —retención
de fechas, snapshot de comisión, idempotencia del webhook— sin dinero real.

Nunca está disponible fuera de entorno local. Si alguien la configura en
producción, no arranca.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from decimal import Decimal

from app.core.config import get_settings
from app.services.pagos.base import (
    Cobro,
    EstadoPago,
    Notificacion,
    NotificacionInvalida,
    Pasarela,
    Preferencia,
)


class Simulada(Pasarela):
    codigo = "simulada"
    nombre = "Pago simulado (solo desarrollo)"
    reparte_automaticamente = True

    @property
    def disponible(self) -> bool:
        return get_settings().environment == "local"

    @property
    def motivo_no_disponible(self) -> str:
        return "El pago simulado solo funciona en entorno local."

    def crear_preferencia(self, cobro: Cobro) -> Preferencia:
        self.exigir_disponible()
        s = get_settings()
        id_externo = f"sim-{uuid.uuid4().hex[:16]}"
        base = s.url_publica_web.rstrip("/")
        return Preferencia(
            id_externo=id_externo,
            url_pago=(
                f"{base}/pago-simulado?pago={id_externo}"
                f"&reserva={cobro.codigo_reserva}&total={cobro.total}"
            ),
            pasarela=self.codigo,
            datos={"total": str(cobro.total), "comision": str(cobro.comision_plataforma)},
        )

    def firmar(self, cuerpo: bytes) -> str:
        """La firma que la pantalla de pago simulado tiene que mandar."""
        return hmac.new(
            get_settings().secret_key.encode(), cuerpo, hashlib.sha256
        ).hexdigest()

    def leer_notificacion(self, cuerpo: bytes, cabeceras: dict[str, str]) -> Notificacion:
        self.exigir_disponible()
        firma = cabeceras.get("x-firma-simulada") or cabeceras.get("X-Firma-Simulada") or ""
        if not hmac.compare_digest(self.firmar(cuerpo), firma):
            raise NotificacionInvalida("Firma inválida")

        datos = json.loads(cuerpo or b"{}")
        estado = EstadoPago(datos.get("estado", "aprobado"))
        return Notificacion(
            id_externo=str(datos["pago"]),
            codigo_reserva=datos.get("reserva"),
            estado=estado,
            monto=Decimal(str(datos.get("total", 0))),
            pasarela=self.codigo,
            datos=datos,
        )

    def consultar(self, id_externo: str) -> Notificacion:
        self.exigir_disponible()
        # No hay servidor al que preguntarle: el estado lo trae la notificación.
        return Notificacion(
            id_externo=id_externo,
            codigo_reserva=None,
            estado=EstadoPago.PENDIENTE,
            monto=None,
            pasarela=self.codigo,
        )

    def reintegrar(self, id_externo: str, monto: Decimal | None = None) -> Notificacion:
        self.exigir_disponible()
        return Notificacion(
            id_externo=id_externo,
            codigo_reserva=None,
            estado=EstadoPago.DEVUELTO,
            monto=monto,
            pasarela=self.codigo,
        )
