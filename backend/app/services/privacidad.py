"""Qué se muestra de la ubicación de un alojamiento, y a quién.

La dirección y el punto exacto son la casa de alguien: se ven solo con una
reserva confirmada. En público el mapa muestra un punto aproximado, redondeado
a dos decimales (~1 km). Redondear —en vez de sumar ruido al azar— da siempre
el mismo punto, así que pedir la ficha muchas veces y promediar no lo revela.
"""

from __future__ import annotations

import math

from app.models.enums import EstadoReserva

DECIMALES_PUBLICOS = 2

#: Estados en los que el viajero ya tiene derecho a saber adónde va.
ESTADOS_CON_DIRECCION = (EstadoReserva.CONFIRMADA, EstadoReserva.COMPLETADA)

#: Estados en los que el prestador ve los datos que el viajero cargó para el
#: servicio (la dirección donde lo buscan, su vuelo): ya pagó. Con una reserva a
#: solicitud el prestador los necesita para decidir.
ESTADOS_CON_DATOS = (
    EstadoReserva.PENDIENTE_APROBACION,
    EstadoReserva.CONFIRMADA,
    EstadoReserva.COMPLETADA,
)


def aproximar(valor: float | None) -> float | None:
    return None if valor is None else round(valor, DECIMALES_PUBLICOS)


def distancia_publica(km: float | None) -> float | None:
    """La distancia al punto exacto, en kilómetros enteros (mínimo 1).

    Con decimales, pedir la búsqueda desde tres lugares alcanzaría para
    triangular la casa, aunque el punto que se muestra esté redondeado.
    """
    return None if km is None else float(max(1, round(km)))


def radio_publico(km: float) -> float:
    """El radio del filtro, en kilómetros enteros: con decimales, achicarlo de a
    poco hasta que el alojamiento sale de la lista daría su distancia exacta."""
    return float(max(1, math.ceil(km)))
