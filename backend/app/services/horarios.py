"""Disponibilidad por rango de hora (salones de eventos, docs/04 §5 S2).

Es la contraparte de los bloqueos por noche, con la misma regla de fondo
(CLAUDE.md §6): el choque entre dos reservas lo detecta la base con una
restricción de exclusión, no un `if`. Entre el chequeo y la inserción puede
meterse otra transacción, y la restricción es lo único que cierra esa ventana.

Los rangos son semiabiertos, [inicio, fin): un evento que termina a las 18 y otro
que empieza a las 18 no se pisan. Todo se guarda con zona horaria, y un rango
puede cruzar la medianoche (de 21 a 5 h).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import BloqueoHorario, Unidad
from app.models.enums import ModoReserva, OrigenBloqueo

#: La hora "de reloj" de los salones es la de Argentina, sin horario de verano.
ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
#: Ningún bloqueo de un salón dura más que esto: cortaría errores de carga (un
#: fin con el año mal escrito tomaría el salón por meses).
DURACION_MAXIMA = timedelta(hours=48)
DURACION_MINIMA = timedelta(minutes=30)


class HorarioInvalido(ValueError):
    """El rango no tiene sentido: al revés, sin zona horaria, demasiado largo."""


class HorarioOcupado(Exception):
    """Ese rango se superpone con otro bloqueo activo de la unidad."""


@dataclass(frozen=True)
class Ocupado:
    inicio: datetime
    fin: datetime
    origen: OrigenBloqueo


def _validar(unidad: Unidad, inicio: datetime, fin: datetime) -> None:
    if unidad.publicacion.tipo_servicio.modo_reserva is not ModoReserva.HORAS:
        raise HorarioInvalido("Esta unidad no se alquila por horario")
    if inicio.tzinfo is None or fin.tzinfo is None:
        # Sin zona, "21:00" puede ser de cualquier lugar: se rechaza en vez de adivinar.
        raise HorarioInvalido("El horario tiene que venir con zona horaria")
    if fin <= inicio:
        raise HorarioInvalido("El fin tiene que ser posterior al inicio")
    if fin - inicio < DURACION_MINIMA:
        raise HorarioInvalido("El rango es demasiado corto")
    if fin - inicio > DURACION_MAXIMA:
        raise HorarioInvalido("Un bloqueo no puede durar más de 48 horas")


def _vigente(ahora: datetime):
    """Bloqueos que ocupan de verdad: activos y, si son retenciones, sin vencer."""
    return and_(
        BloqueoHorario.activo.is_(True),
        or_(BloqueoHorario.vence_en.is_(None), BloqueoHorario.vence_en > ahora),
    )


def _rango(inicio: datetime, fin: datetime):
    return func.tstzrange(inicio, fin, "[)")


def libre(
    db: Session, unidad_id, inicio: datetime, fin: datetime, ahora: datetime | None = None
) -> bool:
    """Si nadie ocupa ningún momento de [inicio, fin)."""
    ahora = ahora or datetime.now(UTC)
    choque = db.scalar(
        select(BloqueoHorario.id)
        .where(
            BloqueoHorario.unidad_id == unidad_id,
            _vigente(ahora),
            BloqueoHorario.rango.op("&&")(_rango(inicio, fin)),
        )
        .limit(1)
    )
    return choque is None


def ocupados(
    db: Session, unidad_id, desde: datetime, hasta: datetime, ahora: datetime | None = None
) -> list[Ocupado]:
    """Lo ocupado entre `desde` y `hasta`, en orden. Alimenta el calendario del día."""
    ahora = ahora or datetime.now(UTC)
    filas = db.scalars(
        select(BloqueoHorario)
        .where(
            BloqueoHorario.unidad_id == unidad_id,
            _vigente(ahora),
            BloqueoHorario.rango.op("&&")(_rango(desde, hasta)),
        )
        .order_by(func.lower(BloqueoHorario.rango))
    ).all()
    return [Ocupado(b.rango.lower, b.rango.upper, b.origen) for b in filas]


def bloquear(
    db: Session,
    unidad: Unidad,
    inicio: datetime,
    fin: datetime,
    origen: OrigenBloqueo,
    vence_en: datetime | None = None,
    nota: str | None = None,
    ahora: datetime | None = None,
) -> BloqueoHorario:
    """Toma el rango, o levanta `HorarioOcupado` si otro ya lo tiene.

    Las retenciones vencidas siguen activas hasta que la tarea periódica las
    suelta; acá se sueltan las que estorban, para que un pago abandonado no
    trabe a quien llega después.
    """
    _validar(unidad, inicio, fin)
    ahora = ahora or datetime.now(UTC)

    db.execute(
        update(BloqueoHorario)
        .where(
            BloqueoHorario.unidad_id == unidad.id,
            BloqueoHorario.activo.is_(True),
            BloqueoHorario.vence_en.is_not(None),
            BloqueoHorario.vence_en <= ahora,
            BloqueoHorario.rango.op("&&")(_rango(inicio, fin)),
        )
        .values(activo=False)
        .execution_options(synchronize_session=False)
    )

    bloqueo = BloqueoHorario(
        unidad_id=unidad.id,
        rango=Range(inicio, fin, bounds="[)"),
        origen=origen,
        activo=True,
        vence_en=vence_en,
        nota=nota,
    )
    # Un savepoint: si la base rechaza el rango, la transacción del que llama sigue viva.
    try:
        with db.begin_nested():
            db.add(bloqueo)
            db.flush()
    except IntegrityError as e:
        raise HorarioOcupado("Ese horario ya está ocupado") from e
    return bloqueo


def soltar_vencidos(db: Session, ahora: datetime | None = None) -> int:
    """Desactiva las retenciones vencidas. Para la tarea periódica."""
    ahora = ahora or datetime.now(UTC)
    resultado = db.execute(
        update(BloqueoHorario)
        .where(
            BloqueoHorario.activo.is_(True),
            BloqueoHorario.vence_en.is_not(None),
            BloqueoHorario.vence_en <= ahora,
        )
        .values(activo=False)
        .execution_options(synchronize_session=False)
    )
    return resultado.rowcount or 0
