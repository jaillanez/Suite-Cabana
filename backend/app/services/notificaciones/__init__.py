"""Buzón de notificaciones (docs/01 §5 R9).

Se encola, se guarda, y después se envía. El envío puede fallar; el registro no.

Canales:
- Correo: por consola en desarrollo, por SMTP cuando esté configurado.
- WhatsApp: previsto, sin proveedor definido todavía (`docs/01 §9`). Sus mensajes
  se guardan marcados como descartados, para poder reenviarlos el día que haya
  proveedor en vez de perderlos.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notificacion
from app.models.enums import CanalNotificacion, EstadoNotificacion
from app.services.notificaciones.base import (
    Canal,
    CanalNoDisponible,
    CanalPendiente,
    ErrorDeEnvio,
    Mensaje,
)
from app.services.notificaciones.correo import CorreoPorConsola, CorreoSMTP
from app.services.notificaciones.plantillas import armar

__all__ = [
    "Canal",
    "CanalNoDisponible",
    "ErrorDeEnvio",
    "Mensaje",
    "canales",
    "encolar",
    "enviar_pendientes",
]

registro = logging.getLogger("notificaciones")
MAXIMO_INTENTOS = 5


def canales() -> dict[CanalNotificacion, Canal]:
    """El canal que corresponde a cada medio, según lo configurado."""
    smtp = CorreoSMTP()
    consola = CorreoPorConsola()
    return {
        CanalNotificacion.EMAIL: smtp if smtp.disponible else consola,
        CanalNotificacion.WHATSAPP: CanalPendiente(
            CanalNotificacion.WHATSAPP,
            "WhatsApp",
            "Falta elegir el proveedor (docs/01 §9).",
        ),
    }


def encolar(
    db: Session,
    evento: str,
    canal: CanalNotificacion,
    destino: str,
    datos: dict,
    usuario_id: uuid.UUID | None = None,
    reserva_id: uuid.UUID | None = None,
) -> Notificacion | None:
    """Guarda una notificación en el buzón. Devuelve None si no hay a dónde mandarla."""
    if not destino:
        return None

    plantilla = armar(evento, datos)
    notificacion = Notificacion(
        usuario_id=usuario_id,
        reserva_id=reserva_id,
        canal=canal,
        evento=evento,
        destino=destino,
        asunto=plantilla.asunto,
        cuerpo=plantilla.cuerpo,
        estado=EstadoNotificacion.PENDIENTE,
        datos=datos,
    )
    db.add(notificacion)
    db.flush()
    return notificacion


def enviar(db: Session, notificacion: Notificacion) -> bool:
    """Intenta enviar una. Devuelve si salió."""
    canal = canales()[notificacion.canal]
    notificacion.intentos += 1

    if not canal.disponible:
        # No se pierde: queda registrada para reenviarla cuando haya proveedor.
        notificacion.estado = EstadoNotificacion.DESCARTADA
        notificacion.error = canal.motivo_no_disponible
        db.flush()
        return False

    try:
        canal.enviar(
            Mensaje(
                destino=notificacion.destino,
                asunto=notificacion.asunto or "",
                cuerpo=notificacion.cuerpo,
            )
        )
    except (ErrorDeEnvio, CanalNoDisponible) as e:
        notificacion.error = str(e)
        notificacion.estado = (
            EstadoNotificacion.FALLIDA
            if notificacion.intentos >= MAXIMO_INTENTOS
            else EstadoNotificacion.PENDIENTE
        )
        db.flush()
        return False

    notificacion.estado = EstadoNotificacion.ENVIADA
    notificacion.enviada_en = datetime.now()
    notificacion.error = None
    db.flush()
    return True


def enviar_pendientes(db: Session, limite: int = 100) -> dict[str, int]:
    """Vacía el buzón. Pensada para la cola de trabajos (docs/00 §9)."""
    pendientes = list(
        db.scalars(
            select(Notificacion)
            .where(
                Notificacion.estado == EstadoNotificacion.PENDIENTE,
                Notificacion.intentos < MAXIMO_INTENTOS,
            )
            .order_by(Notificacion.creado_en)
            .limit(limite)
        )
    )
    enviadas = sum(1 for n in pendientes if enviar(db, n))
    return {"intentadas": len(pendientes), "enviadas": enviadas}
