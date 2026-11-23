"""Disponibilidad de una unidad: bloqueos propios y calendarios ajenos (docs/01 §5 R3).

Reglas que sostienen "cero dobles reservas":

- Dos bloqueos activos de la misma unidad no pueden superponerse. Lo garantiza una
  restricción de exclusión en la base, no este código: acá se evita el choque para
  poder dar un mensaje, pero la última palabra la tiene Postgres.
- Un calendario externo nunca pisa una reserva o un bloqueo manual propio. Se
  importa solo lo que queda libre, y lo que se pisa se informa.
- Sincronizar reemplaza lo que ese calendario había traído antes: si en Booking
  cancelaron, acá la fecha se libera.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from app.models import BloqueoFecha, CalendarioExterno, Unidad
from app.models.enums import OrigenBloqueo
from app.services import ical, red

TIEMPO_LIMITE = 20.0
# Sincronización automática (app.tareas): cada calendario, una vez por hora. Por
# pasada se toman pocos, los más atrasados primero: cada descarga puede tardar
# hasta TIEMPO_LIMITE y la misma pasada libera las reservas vencidas.
CADA = timedelta(hours=1)
LOTE = 10
registro = logging.getLogger("calendario")
# Las cabeceras HTTP son ASCII: una tilde acá rompe cada sincronización.
AGENTE = "SuiteCabana/0.1 (calendar sync)"

ETIQUETAS = {
    OrigenBloqueo.MANUAL: "Bloqueada por vos",
    OrigenBloqueo.ICAL: "Ocupada en otra plataforma",
    OrigenBloqueo.RESERVA: "Reservada acá",
    OrigenBloqueo.RETENCION: "Alguien está pagando",
    OrigenBloqueo.EXTERNA: "Vendida por fuera",
}


class RangoInvalido(Exception):
    """La salida no es posterior a la llegada."""


class FechasOcupadas(Exception):
    """Ya hay algo en esas fechas."""


@dataclass(frozen=True)
class Tramo:
    id: uuid.UUID
    desde: date
    hasta: date
    origen: OrigenBloqueo
    etiqueta: str
    nota: str | None
    calendario: str | None


def rango(desde: date, hasta: date) -> Range[date]:
    """Rango de noches con extremos explícitos `[desde, hasta)`.

    Sin los extremos, psycopg arma `(desde, hasta)` —ambos exclusivos— y Postgres
    normaliza el rango discreto corriendo el inicio un día. En un sistema de
    reservas, una fecha que se corre sola es exactamente el error que no puede pasar.
    """
    return Range(desde, hasta, bounds="[)")


def limites(bloqueo: BloqueoFecha) -> tuple[date, date]:
    """Los extremos del bloqueo, ya esté recién creado o leído de la base."""
    valor = bloqueo.rango
    if isinstance(valor, tuple):
        return valor[0], valor[1]
    return valor.lower, valor.upper


def _activos(unidad_id: uuid.UUID, excluir_calendario: uuid.UUID | None = None):
    condiciones = [
        BloqueoFecha.unidad_id == unidad_id,
        BloqueoFecha.activo.is_(True),
        or_(BloqueoFecha.vence_en.is_(None), BloqueoFecha.vence_en > datetime.now()),
    ]
    if excluir_calendario is not None:
        condiciones.append(
            or_(
                BloqueoFecha.calendario_externo_id.is_(None),
                BloqueoFecha.calendario_externo_id != excluir_calendario,
            )
        )
    return select(BloqueoFecha).where(*condiciones)


def ocupacion(db: Session, unidad_id: uuid.UUID) -> list[Tramo]:
    """Todo lo que tiene tomada la unidad, para mostrarlo en el calendario."""
    nombres = {
        c.id: c.nombre for c in db.scalars(select(CalendarioExterno).where(
            CalendarioExterno.unidad_id == unidad_id
        ))
    }
    tramos = []
    for b in db.scalars(_activos(unidad_id).order_by(BloqueoFecha.rango)):
        desde, hasta = limites(b)
        tramos.append(
            Tramo(
                id=b.id,
                desde=desde,
                hasta=hasta,
                origen=b.origen,
                etiqueta=ETIQUETAS.get(b.origen, "Ocupada"),
                nota=b.nota,
                calendario=nombres.get(b.calendario_externo_id),
            )
        )
    return tramos


def bloquear(
    db: Session, unidad_id: uuid.UUID, desde: date, hasta: date, nota: str | None = None
) -> BloqueoFecha:
    """Bloqueo manual: el prestador se guarda esas noches."""
    if hasta <= desde:
        raise RangoInvalido("La salida tiene que ser posterior a la llegada")
    for b in db.scalars(_activos(unidad_id)):
        ini, fin = limites(b)
        if ini < hasta and desde < fin:
            raise FechasOcupadas(
                f"Esas fechas ya están tomadas ({ETIQUETAS.get(b.origen, 'ocupadas').lower()})"
            )
    bloqueo = BloqueoFecha(
        unidad_id=unidad_id,
        rango=rango(desde, hasta),
        origen=OrigenBloqueo.MANUAL,
        activo=True,
        nota=(nota or "").strip() or None,
    )
    db.add(bloqueo)
    db.flush()
    return bloqueo


def desbloquear(db: Session, unidad_id: uuid.UUID, bloqueo_id: uuid.UUID) -> bool:
    """Solo se sueltan los bloqueos manuales: los otros los maneja su fuente."""
    bloqueo = db.scalar(
        select(BloqueoFecha).where(
            BloqueoFecha.id == bloqueo_id,
            BloqueoFecha.unidad_id == unidad_id,
            BloqueoFecha.origen == OrigenBloqueo.MANUAL,
        )
    )
    if bloqueo is None:
        return False
    db.delete(bloqueo)
    db.flush()
    return True


@dataclass(frozen=True)
class ResultadoSincronizacion:
    importados: int
    descartados: int
    detalle: str


def motivo(e: Exception) -> str:
    """Traduce la falla a algo accionable.

    Al anfitrión no le sirve `HTTPStatusError`: le sirve saber si la dirección se
    le venció —y tiene que sacarla de nuevo— o si el portal está caído y hay que
    esperar. Son dos acciones distintas.
    """
    if isinstance(e, red.DireccionNoPermitida):
        return f"{e}. Pegá la dirección que da la plataforma."
    if isinstance(e, httpx.HTTPStatusError):
        codigo = e.response.status_code
        if codigo in (401, 403):
            return (
                "La plataforma rechazó la dirección. Suele pasar cuando caduca: "
                "sacala de nuevo desde su panel y volvé a pegarla."
            )
        if codigo == 404:
            return (
                "Esa dirección ya no existe en la plataforma. Sacá una nueva "
                "desde su panel."
            )
        return f"La plataforma respondió con un error ({codigo}). Probá más tarde."
    if isinstance(e, httpx.TimeoutException):
        return "La plataforma tardó demasiado en responder. Probá de nuevo en un rato."
    if isinstance(e, httpx.TransportError):
        return "No pudimos conectarnos. Revisá que la dirección esté bien escrita."
    return "No pudimos traer el calendario. Probá de nuevo en un rato."


def descargar(url: str) -> bytes:
    """Trae el calendario. Solo de internet pública: la URL la pegó un usuario."""
    return red.descargar_publica(url, agente=AGENTE, tiempo=TIEMPO_LIMITE)


def sincronizar(
    db: Session, calendario: CalendarioExterno, contenido: bytes | None = None
) -> ResultadoSincronizacion:
    """Trae el calendario externo y reemplaza lo que ese calendario había traído.

    `contenido` existe para los tests: en producción se descarga de la URL.
    """
    calendario.ultimo_intento = datetime.now(UTC)
    if contenido is None:
        try:
            contenido = descargar(calendario.url)
        except Exception as e:  # noqa: BLE001 - httpx levanta varias familias
            calendario.ultimo_error = motivo(e)
            db.flush()
            raise

    try:
        ocupaciones = ical.parsear(contenido)
    except ical.CalendarioIlegible as e:
        calendario.ultimo_error = f"El archivo no se entiende: {e}"
        db.flush()
        raise

    # Lo que este calendario había traído antes se va: si allá cancelaron, acá
    # la fecha tiene que quedar libre.
    db.execute(
        delete(BloqueoFecha).where(BloqueoFecha.calendario_externo_id == calendario.id)
    )
    db.flush()

    ajenos = [
        limites(b)
        for b in db.scalars(_activos(calendario.unidad_id, excluir_calendario=calendario.id))
    ]
    libres = ical.restar(ocupaciones, ajenos)

    for tramo in libres:
        db.add(
            BloqueoFecha(
                unidad_id=calendario.unidad_id,
                rango=rango(tramo.desde, tramo.hasta),
                origen=OrigenBloqueo.ICAL,
                activo=True,
                calendario_externo_id=calendario.id,
                nota=tramo.resumen[:200],
            )
        )

    descartados = len(ocupaciones) - len(libres)
    calendario.ultima_sincronizacion = calendario.ultimo_intento
    calendario.ultimo_error = None
    db.flush()

    detalle = f"{len(libres)} tramos importados"
    if descartados > 0:
        detalle += (
            f"; {descartados} se pisaban con reservas o bloqueos propios y no se tocaron"
        )
    return ResultadoSincronizacion(
        importados=len(libres), descartados=descartados, detalle=detalle
    )


def sincronizar_vencidos(
    db: Session, ahora: datetime | None = None, lote: int = LOTE
) -> dict[str, int]:
    """Vuelve a traer los calendarios que llevan una hora o más sin intentarse.

    Cada uno en su propio savepoint: uno caído o con la dirección vencida deja su
    motivo en `ultimo_error` (lo ve el anfitrión) y no frena a los demás. Si dos
    procesos corrieran a la vez, `skip_locked` evita que tomen el mismo.
    """
    ahora = ahora or datetime.now(UTC)
    pendientes = list(
        db.scalars(
            select(CalendarioExterno)
            .join(Unidad, Unidad.id == CalendarioExterno.unidad_id)
            .where(
                Unidad.activa.is_(True),
                or_(
                    CalendarioExterno.ultimo_intento.is_(None),
                    CalendarioExterno.ultimo_intento <= ahora - CADA,
                ),
            )
            .order_by(CalendarioExterno.ultimo_intento.asc().nulls_first())
            .limit(lote)
            .with_for_update(of=CalendarioExterno, skip_locked=True)
        )
    )
    bien = mal = 0
    for calendario in pendientes:
        try:
            with db.begin_nested():
                sincronizar(db, calendario)
            bien += 1
        except Exception as e:  # noqa: BLE001 - red, formato o choque en la base
            mal += 1
            # El savepoint se deshizo, con el intento y el motivo adentro: se
            # vuelven a anotar afuera para que no se reintente cada minuto.
            calendario.ultimo_intento = datetime.now(UTC)
            calendario.ultimo_error = (
                f"El archivo no se entiende: {e}"
                if isinstance(e, ical.CalendarioIlegible)
                else motivo(e)
            )
            registro.warning("calendario %s: %s", calendario.id, calendario.ultimo_error)
    db.flush()
    return {"calendarios_al_dia": bien, "calendarios_con_error": mal}


def exportar(db: Session, unidad: Unidad) -> bytes:
    """El calendario público de la unidad, para pegar en Booking o Airbnb."""
    tramos = [
        ical.Ocupacion(
            desde=t.desde,
            hasta=t.hasta,
            resumen=t.etiqueta,
            uid=f"{t.id}@suite-cabana",
        )
        for t in ocupacion(db, unidad.id)
        # Lo que trajo otra plataforma no se le devuelve: sería un eco.
        if t.origen is not OrigenBloqueo.ICAL
    ]
    nombre = f"{unidad.publicacion.titulo} · {unidad.nombre}"
    return ical.generar(nombre, tramos, str(unidad.ical_export_token))
