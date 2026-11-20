"""Búsqueda de alojamientos disponibles (docs/01 §5 R4).

Toda la lógica vive acá: el frontend solo muestra lo que este servicio calcula.

El filtrado selectivo —ubicación, capacidad, noches libres— ocurre en SQL, que es
donde la base usa sus índices GiST. El precio de cada unidad se calcula después en
Python con `app.services.precios`, porque depende de tarifas por temporada, por día
de la semana, cargos y descuentos que no se expresan bien en una sola consulta.
Para que eso no degrade, la consulta corta en `LIMITE_CANDIDATAS` unidades; con más
oferta por destino habrá que materializar precios por noche.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from geoalchemy2 import Geography, Geometry
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import (
    BloqueoFecha,
    Comodidad,
    Localidad,
    Provincia,
    Publicacion,
    ReglaComision,
    SubtipoServicio,
    Unidad,
    publicacion_comodidad,
)
from app.models.enums import EstadoPublicacion
from app.services import comisiones, precios

LIMITE_CANDIDATAS = 600
POR_PAGINA_MAX = 48
RADIO_KM_DEFECTO = 25.0


class Orden(StrEnum):
    RELEVANCIA = "relevancia"
    PRECIO_ASC = "precio_asc"
    PRECIO_DESC = "precio_desc"
    DISTANCIA = "distancia"


class DestinoDesconocido(Exception):
    """El destino pedido no existe en el catálogo."""


@dataclass(frozen=True)
class Filtros:
    fecha_inicio: date
    fecha_fin: date
    personas: int = 1
    mascotas: int = 0
    provincia: str | None = None
    localidad: str | None = None
    lat: float | None = None
    lon: float | None = None
    radio_km: float = RADIO_KM_DEFECTO
    precio_min: Decimal | None = None
    precio_max: Decimal | None = None
    subtipos: tuple[str, ...] = ()
    comodidades: tuple[str, ...] = ()
    confirmacion_inmediata: bool | None = None
    orden: Orden = Orden.RELEVANCIA
    pagina: int = 1
    por_pagina: int = 24

    @property
    def noches(self) -> int:
        return (self.fecha_fin - self.fecha_inicio).days


@dataclass(frozen=True)
class Destino:
    """Lo que se buscó, ya resuelto contra el catálogo."""

    localidad_id: UUID | None = None
    localidad: str | None = None
    provincia_id: UUID | None = None
    provincia: str | None = None
    lat: float | None = None
    lon: float | None = None

    @property
    def punto(self) -> tuple[float, float] | None:
        return (self.lat, self.lon) if self.lat is not None and self.lon is not None else None


@dataclass(frozen=True)
class PrecioViajero:
    """Precio del prestador más el cargo de servicio que la regla le pase al viajero.

    `cargo_servicio` vale cero cuando la comisión la paga el prestador o cuando no se
    cobra comisión. El desglose nombra siempre sus componentes, así cambiar la regla
    no obliga a cambiar la pantalla.
    """

    precio: precios.Precio
    cargo_servicio: Decimal
    total: Decimal


@dataclass(frozen=True)
class UnidadDisponible:
    id: UUID
    nombre: str
    capacidad: int
    precio: PrecioViajero


@dataclass(frozen=True)
class Resultado:
    publicacion_id: UUID
    slug: str
    titulo: str
    subtipo: str | None
    subtipo_codigo: str | None
    prestador: str
    localidad: str
    provincia: str
    confirmacion_inmediata: bool
    lat: float | None
    lon: float | None
    distancia_km: float | None
    fotos: list[dict[str, str | None]]
    comodidades: list[str]
    unidades_disponibles: int
    unidad: UnidadDisponible


@dataclass
class Pagina:
    total: int
    pagina: int
    por_pagina: int
    paginas: int
    noches: int
    destino: Destino
    resultados: list[Resultado] = field(default_factory=list)


def lat_lon(columna):
    """Latitud y longitud de una columna Geography, vía su geometría."""
    geom = columna.cast(Geometry)
    return func.ST_Y(geom), func.ST_X(geom)


def resolver_destino(db: Session, f: Filtros) -> Destino:
    """Traduce lo que escribió el viajero a ids del catálogo y a un punto de referencia."""
    if f.lat is not None and f.lon is not None:
        return Destino(lat=f.lat, lon=f.lon)

    if f.localidad:
        lat_col, lon_col = lat_lon(Localidad.ubicacion)
        stmt = (
            select(Localidad.id, Localidad.nombre, Provincia.id, Provincia.nombre, lat_col, lon_col)
            .join(Provincia, Localidad.provincia_id == Provincia.id)
            .where(Localidad.slug == f.localidad)
        )
        if f.provincia:
            stmt = stmt.where(Provincia.slug == f.provincia)
        fila = db.execute(stmt).first()
        if fila is None:
            raise DestinoDesconocido(f.localidad)
        loc_id, loc_nombre, prov_id, prov_nombre, lat, lon = fila
        return Destino(
            localidad_id=loc_id,
            localidad=loc_nombre,
            provincia_id=prov_id,
            provincia=prov_nombre,
            lat=lat,
            lon=lon,
        )

    if f.provincia:
        fila = db.execute(
            select(Provincia.id, Provincia.nombre).where(Provincia.slug == f.provincia)
        ).first()
        if fila is None:
            raise DestinoDesconocido(f.provincia)
        return Destino(provincia_id=fila[0], provincia=fila[1])

    return Destino()


def _sin_bloqueos(fecha_inicio: date, fecha_fin: date):
    """Ninguna noche del rango pedido puede estar tomada, retenida ni bloqueada por iCal."""
    rango = func.daterange(fecha_inicio, fecha_fin, "[)")
    return (
        ~select(BloqueoFecha.id)
        .where(
            BloqueoFecha.unidad_id == Unidad.id,
            BloqueoFecha.activo.is_(True),
            BloqueoFecha.rango.op("&&")(rango),
            or_(BloqueoFecha.vence_en.is_(None), BloqueoFecha.vence_en > func.now()),
        )
        .exists()
    )


def _consulta_candidatas(f: Filtros, destino: Destino) -> Select:
    stmt = (
        select(Unidad)
        .join(Publicacion, Unidad.publicacion_id == Publicacion.id)
        .join(Localidad, Publicacion.localidad_id == Localidad.id)
        .where(
            Unidad.activa.is_(True),
            Publicacion.estado == EstadoPublicacion.APROBADA,
            Unidad.capacidad >= f.personas,
            _sin_bloqueos(f.fecha_inicio, f.fecha_fin),
        )
        .options(
            selectinload(Unidad.tarifas),
            selectinload(Unidad.publicacion).selectinload(Publicacion.fotos),
            selectinload(Unidad.publicacion).selectinload(Publicacion.comodidades),
            selectinload(Unidad.publicacion).selectinload(Publicacion.prestador),
            selectinload(Unidad.publicacion).selectinload(Publicacion.subtipo),
            selectinload(Unidad.publicacion)
            .selectinload(Publicacion.localidad)
            .selectinload(Localidad.provincia),
        )
    )

    if destino.localidad_id:
        stmt = stmt.where(Publicacion.localidad_id == destino.localidad_id)
    elif destino.provincia_id:
        stmt = stmt.where(Localidad.provincia_id == destino.provincia_id)
    elif destino.punto:
        punto = func.ST_SetSRID(func.ST_MakePoint(destino.lon, destino.lat), 4326).cast(Geography)
        stmt = stmt.where(func.ST_DWithin(Publicacion.ubicacion, punto, f.radio_km * 1000))

    if f.subtipos:
        stmt = stmt.join(
            SubtipoServicio, Publicacion.subtipo_servicio_id == SubtipoServicio.id
        ).where(SubtipoServicio.codigo.in_(f.subtipos))

    if f.confirmacion_inmediata is not None:
        stmt = stmt.where(Publicacion.confirmacion_inmediata.is_(f.confirmacion_inmediata))

    if f.comodidades:
        pedidas = set(f.comodidades)
        encontradas = (
            select(func.count())
            .select_from(publicacion_comodidad)
            .join(Comodidad, Comodidad.id == publicacion_comodidad.c.comodidad_id)
            .where(
                publicacion_comodidad.c.publicacion_id == Publicacion.id,
                Comodidad.codigo.in_(pedidas),
            )
            .scalar_subquery()
        )
        stmt = stmt.where(encontradas == len(pedidas))

    return stmt.order_by(Publicacion.id, Unidad.id).limit(LIMITE_CANDIDATAS)


def tarifas_de(unidad: Unidad) -> list[precios.Tarifa]:
    """Las tarifas del modelo, en la forma que espera el motor de precios."""
    return [
        precios.Tarifa(
            precio_noche=t.precio_noche,
            fecha_desde=t.fecha_desde,
            fecha_hasta=t.fecha_hasta,
            precios_dia_semana=t.precios_dia_semana,
            estadia_minima=t.estadia_minima,
            estadia_maxima=t.estadia_maxima,
            anticipacion_minima_dias=t.anticipacion_minima_dias,
            prioridad=t.prioridad,
        )
        for t in unidad.tarifas
    ]


def unidad_plana(u: Unidad) -> precios.Unidad:
    return precios.Unidad(
        capacidad=u.capacidad,
        capacidad_base=u.capacidad_base,
        cargo_limpieza=u.cargo_limpieza,
        cargo_persona_extra=u.cargo_persona_extra,
        cargo_mascota=u.cargo_mascota,
        descuento_semanal=u.descuento_semanal,
        descuento_mensual=u.descuento_mensual,
    )


def distancia_km(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float | None:
    """Haversine entre el punto del destino y el de la publicación."""
    if not a or not b:
        return None
    radio = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return round(2 * radio * math.asin(math.sqrt(h)), 1)


def _antiguedad_meses(alta: date, hoy: date) -> int:
    return max(0, (hoy.year - alta.year) * 12 + (hoy.month - alta.month))


def cobro_viajero(
    reglas: list[comisiones.Regla],
    precio: precios.Precio,
    unidad: Unidad,
    alicuota: Decimal,
    hoy: date,
    fecha_servicio: date,
) -> PrecioViajero:
    """Aplica la regla de comisión vigente y devuelve lo que paga el viajero."""
    p = unidad.publicacion
    ctx = comisiones.ContextoComision(
        monto=precio.subtotal,
        fecha_servicio=fecha_servicio,
        fecha_creacion=hoy,
        tipo_servicio_id=p.tipo_servicio_id,
        subtipo_servicio_id=p.subtipo_servicio_id,
        provincia_id=p.localidad.provincia_id,
        localidad_id=p.localidad_id,
        zona_id=p.zona_id,
        prestador_id=p.prestador_id,
        publicacion_id=p.id,
        antiguedad_prestador_meses=_antiguedad_meses(p.prestador.fecha_alta, hoy),
        categoria_prestador=p.prestador.categoria,
    )
    try:
        cargo = comisiones.resolver(reglas, ctx, alicuota).cargo_viajero
    except comisiones.SinReglaAplicable:
        # Sin regla por defecto no se inventa un cargo: el viajero ve el precio del
        # prestador y el operador detecta el faltante en el simulador.
        cargo = Decimal("0.00")
    return PrecioViajero(precio=precio, cargo_servicio=cargo, total=precio.subtotal + cargo)


def _coordenadas(db: Session, publicaciones: set[UUID]) -> dict[UUID, tuple[float, float]]:
    if not publicaciones:
        return {}
    lat_col, lon_col = lat_lon(Publicacion.ubicacion)
    filas = db.execute(
        select(Publicacion.id, lat_col, lon_col).where(
            Publicacion.id.in_(publicaciones), Publicacion.ubicacion.is_not(None)
        )
    ).all()
    return {pid: (lat, lon) for pid, lat, lon in filas}


def _clave_orden(orden: Orden):
    match orden:
        case Orden.PRECIO_ASC:
            return lambda r: (r.unidad.precio.total, r.titulo)
        case Orden.PRECIO_DESC:
            return lambda r: (-r.unidad.precio.total, r.titulo)
        case Orden.DISTANCIA:
            return lambda r: (
                r.distancia_km if r.distancia_km is not None else float("inf"),
                r.titulo,
            )
        case _:
            # Todavía no hay reseñas: relevancia es confirmación inmediata primero,
            # después cuántas fotos tiene la ficha, y a igualdad, el precio más bajo.
            return lambda r: (
                not r.confirmacion_inmediata,
                -len(r.fotos),
                r.unidad.precio.total,
                r.titulo,
            )


def buscar(db: Session, f: Filtros, hoy: date | None = None) -> Pagina:
    hoy = hoy or date.today()
    if f.noches < 1:
        raise precios.NoDisponible(precios.MotivoNoDisponible.RANGO_INVALIDO)

    destino = resolver_destino(db, f)
    reglas = [comisiones.regla_desde_modelo(m) for m in db.scalars(select(ReglaComision))]
    alicuota = get_settings().iva_comision

    candidatas = list(db.scalars(_consulta_candidatas(f, destino)).unique())
    coordenadas = _coordenadas(db, {u.publicacion_id for u in candidatas})

    disponibles: dict[UUID, list[tuple[Unidad, PrecioViajero]]] = {}
    for unidad in candidatas:
        try:
            precio = precios.calcular(
                unidad_plana(unidad),
                tarifas_de(unidad),
                f.fecha_inicio,
                f.fecha_fin,
                personas=f.personas,
                mascotas=f.mascotas,
                hoy=hoy,
            )
        except precios.NoDisponible:
            continue
        disponibles.setdefault(unidad.publicacion_id, []).append(
            (unidad, cobro_viajero(reglas, precio, unidad, alicuota, hoy, f.fecha_inicio))
        )

    resultados: list[Resultado] = []
    for publicacion_id, unidades in disponibles.items():
        # La ficha se muestra con su unidad más barata entre las que sí entran.
        unidades.sort(key=lambda par: (par[1].total, par[0].nombre))
        unidad, cobro = unidades[0]
        if f.precio_min is not None and cobro.total < f.precio_min:
            continue
        if f.precio_max is not None and cobro.total > f.precio_max:
            continue
        p = unidad.publicacion
        punto = coordenadas.get(publicacion_id)
        resultados.append(
            Resultado(
                publicacion_id=publicacion_id,
                slug=p.slug,
                titulo=p.titulo,
                subtipo=p.subtipo.nombre if p.subtipo else None,
                subtipo_codigo=p.subtipo.codigo if p.subtipo else None,
                prestador=p.prestador.razon_social,
                localidad=p.localidad.nombre,
                provincia=p.localidad.provincia.nombre,
                confirmacion_inmediata=p.confirmacion_inmediata,
                lat=punto[0] if punto else None,
                lon=punto[1] if punto else None,
                distancia_km=distancia_km(destino.punto, punto),
                fotos=[{"url": ft.url, "descripcion": ft.descripcion} for ft in p.fotos],
                comodidades=[c.codigo for c in p.comodidades],
                unidades_disponibles=len(unidades),
                unidad=UnidadDisponible(
                    id=unidad.id,
                    nombre=unidad.nombre,
                    capacidad=unidad.capacidad,
                    precio=cobro,
                ),
            )
        )

    resultados.sort(key=_clave_orden(f.orden))

    total = len(resultados)
    por_pagina = max(1, min(f.por_pagina, POR_PAGINA_MAX))
    paginas = max(1, math.ceil(total / por_pagina))
    pagina = max(1, min(f.pagina, paginas))
    desde = (pagina - 1) * por_pagina

    return Pagina(
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        paginas=paginas,
        noches=f.noches,
        destino=destino,
        resultados=resultados[desde : desde + por_pagina],
    )
