"""Contacto por WhatsApp entre viajero y anfitrión.

Sin proveedor de mensajería: un enlace `wa.me` que abre la conversación con el
mensaje ya escrito. Reglas:

- El teléfono se guarda normalizado (`+549…` para un celular argentino), así el
  enlace sale bien sin importar cómo lo escribió cada uno: con 0, con 15, con
  espacios o guiones.
- El enlace existe solo con la reserva **confirmada**. Antes, el número serviría
  para arreglar por fuera y saltear la reserva (y la comisión); después de una
  cancelación ya no hay nada que coordinar.
- El viajero ve el del anfitrión y el anfitrión el del viajero; nadie más.
"""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import quote

from sqlalchemy.orm import object_session

from app.models import Reserva, Usuario
from app.models.enums import EstadoReserva

Lado = Literal["viajero", "anfitrion"]

MENSAJE_INVALIDO = (
    "Ese número no parece un celular. Escribilo con la característica, "
    "por ejemplo 264 412 3456. Si es de otro país, empezá con +"
)
MENSAJE_AMBIGUO = (
    "No sabemos dónde está el 15 en ese número. Escribilo sin el 15, "
    "por ejemplo 264 412 3456"
)
FALTA_TELEFONO = (
    "Dejanos tu WhatsApp: con la reserva confirmada, el anfitrión y vos se pueden "
    "escribir desde la reserva"
)


class TelefonoInvalido(ValueError):
    def __init__(self, mensaje: str = MENSAJE_INVALIDO) -> None:
        super().__init__(mensaje)


def _sin_15(d: str) -> str:
    """Saca el 15 de un celular escrito a la vieja usanza (0264 15 412-3456).

    La característica tiene 2, 3 o 4 cifras y el 15 va justo después. Si el 15
    puede estar en más de un lugar (011 15 1512-3456), no se adivina: un número
    mal corregido le escribe a otra persona.
    """
    lugares = [largo for largo in (2, 3, 4) if d[largo : largo + 2] == "15"]
    if len(lugares) != 1:
        raise TelefonoInvalido(MENSAJE_AMBIGUO if lugares else MENSAJE_INVALIDO)
    largo = lugares[0]
    return d[:largo] + d[largo + 2 :]


def normalizar(texto: str) -> str:
    """El número en formato internacional (`+5492644123456`). Levanta TelefonoInvalido.

    Sin código de país se asume Argentina. Un número de otro país tiene que venir
    con `+` o `00` adelante, y se deja tal cual.
    """
    t = (texto or "").strip()
    internacional = t.startswith("+")
    d = re.sub(r"\D", "", t)
    if d.startswith("00"):
        d, internacional = d[2:], True
    if internacional and not d.startswith("54"):
        if 8 <= len(d) <= 15:
            return f"+{d}"
        raise TelefonoInvalido()

    if d.startswith("54"):
        d = d[2:]
        if d.startswith("9"):
            d = d[1:]
    d = d.removeprefix("0")
    if len(d) == 12:
        d = _sin_15(d)
    if len(d) != 10:
        raise TelefonoInvalido()
    return f"+549{d}"


def _fechas(reserva: Reserva) -> str:
    from app.services import reservas

    item = reservas.principal(reserva)
    if item.inicio_en is not None:
        return f"el {item.fecha_inicio:%d/%m}"
    return f"del {item.fecha_inicio:%d/%m} al {item.fecha_fin:%d/%m}"


def enlace(reserva: Reserva, para: Lado) -> str | None:
    """El enlace para que `para` le escriba al otro lado, o None si no corresponde."""
    if reserva.estado is not EstadoReserva.CONFIRMADA:
        return None
    db = object_session(reserva)
    if db is None:
        return None
    from app.services import reservas

    item = reservas.principal(reserva)
    lugar = item.unidad.publicacion.titulo
    viajero = db.get(Usuario, reserva.usuario_id)
    anfitrion = db.get(Usuario, item.unidad.publicacion.prestador.usuario_id)
    if viajero is None or anfitrion is None:
        return None

    if para == "viajero":
        destino = anfitrion.telefono
        texto = f"Hola, te escribo por la reserva {reserva.codigo} en {lugar} ({_fechas(reserva)})."
    else:
        destino = viajero.telefono
        texto = (
            f"Hola {viajero.nombre}, te escribo por tu reserva {reserva.codigo} en "
            f"{lugar} ({_fechas(reserva)})."
        )
    if not destino:
        return None
    try:
        # Los cargados antes de normalizar se guardaron como los escribió cada uno.
        numero = normalizar(destino)
    except TelefonoInvalido:
        return None
    return f"https://wa.me/{numero.lstrip('+')}?text={quote(texto)}"
