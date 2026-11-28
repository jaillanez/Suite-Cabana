"""Traslados para el viajero: buscar, ver la ficha y comparar vehículos para un
viaje (docs/06, etapa 4).

La búsqueda no puede decir si un vehículo está libre: cuánto lo ocupa un viaje
depende del recorrido (la duración, la vuelta a la base). Eso se responde en la
ficha, con el viaje armado (`opciones`), y sale de la misma cuenta que la reserva
(`reservas_traslado.cotizar_traslado` y `horarios.libre`): lo que se ofrece como
libre es lo que se puede reservar, salvo que alguien se adelante.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.models import (
    Comodidad,
    Localidad,
    LugarTraslado,
    Provincia,
    Publicacion,
    SubtipoServicio,
    TarifaTraslado,
    TramoTraslado,
    Unidad,
    publicacion_comodidad,
)
from app.models.enums import EstadoPublicacion, ModoReserva
from app.services import horarios, reservas, tipos
from app.services import reservas_traslado as rt

POR_PAGINA_MAX = 48
TOPE_CANDIDATAS = 500
#: Vehículos que se cotizan por pedido de opciones: más que esto es una flota que
#: necesita su propio buscador, y la cuenta por vehículo es cara.
MAX_VEHICULOS_OPCIONES = 20


class NoEncontrado(Exception):
    pass


@dataclass(frozen=True)
class Recorrido:
    origen: str
    destino: str
    precio: Decimal
    por_persona: bool
    duracion_minutos: int
    ambos_sentidos: bool


@dataclass
class Vehiculo:
    unidad: Unidad
    recorridos: list[Recorrido] = field(default_factory=list)
    tarifa: TarifaTraslado | None = None

    @property
    def por_km(self) -> bool:
        return self.tarifa is not None and self.tarifa.precio_km is not None


@dataclass(frozen=True)
class PrecioDesde:
    monto: Decimal
    detalle: str  # "por viaje", "por persona", "por viaje (mínimo)"


@dataclass
class Resultado:
    publicacion: Publicacion
    vehiculos: list[Vehiculo]
    precio_desde: PrecioDesde | None

    @property
    def pasajeros_maximo(self) -> int:
        return max(v.unidad.capacidad for v in self.vehiculos)

    @property
    def valijas_maximo(self) -> int | None:
        """None: algún vehículo no tiene límite."""
        valijas = [v.unidad.equipaje for v in self.vehiculos]
        return None if any(x is None for x in valijas) else max(valijas)


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


def _publicados():
    return select(Publicacion).where(
        Publicacion.estado == EstadoPublicacion.APROBADA, tipos.de_modo(ModoReserva.TRAMO)
    )


def vehiculos_de(db: Session, publicaciones: list[Publicacion]) -> dict[UUID, list[Vehiculo]]:
    """Los vehículos que se pueden reservar de cada publicación —activos y con una
    forma de cobrar—, con sus recorridos y su tarifa. Tres consultas en total, sean
    cuantas sean las publicaciones: la búsqueda es pública."""
    unidades = [u for p in publicaciones for u in p.unidades if u.activa]
    if not unidades:
        return {}
    ids = [u.id for u in unidades]
    origen, destino = aliased(LugarTraslado), aliased(LugarTraslado)
    tramos: dict[UUID, list[Recorrido]] = {}
    for t, o, d in db.execute(
        select(TramoTraslado, origen.nombre, destino.nombre)
        .join(origen, TramoTraslado.origen_id == origen.id)
        .join(destino, TramoTraslado.destino_id == destino.id)
        .where(
            TramoTraslado.unidad_id.in_(ids),
            TramoTraslado.activo.is_(True),
            origen.activo.is_(True),
            destino.activo.is_(True),
        )
        .order_by(origen.nombre, destino.nombre)
    ).all():
        tramos.setdefault(t.unidad_id, []).append(
            Recorrido(o, d, t.precio, t.por_persona, t.duracion_minutos, t.ambos_sentidos)
        )
    tarifas = {
        t.unidad_id: t
        for t in db.scalars(select(TarifaTraslado).where(TarifaTraslado.unidad_id.in_(ids)))
    }
    resultado: dict[UUID, list[Vehiculo]] = {}
    for u in sorted(unidades, key=lambda x: (x.capacidad, x.nombre)):
        v = Vehiculo(u, tramos.get(u.id, []), tarifas.get(u.id))
        if v.recorridos or v.por_km:
            resultado.setdefault(u.publicacion_id, []).append(v)
    return resultado


def precio_desde(vehiculos: list[Vehiculo]) -> PrecioDesde | None:
    """El "desde" de la tarjeta: el recorrido fijo más barato (por viaje o por
    persona) o, si no hay, el mínimo de la tarifa por km. Sin mínimo cargado, no se
    inventa un número: no hay "desde"."""
    opciones: list[PrecioDesde] = []
    for v in vehiculos:
        for r in v.recorridos:
            opciones.append(PrecioDesde(r.precio, "por persona" if r.por_persona else "por viaje"))
    if not opciones:
        for v in vehiculos:
            if v.por_km and v.tarifa.minimo > 0:
                opciones.append(PrecioDesde(v.tarifa.minimo, "por viaje (mínimo)"))
    return min(opciones, key=lambda o: o.monto) if opciones else None


def buscar(
    db: Session,
    localidad: str | None = None,
    provincia: str | None = None,
    pasajeros: int = 1,
    valijas: int = 0,
    lugar: str | None = None,
    subtipos: tuple[str, ...] = (),
    comodidades: tuple[str, ...] = (),
    pagina: int = 1,
    por_pagina: int = 24,
) -> Pagina:
    """Traslados de un destino con un vehículo donde entran los pasajeros y las
    valijas. `lugar`: que tenga un lugar con ese nombre ("aeropuerto")."""
    consulta = _publicados().join(Localidad, Publicacion.localidad_id == Localidad.id)
    if localidad:
        consulta = consulta.where(Localidad.slug == localidad)
    elif provincia:
        consulta = consulta.join(Provincia, Localidad.provincia_id == Provincia.id).where(
            Provincia.slug == provincia
        )
    if lugar and lugar.strip():
        # Escapado: un "%" o un "_" del viajero se buscan como texto, no como comodín.
        texto = lugar.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        consulta = consulta.where(
            select(LugarTraslado.id)
            .where(
                LugarTraslado.publicacion_id == Publicacion.id,
                LugarTraslado.activo.is_(True),
                LugarTraslado.nombre.ilike(f"%{texto}%", escape="\\"),
            )
            .exists()
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
    de = vehiculos_de(db, list(candidatas))

    resultados: list[Resultado] = []
    for p in candidatas:
        entran = [
            v
            for v in de.get(p.id, [])
            if v.unidad.capacidad >= pasajeros
            and (v.unidad.equipaje is None or v.unidad.equipaje >= valijas)
        ]
        if entran:
            resultados.append(Resultado(p, entran, precio_desde(entran)))

    # Primero lo que tiene foto: una tarjeta vacía arriba es la peor primera impresión.
    resultados.sort(key=lambda r: (not r.publicacion.fotos, r.publicacion.titulo))
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAX))
    paginas = max(1, math.ceil(len(resultados) / por_pagina))
    pagina = max(1, min(pagina, paginas))
    inicio = (pagina - 1) * por_pagina
    return Pagina(
        total=len(resultados), pagina=pagina, paginas=paginas,
        resultados=resultados[inicio : inicio + por_pagina],
    )


def obtener(db: Session, slug: str) -> Publicacion:
    p = db.scalar(_publicados().where(Publicacion.slug == slug).options(*_opciones()))
    if p is None:
        raise NoEncontrado(slug)
    return p


def lugares(db: Session, p: Publicacion) -> list[LugarTraslado]:
    return list(
        db.scalars(
            select(LugarTraslado)
            .where(LugarTraslado.publicacion_id == p.id, LugarTraslado.activo.is_(True))
            .order_by(LugarTraslado.nombre)
        )
    )


def destinos(db: Session) -> list[tuple[Localidad, Provincia, int]]:
    """Localidades con traslados publicados, para el buscador."""
    cuenta = (
        select(func.count(Publicacion.id))
        .where(
            Publicacion.localidad_id == Localidad.id,
            Publicacion.estado == EstadoPublicacion.APROBADA,
            tipos.de_modo(ModoReserva.TRAMO),
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
    """Traslados publicados en una localidad: lo que se ofrece desde un alojamiento
    de la zona ("¿Te buscamos en el aeropuerto?")."""
    return list(
        db.scalars(
            _publicados()
            .where(Publicacion.localidad_id == localidad_id)
            .order_by(Publicacion.titulo)
            .limit(limite)
        )
    )


# --- Comparar vehículos para un viaje ---


@dataclass
class Opcion:
    vehiculo: Unidad
    cotizacion: rt.CotizacionTraslado | None
    disponible: bool
    motivo: str | None = None


def opciones(
    db: Session, p: Publicacion, pedido: rt.Pedido, ahora: datetime | None = None
) -> list[Opcion]:
    """Cada vehículo del prestador para ese viaje: cuánto sale y si está libre, o por
    qué no se puede (no entran, no hace ese recorrido, está ocupado).

    Primero los que se pueden reservar, del más barato al más caro.
    """
    ahora = ahora or datetime.now(UTC)
    vehiculos = vehiculos_de(db, [p]).get(p.id, [])[:MAX_VEHICULOS_OPCIONES]
    resultado: list[Opcion] = []
    for v in vehiculos:
        try:
            cot = rt.cotizar_traslado(db, v.unidad, pedido, ahora)
        except reservas.NoSePuedeReservar as e:
            resultado.append(Opcion(v.unidad, None, False, str(e)))
            continue
        libre = all(
            horarios.libre(db, v.unidad.id, x.precio.inicio, x.ocupado_hasta, ahora)
            for x in cot.viajes
        )
        resultado.append(
            Opcion(
                v.unidad, cot, libre,
                None if libre else "Ya tiene un viaje a esa hora",
            )
        )
    resultado.sort(
        key=lambda o: (
            not o.disponible,
            o.cotizacion is None,
            o.cotizacion.total_viajero if o.cotizacion else Decimal(0),
            o.vehiculo.capacidad,
        )
    )
    return resultado
