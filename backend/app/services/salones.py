"""Salones para el viajero: buscar, ver la ficha, saber si hay lugar (docs/04 §5 S9-S10).

La disponibilidad de un día se responde con la misma fuente de verdad que la
reserva (`horarios`), así que "hay lugar" en la búsqueda y "se pudo reservar"
nunca se contradicen por una regla distinta; a lo sumo, por alguien que se
adelantó entre una cosa y la otra.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Comodidad,
    Localidad,
    Provincia,
    Publicacion,
    SubtipoServicio,
    Unidad,
    publicacion_comodidad,
)
from app.models.enums import EstadoPublicacion, ModoReserva
from app.services import horarios, reservas, tipos
from app.services import precios_eventos as pe

POR_PAGINA_MAX = 48
TOPE_CANDIDATAS = 500


class NoEncontrado(Exception):
    pass


@dataclass(frozen=True)
class PrecioDesde:
    monto: Decimal
    detalle: str  # "por turno", "por 3 h"


@dataclass
class Resultado:
    publicacion: Publicacion
    capacidad_maxima: int
    sentados_maximo: int | None
    precio_desde: PrecioDesde | None
    disponible: bool | None  # None: no se pidió día


@dataclass
class Pagina:
    total: int
    pagina: int
    paginas: int
    resultados: list[Resultado]


def _opciones():
    return (
        selectinload(Publicacion.fotos),
        selectinload(Publicacion.comodidades),
        selectinload(Publicacion.subtipo),
        selectinload(Publicacion.prestador),
        selectinload(Publicacion.tipo_servicio),
        selectinload(Publicacion.politica_cancelacion),
        selectinload(Publicacion.localidad).selectinload(Localidad.provincia),
        selectinload(Publicacion.unidades).selectinload(Unidad.franjas),
        selectinload(Publicacion.unidades).selectinload(Unidad.tarifa_horaria),
        selectinload(Publicacion.unidades).selectinload(Unidad.adicionales),
    )


def _publicados():
    return select(Publicacion).where(
        Publicacion.estado == EstadoPublicacion.APROBADA, tipos.de_modo(ModoReserva.HORAS)
    )


def espacios(p: Publicacion, invitados: int = 1) -> list[Unidad]:
    """Los espacios que se pueden reservar y alcanzan para esa cantidad."""
    return [
        u
        for u in sorted(p.unidades, key=lambda x: (-x.capacidad, x.nombre))
        if u.activa and u.capacidad >= invitados
        and (any(f.activa for f in u.franjas) or reservas.tarifa_horas(u) is not None)
    ]


def precio_desde(unidades: list[Unidad], dia: date | None) -> PrecioDesde | None:
    """El precio más bajo para empezar a hablar: el turno más barato o el mínimo de horas."""
    opciones: list[PrecioDesde] = []
    for u in unidades:
        for f in u.franjas:
            if f.activa:
                monto = (
                    pe.precio_del_dia(f.precio, f.precios_dia_semana, dia) if dia else f.precio
                )
                opciones.append(PrecioDesde(monto, "por turno"))
        t = reservas.tarifa_horas(u)
        if t:
            hora = (
                pe.precio_del_dia(t.precio_hora, t.precios_dia_semana, dia)
                if dia
                else t.precio_hora
            )
            opciones.append(PrecioDesde(hora * t.horas_minimas, f"por {t.horas_minimas} h"))
    return min(opciones, key=lambda o: o.monto) if opciones else None


def hay_lugar(db: Session, unidad: Unidad, dia: date, ahora: datetime | None = None) -> bool:
    """Si ese día se puede reservar algo de este espacio: un turno libre, o un hueco
    del mínimo de horas dentro del horario de atención."""
    ahora = ahora or datetime.now(UTC)
    preparacion = timedelta(minutes=unidad.preparacion_minutos or 0)

    for f in unidad.franjas:
        if not f.activa:
            continue
        inicio, fin = reservas.franja_plana(f).rango(dia)
        if inicio > ahora and horarios.libre(db, unidad.id, inicio, fin + preparacion):
            return True

    t = reservas.tarifa_horas(unidad)
    if t is None:
        return False
    apertura, cierre = t.atencion(dia)
    minimo = timedelta(hours=t.horas_minimas)
    # Desde ahora, redondeado a la media hora siguiente: no se reserva el pasado.
    if ahora > apertura:
        media = timedelta(minutes=30)
        apertura = max(apertura, apertura + math.ceil((ahora - apertura) / media) * media)
    if cierre - apertura < minimo:
        return False

    cursor = apertura
    for o in horarios.ocupados(db, unidad.id, apertura - preparacion, cierre):
        if o.inicio > cursor and o.inicio - cursor >= minimo + preparacion:
            return True
        cursor = max(cursor, o.fin)
    return cierre - cursor >= minimo


def buscar(
    db: Session,
    localidad: str | None = None,
    provincia: str | None = None,
    dia: date | None = None,
    invitados: int = 1,
    subtipos: tuple[str, ...] = (),
    comodidades: tuple[str, ...] = (),
    pagina: int = 1,
    por_pagina: int = 24,
) -> Pagina:
    consulta = _publicados().join(Localidad, Publicacion.localidad_id == Localidad.id)
    if localidad:
        consulta = consulta.where(Localidad.slug == localidad)
    elif provincia:
        consulta = consulta.join(Provincia, Localidad.provincia_id == Provincia.id).where(
            Provincia.slug == provincia
        )
    if subtipos:
        consulta = consulta.join(
            SubtipoServicio, Publicacion.subtipo_servicio_id == SubtipoServicio.id
        ).where(SubtipoServicio.codigo.in_(subtipos))
    if comodidades:
        pedidas = set(comodidades)
        tiene = (
            select(func.count())
            .select_from(publicacion_comodidad)
            .join(Comodidad, Comodidad.id == publicacion_comodidad.c.comodidad_id)
            .where(
                publicacion_comodidad.c.publicacion_id == Publicacion.id,
                Comodidad.codigo.in_(pedidas),
            )
            .scalar_subquery()
        )
        consulta = consulta.where(tiene == len(pedidas))

    candidatas = db.scalars(
        consulta.options(*_opciones()).order_by(Publicacion.titulo).limit(TOPE_CANDIDATAS)
    ).unique().all()

    resultados: list[Resultado] = []
    for p in candidatas:
        utiles = espacios(p, invitados)
        if not utiles:
            continue
        disponible = None
        if dia is not None:
            disponible = any(hay_lugar(db, u, dia) for u in utiles)
            if not disponible:
                continue  # con día, se muestra solo lo que se puede reservar ese día
        resultados.append(
            Resultado(
                publicacion=p,
                capacidad_maxima=max(u.capacidad for u in utiles),
                sentados_maximo=max(
                    (u.capacidad_sentados for u in utiles if u.capacidad_sentados), default=None
                ),
                precio_desde=precio_desde(utiles, dia),
                disponible=disponible,
            )
        )

    # Primero lo que tiene foto: una tarjeta vacía arriba es la peor primera impresión.
    resultados.sort(key=lambda r: (not r.publicacion.fotos, r.publicacion.titulo))
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAX))
    paginas = max(1, math.ceil(len(resultados) / por_pagina))
    pagina = max(1, min(pagina, paginas))
    inicio = (pagina - 1) * por_pagina
    return Pagina(
        total=len(resultados),
        pagina=pagina,
        paginas=paginas,
        resultados=resultados[inicio : inicio + por_pagina],
    )


def obtener(db: Session, slug: str) -> Publicacion:
    p = db.scalar(_publicados().where(Publicacion.slug == slug).options(*_opciones()))
    if p is None:
        raise NoEncontrado(slug)
    return p


def destinos(db: Session) -> list[tuple[Localidad, Provincia, int]]:
    """Localidades con salones publicados, para el buscador."""
    cuenta = (
        select(func.count(Publicacion.id))
        .where(
            Publicacion.localidad_id == Localidad.id,
            Publicacion.estado == EstadoPublicacion.APROBADA,
            tipos.de_modo(ModoReserva.HORAS),
        )
        .scalar_subquery()
    )
    return [
        (loc, prov, n)
        for loc, prov, n in db.execute(
            select(Localidad, Provincia, cuenta)
            .join(Provincia, Localidad.provincia_id == Provincia.id)
            .order_by(Provincia.nombre, Localidad.nombre)
        ).all()
        if n
    ]


def del_mismo_anfitrion(
    db: Session, prestador_id: UUID, modo: ModoReserva, excluir: UUID | None = None
) -> list[Publicacion]:
    """Lo que el mismo anfitrión publica del otro tipo: "también tiene salón"."""
    consulta = select(Publicacion).where(
        Publicacion.prestador_id == prestador_id,
        Publicacion.estado == EstadoPublicacion.APROBADA,
        tipos.de_modo(modo),
    )
    if excluir:
        consulta = consulta.where(Publicacion.id != excluir)
    return list(db.scalars(consulta.order_by(Publicacion.titulo).limit(6)))
