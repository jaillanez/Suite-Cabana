"""Excursiones para el viajero: buscar, ver la ficha, saber cuándo sale (docs/05, etapa 4).

"Hay lugar" en la búsqueda sale de la misma fuente que la reserva
(`salidas.salidas`), así que la búsqueda y la reserva no se contradicen por una
regla distinta; a lo sumo, por alguien que se adelantó entre una cosa y la otra.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Comodidad,
    Localidad,
    PrecioPasajero,
    Provincia,
    Publicacion,
    SubtipoServicio,
    Unidad,
    publicacion_comodidad,
)
from app.models.enums import EstadoPublicacion, ModoReserva
from app.services import salidas, tipos

POR_PAGINA_MAX = 48
TOPE_CANDIDATAS = 500
#: Con fecha hay que mirar las salidas de cada candidata: el tope es más bajo.
TOPE_CANDIDATAS_CON_FECHA = 200
#: Hasta dónde se busca la próxima salida para mostrarla en la tarjeta.
DIAS_PROXIMA_SALIDA = 60


class NoEncontrada(Exception):
    pass


@dataclass(frozen=True)
class PrecioDesde:
    monto: Decimal
    detalle: str  # "por persona"


@dataclass
class Resultado:
    publicacion: Publicacion
    maximo_por_reserva: int
    precio_desde: PrecioDesde | None
    proxima_salida: salidas.Salida | None
    salidas_del_dia: list[salidas.Salida]


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
        selectinload(Publicacion.zona),
        selectinload(Publicacion.localidad).selectinload(Localidad.provincia),
        selectinload(Publicacion.unidades).selectinload(Unidad.publicacion),
    )


def _publicadas():
    return select(Publicacion).where(
        Publicacion.estado == EstadoPublicacion.APROBADA, tipos.de_modo(ModoReserva.TURNO_CUPO)
    )


def precios_de(db: Session, unidades: list[Unidad]) -> dict[UUID, list[PrecioPasajero]]:
    """Los precios activos de cada actividad, en el orden del prestador."""
    if not unidades:
        return {}
    filas = db.scalars(
        select(PrecioPasajero)
        .where(
            PrecioPasajero.unidad_id.in_([u.id for u in unidades]),
            PrecioPasajero.activo.is_(True),
        )
        .order_by(PrecioPasajero.orden, PrecioPasajero.nombre)
    )
    por_unidad: dict[UUID, list[PrecioPasajero]] = {}
    for p in filas:
        por_unidad.setdefault(p.unidad_id, []).append(p)
    return por_unidad


def actividades(
    p: Publicacion, precios: dict[UUID, list[PrecioPasajero]], personas: int = 1
) -> list[Unidad]:
    """Las actividades que se pueden reservar (tienen precios) para esa cantidad."""
    return [
        u
        for u in sorted(p.unidades, key=lambda x: x.nombre)
        if u.activa and u.capacidad >= personas and precios.get(u.id)
    ]


def precio_desde(
    unidades: list[Unidad], precios: dict[UUID, list[PrecioPasajero]]
) -> PrecioDesde | None:
    """El "desde" de la tarjeta: en cada actividad, el primer precio que cargó el
    prestador entre quienes ocupan lugar y pagan (suele ser el adulto); entre
    actividades, el más bajo.

    No es el más barato de todos: un menor a mitad de precio no es el precio de la
    excursión. Si en una actividad todos van gratis, es gratis.
    """
    montos = []
    for u in unidades:
        ocupan = [c for c in precios.get(u.id, []) if c.ocupa_lugar]
        pagan = [c for c in ocupan if c.precio > 0]
        if pagan:
            montos.append(pagan[0].precio)
        elif ocupan:
            montos.append(Decimal(0))
    return PrecioDesde(min(montos), "por persona") if montos else None


def _salidas(db: Session, u: Unidad, desde: date, hasta: date, personas: int) -> list:
    return [s for s in salidas.salidas(db, u, desde, hasta) if s.libres >= personas]


def buscar(
    db: Session,
    localidad: str | None = None,
    provincia: str | None = None,
    fecha: date | None = None,
    personas: int = 1,
    subtipos: tuple[str, ...] = (),
    comodidades: tuple[str, ...] = (),
    pagina: int = 1,
    por_pagina: int = 24,
) -> Pagina:
    consulta = _publicadas().join(Localidad, Publicacion.localidad_id == Localidad.id)
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

    tope = TOPE_CANDIDATAS if fecha is None else TOPE_CANDIDATAS_CON_FECHA
    candidatas = db.scalars(
        consulta.options(*_opciones()).order_by(Publicacion.titulo).limit(tope)
    ).unique().all()
    precios = precios_de(db, [u for p in candidatas for u in p.unidades])

    resultados: list[Resultado] = []
    for p in candidatas:
        utiles = actividades(p, precios, personas)
        if not utiles:
            continue
        del_dia: list[salidas.Salida] = []
        if fecha is not None:
            del_dia = sorted(
                (s for u in utiles for s in _salidas(db, u, fecha, fecha, personas)),
                key=lambda s: s.inicio,
            )
            if not del_dia:
                continue  # con fecha, solo lo que sale ese día con lugar
        resultados.append(
            Resultado(
                publicacion=p,
                maximo_por_reserva=max(u.capacidad for u in utiles),
                precio_desde=precio_desde(utiles, precios),
                proxima_salida=del_dia[0] if del_dia else None,
                salidas_del_dia=del_dia,
            )
        )

    # Primero lo que tiene foto: una tarjeta vacía arriba es la peor primera impresión.
    resultados.sort(key=lambda r: (not r.publicacion.fotos, r.publicacion.titulo))
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAX))
    paginas = max(1, math.ceil(len(resultados) / por_pagina))
    pagina = max(1, min(pagina, paginas))
    inicio = (pagina - 1) * por_pagina
    visibles = resultados[inicio : inicio + por_pagina]

    # Sin fecha, la próxima salida se busca solo para lo que se muestra.
    if fecha is None:
        hoy = salidas.hoy()
        for r in visibles:
            proximas = sorted(
                (
                    s
                    for u in actividades(r.publicacion, precios, personas)
                    for s in _salidas(
                        db, u, hoy, hoy + timedelta(days=DIAS_PROXIMA_SALIDA), personas
                    )
                ),
                key=lambda s: s.inicio,
            )
            r.proxima_salida = proximas[0] if proximas else None

    return Pagina(total=len(resultados), pagina=pagina, paginas=paginas, resultados=visibles)


def obtener(db: Session, slug: str) -> Publicacion:
    p = db.scalar(_publicadas().where(Publicacion.slug == slug).options(*_opciones()))
    if p is None:
        raise NoEncontrada(slug)
    return p


def destinos(db: Session) -> list[tuple[Localidad, Provincia, int]]:
    """Localidades con excursiones publicadas, para el buscador."""
    cuenta = (
        select(func.count(Publicacion.id))
        .where(
            Publicacion.localidad_id == Localidad.id,
            Publicacion.estado == EstadoPublicacion.APROBADA,
            tipos.de_modo(ModoReserva.TURNO_CUPO),
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


def en_localidad(db: Session, localidad_id: UUID, limite: int = 6) -> list[Publicacion]:
    """Excursiones publicadas en una localidad: lo que se ofrece en la ficha de un
    alojamiento de la zona (docs/02 §10, venta cruzada)."""
    return list(
        db.scalars(
            _publicadas()
            .where(Publicacion.localidad_id == localidad_id)
            .order_by(Publicacion.titulo)
            .limit(limite)
        )
    )
