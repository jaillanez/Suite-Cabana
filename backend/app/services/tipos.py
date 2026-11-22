"""Qué se reserva cómo. La lógica que asume noches —búsqueda, ficha, cotización—
solo tiene que ver lo que se reserva por noches; un salón (docs/04) va por horario.

Se filtra por el modo de reserva y no por el código "alojamiento": un tipo nuevo
que no sea por noches queda afuera solo, sin tocar cada consulta.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models import Publicacion, TipoServicio
from app.models.enums import ModoReserva


def de_modo(modo: ModoReserva):
    """Condición para un `where`: publicaciones cuyo tipo se reserva de ese modo."""
    return Publicacion.tipo_servicio_id.in_(
        select(TipoServicio.id).where(TipoServicio.modo_reserva == modo)
    )


def por_noches():
    return de_modo(ModoReserva.NOCHES)
