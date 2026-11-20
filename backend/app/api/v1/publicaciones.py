"""Búsqueda pública de alojamientos (docs/01 §5 R4).

El frontend no calcula nada: acá se resuelve disponibilidad, precio, comisión,
orden y paginado. Los importes viajan como string para no perder precisión al
pasar por JSON, donde todo número es float.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, PlainSerializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Comodidad, Localidad, Provincia, Publicacion, SubtipoServicio
from app.models.enums import EstadoPublicacion
from app.services import busqueda, precios
from app.services import publicaciones as fichas

router = APIRouter(tags=["publicaciones"])

Dinero = Annotated[
    Decimal, PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")
]


class NocheOut(BaseModel):
    fecha: date
    precio: Dinero


class PrecioOut(BaseModel):
    noches: int
    promedio_noche: Dinero
    alojamiento: Dinero
    descuento: Dinero
    porcentaje_descuento: Dinero
    limpieza: Dinero
    personas_extra: Dinero
    mascotas: Dinero
    subtotal: Dinero = Field(description="Lo que cobra el prestador")
    cargo_servicio: Dinero = Field(description="Comisión que la regla le pasa al viajero")
    total: Dinero = Field(description="Lo que paga el viajero, todo incluido")
    detalle_noches: list[NocheOut]


class UnidadOut(BaseModel):
    id: UUID
    nombre: str
    capacidad: int
    precio: PrecioOut


class FotoOut(BaseModel):
    url: str
    descripcion: str | None = None


class ResultadoOut(BaseModel):
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
    fotos: list[FotoOut]
    comodidades: list[str]
    unidades_disponibles: int
    unidad: UnidadOut


class DestinoOut(BaseModel):
    localidad: str | None = None
    provincia: str | None = None
    lat: float | None = None
    lon: float | None = None


class BusquedaOut(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    paginas: int
    noches: int
    moneda: str = "ARS"
    destino: DestinoOut
    resultados: list[ResultadoOut]


class SugerenciaDestino(BaseModel):
    nombre: str
    slug: str
    provincia: str
    provincia_slug: str
    publicaciones: int


def _precio_out(p: busqueda.PrecioViajero) -> PrecioOut:
    return PrecioOut(
        noches=p.precio.cantidad_noches,
        promedio_noche=p.precio.promedio_noche,
        alojamiento=p.precio.alojamiento,
        descuento=p.precio.descuento,
        porcentaje_descuento=p.precio.porcentaje_descuento,
        limpieza=p.precio.limpieza,
        personas_extra=p.precio.personas_extra,
        mascotas=p.precio.mascotas,
        subtotal=p.precio.subtotal,
        cargo_servicio=p.cargo_servicio,
        total=p.total,
        detalle_noches=[NocheOut(fecha=n.fecha, precio=n.precio) for n in p.precio.noches],
    )


@router.get("/destinos", response_model=list[SugerenciaDestino])
def destinos(
    q: Annotated[str | None, Query(max_length=80, description="Texto a buscar")] = None,
    limite: Annotated[int, Query(ge=1, le=50)] = 20,
    db: Session = Depends(get_db),
) -> list[SugerenciaDestino]:
    """Localidades con oferta publicada. Alimenta el buscador y las sugerencias."""
    publicadas = (
        select(func.count(Publicacion.id))
        .where(
            Publicacion.localidad_id == Localidad.id,
            Publicacion.estado == EstadoPublicacion.APROBADA,
        )
        .scalar_subquery()
    )
    stmt = (
        select(Localidad.nombre, Localidad.slug, Provincia.nombre, Provincia.slug, publicadas)
        .join(Provincia, Localidad.provincia_id == Provincia.id)
        .where(publicadas > 0)
    )
    if q:
        patron = f"%{q.strip()}%"
        stmt = stmt.where(Localidad.nombre.ilike(patron) | Provincia.nombre.ilike(patron))
    stmt = stmt.order_by(publicadas.desc(), Localidad.nombre).limit(limite)
    return [
        SugerenciaDestino(
            nombre=nombre,
            slug=slug,
            provincia=provincia,
            provincia_slug=provincia_slug,
            publicaciones=cantidad,
        )
        for nombre, slug, provincia, provincia_slug, cantidad in db.execute(stmt)
    ]


@router.get("/publicaciones/buscar", response_model=BusquedaOut)
def buscar(
    desde: Annotated[date, Query(description="Fecha de llegada")],
    hasta: Annotated[date, Query(description="Fecha de salida")],
    personas: Annotated[int, Query(ge=1, le=30)] = 2,
    mascotas: Annotated[int, Query(ge=0, le=5)] = 0,
    provincia: Annotated[str | None, Query(max_length=120)] = None,
    localidad: Annotated[str | None, Query(max_length=120)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radio_km: Annotated[float, Query(gt=0, le=300)] = busqueda.RADIO_KM_DEFECTO,
    precio_min: Annotated[Decimal | None, Query(ge=0)] = None,
    precio_max: Annotated[Decimal | None, Query(ge=0)] = None,
    subtipo: Annotated[list[str] | None, Query(description="Códigos de subtipo")] = None,
    comodidad: Annotated[list[str] | None, Query(description="Códigos de comodidad")] = None,
    confirmacion_inmediata: bool | None = None,
    orden: busqueda.Orden = busqueda.Orden.RELEVANCIA,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=busqueda.POR_PAGINA_MAX)] = 24,
    db: Session = Depends(get_db),
) -> BusquedaOut:
    filtros = busqueda.Filtros(
        fecha_inicio=desde,
        fecha_fin=hasta,
        personas=personas,
        mascotas=mascotas,
        provincia=provincia,
        localidad=localidad,
        lat=lat,
        lon=lon,
        radio_km=radio_km,
        precio_min=precio_min,
        precio_max=precio_max,
        subtipos=tuple(subtipo or ()),
        comodidades=tuple(comodidad or ()),
        confirmacion_inmediata=confirmacion_inmediata,
        orden=orden,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    try:
        pagina_resultados = busqueda.buscar(db, filtros)
    except precios.NoDisponible as e:
        raise HTTPException(422, str(e)) from e
    except busqueda.DestinoDesconocido as e:
        raise HTTPException(
            404,
            {
                "mensaje": "No conocemos ese destino todavía",
                "destino": str(e),
                "sugerencias": [s.model_dump() for s in destinos(limite=8, db=db)],
            },
        ) from e

    return BusquedaOut(
        total=pagina_resultados.total,
        pagina=pagina_resultados.pagina,
        por_pagina=pagina_resultados.por_pagina,
        paginas=pagina_resultados.paginas,
        noches=pagina_resultados.noches,
        destino=DestinoOut(
            localidad=pagina_resultados.destino.localidad,
            provincia=pagina_resultados.destino.provincia,
            lat=pagina_resultados.destino.lat,
            lon=pagina_resultados.destino.lon,
        ),
        resultados=[
            ResultadoOut(
                publicacion_id=r.publicacion_id,
                slug=r.slug,
                titulo=r.titulo,
                subtipo=r.subtipo,
                subtipo_codigo=r.subtipo_codigo,
                prestador=r.prestador,
                localidad=r.localidad,
                provincia=r.provincia,
                confirmacion_inmediata=r.confirmacion_inmediata,
                lat=r.lat,
                lon=r.lon,
                distancia_km=r.distancia_km,
                fotos=[FotoOut(**f) for f in r.fotos],
                comodidades=r.comodidades,
                unidades_disponibles=r.unidades_disponibles,
                unidad=UnidadOut(
                    id=r.unidad.id,
                    nombre=r.unidad.nombre,
                    capacidad=r.unidad.capacidad,
                    precio=_precio_out(r.unidad.precio),
                ),
            )
            for r in pagina_resultados.resultados
        ],
    )


class FiltrosDisponibles(BaseModel):
    """Catálogo para armar los filtros sin que el frontend invente códigos."""

    subtipos: list[dict[str, str]]
    comodidades: list[dict[str, str | None]]
    ordenes: list[dict[str, str]]


@router.get("/publicaciones/filtros", response_model=FiltrosDisponibles)
def filtros(db: Session = Depends(get_db)) -> FiltrosDisponibles:
    return FiltrosDisponibles(
        subtipos=[
            {"codigo": s.codigo, "nombre": s.nombre}
            for s in db.scalars(select(SubtipoServicio).order_by(SubtipoServicio.nombre))
        ],
        comodidades=[
            {"codigo": c.codigo, "nombre": c.nombre, "icono": c.icono}
            for c in db.scalars(select(Comodidad).order_by(Comodidad.nombre))
        ],
        ordenes=[
            {"codigo": busqueda.Orden.RELEVANCIA.value, "nombre": "Relevancia"},
            {"codigo": busqueda.Orden.PRECIO_ASC.value, "nombre": "Precio: menor a mayor"},
            {"codigo": busqueda.Orden.PRECIO_DESC.value, "nombre": "Precio: mayor a menor"},
            {"codigo": busqueda.Orden.DISTANCIA.value, "nombre": "Distancia al centro"},
        ],
    )

# --- Ficha de publicación y páginas por destino (docs/01 §5 R4, §6) ---


class ComodidadOut(BaseModel):
    codigo: str
    nombre: str


class PrestadorOut(BaseModel):
    razon_social: str
    verificado: bool
    publica_desde: int = Field(description="Año en que se dio de alta")


class PoliticaOut(BaseModel):
    codigo: str
    nombre: str
    descripcion: str | None
    tramos: list[dict]


class UnidadFichaOut(BaseModel):
    id: UUID
    nombre: str
    capacidad: int
    capacidad_base: int | None
    tarifa_base: Dinero | None = Field(
        description="Precio por noche de referencia, sin temporada ni cargos"
    )
    estadia_minima: int
    cargo_limpieza: Dinero
    cargo_persona_extra: Dinero
    cargo_mascota: Dinero
    descuento_semanal: Dinero
    descuento_mensual: Dinero
    disponible: bool | None = Field(description="null si no se pidieron fechas")
    motivo: str | None
    precio: PrecioOut | None


class FichaOut(BaseModel):
    publicacion_id: UUID
    slug: str
    titulo: str
    descripcion: str
    reglas_casa: str | None
    subtipo: str | None
    subtipo_codigo: str | None
    localidad: str
    localidad_slug: str
    zona: str | None
    provincia: str
    direccion: str | None
    lat: float | None
    lon: float | None
    hora_ingreso: str | None
    hora_salida: str | None
    confirmacion_inmediata: bool
    es_demo: bool
    prestador: PrestadorOut
    politica_cancelacion: PoliticaOut | None
    fotos: list[FotoOut]
    comodidades: list[ComodidadOut]
    unidades: list[UnidadFichaOut]
    noches: int | None
    moneda: str = "ARS"


class ResumenDestinoOut(BaseModel):
    publicacion_id: UUID
    slug: str
    titulo: str
    subtipo: str | None
    localidad: str
    provincia: str
    zona: str | None
    lat: float | None
    lon: float | None
    capacidad_maxima: int
    tarifa_desde: Dinero | None
    confirmacion_inmediata: bool
    fotos: list[FotoOut]
    comodidades: list[str]


class DestinoPaginaOut(BaseModel):
    localidad: str
    localidad_slug: str
    provincia: str
    provincia_slug: str
    zonas: list[str]
    total: int
    pagina: int
    por_pagina: int
    paginas: int
    publicaciones: list[ResumenDestinoOut]


def _unidad_ficha_out(u: fichas.UnidadFicha) -> UnidadFichaOut:
    return UnidadFichaOut(
        id=u.id,
        nombre=u.nombre,
        capacidad=u.capacidad,
        capacidad_base=u.capacidad_base,
        tarifa_base=u.tarifa_base,
        estadia_minima=u.estadia_minima,
        cargo_limpieza=u.cargo_limpieza,
        cargo_persona_extra=u.cargo_persona_extra,
        cargo_mascota=u.cargo_mascota,
        descuento_semanal=u.descuento_semanal,
        descuento_mensual=u.descuento_mensual,
        disponible=u.disponible,
        motivo=u.motivo,
        precio=_precio_out(u.precio) if u.precio else None,
    )


def _resumen_destino_out(r: fichas.ResumenDestino) -> ResumenDestinoOut:
    """La tarjeta de un alojamiento sin fechas: lo que hay, no lo que está libre."""
    p = r.publicacion
    return ResumenDestinoOut(
        publicacion_id=p.id,
        slug=p.slug,
        titulo=p.titulo,
        subtipo=p.subtipo.nombre if p.subtipo else None,
        localidad=p.localidad.nombre,
        provincia=p.localidad.provincia.nombre,
        zona=p.zona.nombre if p.zona else None,
        lat=r.lat,
        lon=r.lon,
        capacidad_maxima=r.capacidad_maxima,
        tarifa_desde=r.tarifa_desde,
        confirmacion_inmediata=p.confirmacion_inmediata,
        fotos=[FotoOut(url=f.url, descripcion=f.descripcion) for f in p.fotos],
        comodidades=[c.codigo for c in p.comodidades],
    )


class ExplorarPaginaOut(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    paginas: int
    publicaciones: list[ResumenDestinoOut]
    #: Desde dónde se midieron las distancias, si se midieron.
    origen: list[float] | None = None


@router.get("/publicaciones/explorar", response_model=ExplorarPaginaOut)
def explorar(
    localidad: Annotated[str | None, Query(max_length=120)] = None,
    provincia: Annotated[str | None, Query(max_length=120)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    personas: Annotated[int | None, Query(ge=1, le=30)] = None,
    subtipo: Annotated[list[str] | None, Query()] = None,
    comodidad: Annotated[list[str] | None, Query()] = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=48)] = 24,
    db: Session = Depends(get_db),
) -> ExplorarPaginaOut:
    """Lo que hay publicado, sin pedir fechas.

    Es lo que ve quien entra a buscar y todavía no sabe cuándo viaja. No filtra
    por disponibilidad —para eso hacen falta las fechas— así que el precio que
    devuelve es la tarifa base, nunca un total. Con `lat`/`lon` ordena por
    cercanía.
    """
    p = fichas.explorar(
        db,
        localidad_slug=localidad,
        provincia_slug=provincia,
        lat=lat,
        lon=lon,
        personas=personas,
        subtipos=subtipo,
        comodidades=comodidad,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return ExplorarPaginaOut(
        total=p.total,
        pagina=p.pagina,
        por_pagina=p.por_pagina,
        paginas=p.paginas,
        publicaciones=[_resumen_destino_out(r) for r in p.publicaciones],
        origen=list(p.origen) if p.origen else None,
    )


@router.get("/destinos/{slug}/publicaciones", response_model=DestinoPaginaOut)
def publicaciones_por_destino(
    slug: str,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=48)] = 24,
    db: Session = Depends(get_db),
) -> DestinoPaginaOut:
    """Lo que hay publicado en un destino, sin fechas. Es la página que indexa Google."""
    try:
        p = fichas.listar_por_destino(db, slug, pagina=pagina, por_pagina=por_pagina)
    except fichas.NoEncontrada as e:
        raise HTTPException(404, f"No conocemos el destino {slug}") from e

    return DestinoPaginaOut(
        localidad=p.localidad.nombre,
        localidad_slug=p.localidad.slug,
        provincia=p.localidad.provincia.nombre,
        provincia_slug=p.localidad.provincia.slug,
        zonas=sorted(z.nombre for z in p.localidad.zonas),
        total=p.total,
        pagina=p.pagina,
        por_pagina=p.por_pagina,
        paginas=p.paginas,
        publicaciones=[_resumen_destino_out(r) for r in p.publicaciones],
    )


@router.get("/publicaciones/{slug}", response_model=FichaOut)
def ficha(
    slug: str,
    desde: date | None = None,
    hasta: date | None = None,
    personas: Annotated[int, Query(ge=1, le=30)] = 2,
    mascotas: Annotated[int, Query(ge=0, le=5)] = 0,
    db: Session = Depends(get_db),
) -> FichaOut:
    """Todo sobre un alojamiento. Con fechas calcula precio y disponibilidad por unidad."""
    try:
        f = fichas.obtener(db, slug, desde=desde, hasta=hasta, personas=personas, mascotas=mascotas)
    except fichas.NoEncontrada as e:
        raise HTTPException(404, "No encontramos ese alojamiento") from e
    except precios.NoDisponible as e:
        raise HTTPException(422, str(e)) from e

    p = f.publicacion
    politica = p.politica_cancelacion
    return FichaOut(
        publicacion_id=p.id,
        slug=p.slug,
        titulo=p.titulo,
        descripcion=p.descripcion,
        reglas_casa=p.reglas_casa,
        subtipo=p.subtipo.nombre if p.subtipo else None,
        subtipo_codigo=p.subtipo.codigo if p.subtipo else None,
        localidad=p.localidad.nombre,
        localidad_slug=p.localidad.slug,
        zona=p.zona.nombre if p.zona else None,
        provincia=p.localidad.provincia.nombre,
        direccion=p.direccion,
        lat=f.lat,
        lon=f.lon,
        hora_ingreso=p.hora_ingreso.isoformat(timespec="minutes") if p.hora_ingreso else None,
        hora_salida=p.hora_salida.isoformat(timespec="minutes") if p.hora_salida else None,
        confirmacion_inmediata=p.confirmacion_inmediata,
        es_demo=p.es_demo,
        prestador=PrestadorOut(
            razon_social=p.prestador.razon_social,
            verificado=p.prestador.verificado,
            publica_desde=p.prestador.fecha_alta.year,
        ),
        politica_cancelacion=(
            PoliticaOut(
                codigo=politica.codigo,
                nombre=politica.nombre,
                descripcion=politica.descripcion,
                tramos=politica.tramos,
            )
            if politica
            else None
        ),
        fotos=[FotoOut(url=x.url, descripcion=x.descripcion) for x in p.fotos],
        comodidades=[ComodidadOut(codigo=c.codigo, nombre=c.nombre) for c in p.comodidades],
        unidades=[_unidad_ficha_out(u) for u in f.unidades],
        noches=f.noches,
    )


class CatalogoAlta(BaseModel):
    """Todo lo que el formulario de alta necesita elegir, en una sola llamada."""

    localidades: list[dict[str, str]]
    subtipos: list[dict[str, str]]
    politicas: list[dict[str, str]]
    comodidades: list[dict[str, str | None]]


@router.get("/catalogos/alta", response_model=CatalogoAlta)
def catalogo_alta(db: Session = Depends(get_db)) -> CatalogoAlta:
    from app.models import PoliticaCancelacion

    localidades = db.execute(
        select(Localidad.id, Localidad.nombre, Localidad.slug, Provincia.nombre)
        .join(Provincia, Localidad.provincia_id == Provincia.id)
        .order_by(Provincia.nombre, Localidad.nombre)
    ).all()
    return CatalogoAlta(
        localidades=[
            {"id": str(i), "nombre": n, "slug": s, "provincia": p} for i, n, s, p in localidades
        ],
        subtipos=[
            {"id": str(x.id), "codigo": x.codigo, "nombre": x.nombre}
            for x in db.scalars(select(SubtipoServicio).order_by(SubtipoServicio.nombre))
        ],
        politicas=[
            {"id": str(x.id), "codigo": x.codigo, "nombre": x.nombre}
            for x in db.scalars(
                select(PoliticaCancelacion)
                .where(PoliticaCancelacion.activa)
                .order_by(PoliticaCancelacion.nombre)
            )
        ],
        comodidades=[
            {"codigo": c.codigo, "nombre": c.nombre, "icono": c.icono}
            for c in db.scalars(select(Comodidad).order_by(Comodidad.nombre))
        ],
    )
