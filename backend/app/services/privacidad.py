"""Qué se muestra de la ubicación de un alojamiento, y a quién.

La dirección y el punto exacto son la casa de alguien: se ven solo con una
reserva confirmada. En público el mapa muestra un punto aproximado, redondeado
a dos decimales (~1 km). Redondear —en vez de sumar ruido al azar— da siempre
el mismo punto, así que pedir la ficha muchas veces y promediar no lo revela.
"""

from __future__ import annotations

from app.models.enums import EstadoReserva

DECIMALES_PUBLICOS = 2

#: Estados en los que el viajero ya tiene derecho a saber adónde va.
ESTADOS_CON_DIRECCION = (EstadoReserva.CONFIRMADA, EstadoReserva.COMPLETADA)


def aproximar(valor: float | None) -> float | None:
    return None if valor is None else round(valor, DECIMALES_PUBLICOS)
