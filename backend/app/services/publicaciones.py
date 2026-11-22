"""Ficha de publicación y listados por destino (docs/01 §5 R4, §6).

La búsqueda contesta "qué hay libre para estas fechas". Acá se contesta lo otro:
"contame todo sobre este lugar" y "qué hay publicado en este destino".

La diferencia importante es que la ficha se abre también **sin fechas**, cuando el
viajero llega desde Google. En ese caso no se inventa un precio: se muestran las
unidades con su tarifa base y se pide las fechas, porque el total depende de
temporada, día de la semana, cantidad de personas y estadía.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
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
)
from app.models.enums import EstadoPublicacion
from app.services import busqueda, comisiones, precios, tipos


class NoEncontrada(Exception):
    """No existe una publicación aprobada con ese slug."""


@dataclass(frozen=True)
class UnidadFicha:
    id: UUID
    nombre: str
    capacidad: int
    capacidad_base: int | None
    tarifa_base: Decimal | None
    estadia_minima: int
    cargo_limpieza: Decimal
    cargo_persona_extra: Decimal
    cargo_mascota: Decimal
    descuento_semanal: Decimal
    descuento_mensual: Decimal
    disponible: bool | None  # None cuando no se pidieron fechas
    motivo: str | None
    precio: busqueda.PrecioViajero | None


@dataclass(frozen=True)
class Ficha:
    publicacion: Publicacion
    unidades: list[UnidadFicha]
    lat: float | None
    lon: float | None
    noches: int | None


def _coordenadas(db: Session, publicacion_id: UUID) -> tuple[float | None, float | None]:
    lat_col, lon_col = busqueda.lat_lon(Publicacion.ubicacion)
    fila = db.execute(
        select(lat_col, lon_col).where(
            Publicacion.id == publicacion_id, Publicacion.ubicacion.is_not(None)
        )
    ).first()
    return (fila[0], fila[1]) if fila else (None, None)


def _tarifa_base(unidad: Unidad) -> tuple[Decimal | None, int]:
    """La tarifa sin fechas es el precio de referencia de la unidad."""
    bases = [t for t in unidad.tarifas if t.fecha_desde is None and t.fecha_hasta is None]
    elegida = bases[0] if bases else (unidad.tarifas[0] if unidad.tarifas else None)
    if elegida is None:
        return None, 1
    return elegida.precio_noche, elegida.estadia_minima


def _libre(db: Session, unidad_id: UUID, desde: date, hasta: date) -> bool:
    rango = func.daterange(desde, hasta, "[)")
    choque = db.scalar(
        select(BloqueoFecha.id).where(
            BloqueoFecha.unidad_id == unidad_id,
            BloqueoFecha.activo.is_(True),
            BloqueoFecha.rango.op("&&")(rango),
            or_(BloqueoFecha.vence_en.is_(None), BloqueoFecha.vence_en > func.now()),
        )
    )
    return choque is None


def obtener(
    db: Session,
    slug: str,
    desde: date | None = None,
    hasta: date | None = None,
    personas: int = 2,
    mascotas: int = 0,
    hoy: date | None = None,
) -> Ficha:
    hoy = hoy or date.today()
    publicacion = db.scalar(
        select(Publicacion)
        .where(
            Publicacion.slug == slug,
            Publicacion.estado == EstadoPublicacion.APROBADA,
            tipos.por_noches(),
        )
        .options(
            selectinload(Publicacion.fotos),
            selectinload(Publicacion.comodidades),
            selectinload(Publicacion.prestador),
            selectinload(Publicacion.subtipo),
            selectinload(Publicacion.zona),
            selectinload(Publicacion.politica_cancelacion),
            selectinload(Publicacion.localidad).selectinload(Localidad.provincia),
            selectinload(Publicacion.unidades).selectinload(Unidad.tarifas),
        )
    )
    if publicacion is None:
        raise NoEncontrada(slug)

    con_fechas = desde is not None and hasta is not None
    noches = (hasta - desde).days if con_fechas else None
    if con_fechas and noches is not None and noches < 1:
        raise precios.NoDisponible(precios.MotivoNoDisponible.RANGO_INVALIDO)

    reglas = [comisiones.regla_desde_modelo(m) for m in db.scalars(select(ReglaComision))]
    alicuota = get_settings().iva_comision

    unidades: list[UnidadFicha] = []
    for u in sorted(publicacion.unidades, key=lambda x: (x.capacidad, x.nombre)):
        if not u.activa:
            continue
        tarifa_base, estadia_minima = _tarifa_base(u)
        disponible: bool | None = None
        motivo: str | None = None
        cobro = None

        if con_fechas:
            assert desde is not None and hasta is not None
            if not _libre(db, u.id, desde, hasta):
                disponible, motivo = False, "Ya está reservada en esas fechas"
            else:
                try:
                    precio = precios.calcular(
                        busqueda.unidad_plana(u),
                        busqueda.tarifas_de(u),
                        desde,
                        hasta,
                        personas=personas,
                        mascotas=mascotas,
                        hoy=hoy,
                    )
                    cobro = busqueda.cobro_viajero(reglas, precio, u, alicuota, hoy, desde)
                    disponible = True
                except precios.NoDisponible as e:
                    disponible, motivo = False, precios.MENSAJES[e.motivo]

        unidades.append(
            UnidadFicha(
                id=u.id,
                nombre=u.nombre,
                capacidad=u.capacidad,
                capacidad_base=u.capacidad_base,
                tarifa_base=tarifa_base,
                estadia_minima=estadia_minima,
                cargo_limpieza=u.cargo_limpieza,
                cargo_persona_extra=u.cargo_persona_extra,
                cargo_mascota=u.cargo_mascota,
                descuento_semanal=u.descuento_semanal,
                descuento_mensual=u.descuento_mensual,
                disponible=disponible,
                motivo=motivo,
                precio=cobro,
            )
        )

    lat, lon = _coordenadas(db, publicacion.id)
    return Ficha(publicacion=publicacion, unidades=unidades, lat=lat, lon=lon, noches=noches)


@dataclass(frozen=True)
class ResumenDestino:
    publicacion: Publicacion
    lat: float | None
    lon: float | None
    capacidad_maxima: int
    tarifa_desde: Decimal | None


@dataclass
class PaginaDestino:
    localidad: Localidad
    total: int
    pagina: int
    por_pagina: int
    paginas: int
    publicaciones: list[ResumenDestino]


def listar_por_destino(
    db: Session, localidad_slug: str, pagina: int = 1, por_pagina: int = 24
) -> PaginaDestino:
    """Listado sin fechas para las páginas por destino, que son las que indexa Google.

    No dice qué está libre —eso depende de las fechas— sino qué hay publicado.
    """
    localidad = db.scalar(
        select(Localidad)
        .where(Localidad.slug == localidad_slug)
        .options(selectinload(Localidad.provincia), selectinload(Localidad.zonas))
    )
    if localidad is None:
        raise NoEncontrada(localidad_slug)

    base = select(Publicacion).where(
        Publicacion.localidad_id == localidad.id,
        Publicacion.estado == EstadoPublicacion.APROBADA,
        tipos.por_noches(),
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    paginas = max(1, math.ceil(total / por_pagina))
    pagina = max(1, min(pagina, paginas))

    filas = list(
        db.scalars(
            base.options(
                selectinload(Publicacion.fotos),
                selectinload(Publicacion.comodidades),
                selectinload(Publicacion.subtipo),
                selectinload(Publicacion.prestador),
                selectinload(Publicacion.unidades).selectinload(Unidad.tarifas),
            )
            .order_by(Publicacion.titulo)
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        ).unique()
    )

    lat_col, lon_col = busqueda.lat_lon(Publicacion.ubicacion)
    coords = {
        pid: (lat, lon)
        for pid, lat, lon in db.execute(
            select(Publicacion.id, lat_col, lon_col).where(
                Publicacion.id.in_([p.id for p in filas]), Publicacion.ubicacion.is_not(None)
            )
        )
    }

    resumenes = []
    for p in filas:
        activas = [u for u in p.unidades if u.activa]
        tarifas = [precio for u in activas if (precio := _tarifa_base(u)[0]) is not None]
        punto = coords.get(p.id, (None, None))
        resumenes.append(
            ResumenDestino(
                publicacion=p,
                lat=punto[0],
                lon=punto[1],
                capacidad_maxima=max((u.capacidad for u in activas), default=0),
                tarifa_desde=min(tarifas) if tarifas else None,
            )
        )

    return PaginaDestino(
        localidad=localidad,
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        paginas=paginas,
        publicaciones=resumenes,
    )


@dataclass
class PaginaExplorar:
    total: int
    pagina: int
    por_pagina: int
    paginas: int
    publicaciones: list[ResumenDestino]
    #: Desde dónde se midieron las distancias, si se midieron.
    origen: tuple[float, float] | None = None


def explorar(
    db: Session,
    *,
    localidad_slug: str | None = None,
    provincia_slug: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    personas: int | None = None,
    subtipos: list[str] | None = None,
    comodidades: list[str] | None = None,
    pagina: int = 1,
    por_pagina: int = 24,
) -> PaginaExplorar:
    """Lo que hay publicado, sin pedir fechas.

    Existe porque una pantalla de búsqueda en blanco es un callejón: el visitante
    que todavía no sabe cuándo viaja igual quiere ver qué hay. No dice qué está
    libre —eso sí necesita fechas— y por eso el precio que muestra es la tarifa
    base, no un total.

    Con `lat`/`lon` ordena por cercanía. Sin eso, primero lo que tiene foto: una
    ficha sin foto arriba de todo es la peor primera impresión posible.
    """
    base = select(Publicacion).where(
        Publicacion.estado == EstadoPublicacion.APROBADA, tipos.por_noches()
    )
    if localidad_slug:
        base = base.join(Localidad, Publicacion.localidad_id == Localidad.id).where(
            Localidad.slug == localidad_slug
        )
    elif provincia_slug:
        base = base.join(Localidad, Publicacion.localidad_id == Localidad.id).join(
            Provincia, Localidad.provincia_id == Provincia.id
        ).where(Provincia.slug == provincia_slug)
    if subtipos:
        base = base.join(
            SubtipoServicio, Publicacion.subtipo_servicio_id == SubtipoServicio.id
        ).where(SubtipoServicio.codigo.in_(subtipos))
    for codigo in comodidades or []:
        base = base.where(Publicacion.comodidades.any(Comodidad.codigo == codigo))
    if personas:
        base = base.where(
            Publicacion.unidades.any(
                (Unidad.activa.is_(True)) & (Unidad.capacidad >= personas)
            )
        )

    filas = list(
        db.scalars(
            base.options(
                selectinload(Publicacion.fotos),
                selectinload(Publicacion.comodidades),
                selectinload(Publicacion.subtipo),
                selectinload(Publicacion.localidad).selectinload(Localidad.provincia),
                selectinload(Publicacion.prestador),
                selectinload(Publicacion.unidades).selectinload(Unidad.tarifas),
            )
        ).unique()
    )

    lat_col, lon_col = busqueda.lat_lon(Publicacion.ubicacion)
    coords = {
        pid: (y, x)
        for pid, y, x in db.execute(
            select(Publicacion.id, lat_col, lon_col).where(
                Publicacion.id.in_([p.id for p in filas]), Publicacion.ubicacion.is_not(None)
            )
        )
    }

    origen = (lat, lon) if lat is not None and lon is not None else None
    resumenes = []
    for p in filas:
        activas = [u for u in p.unidades if u.activa]
        tarifas = [precio for u in activas if (precio := _tarifa_base(u)[0]) is not None]
        punto = coords.get(p.id, (None, None))
        resumenes.append(
            ResumenDestino(
                publicacion=p,
                lat=punto[0],
                lon=punto[1],
                capacidad_maxima=max((u.capacidad for u in activas), default=0),
                tarifa_desde=min(tarifas) if tarifas else None,
            )
        )

    if origen:
        resumenes.sort(
            key=lambda r: (
                busqueda.distancia_km(origen, (r.lat, r.lon)) or float("inf"),
                r.publicacion.titulo,
            )
        )
    else:
        # Con foto primero: una ficha sin foto encabezando la página es la peor
        # primera impresión que puede dar el sitio.
        resumenes.sort(key=lambda r: (not r.publicacion.fotos, r.publicacion.titulo))

    total = len(resumenes)
    paginas = max(1, math.ceil(total / por_pagina))
    pagina = max(1, min(pagina, paginas))
    desde = (pagina - 1) * por_pagina
    return PaginaExplorar(
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        paginas=paginas,
        publicaciones=resumenes[desde : desde + por_pagina],
        origen=origen,
    )


def destinos_con_oferta(db: Session) -> list[tuple[Localidad, Provincia, int]]:
    """Para el sitemap y la navegación entre destinos."""
    cuenta = (
        select(func.count(Publicacion.id))
        .where(
            Publicacion.localidad_id == Localidad.id,
            Publicacion.estado == EstadoPublicacion.APROBADA,
            tipos.por_noches(),
        )
        .scalar_subquery()
    )
    return [
        (loc, prov, n)
        for loc, prov, n in db.execute(
            select(Localidad, Provincia, cuenta)
            .join(Provincia, Localidad.provincia_id == Provincia.id)
            .where(cuenta > 0)
            .order_by(cuenta.desc(), Localidad.nombre)
        )
    ]
