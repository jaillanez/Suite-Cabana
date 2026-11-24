"""Excursiones para el viajero (docs/05, etapa 2): qué salidas hay y con cuántos
lugares, cuánto sale ir, y reservar.

Toda la cuenta la hace el backend (CLAUDE.md §3): la web muestra lo que devuelve
`cotizacion` y no recalcula nada.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import con_email_verificado
from app.api.v1.publicaciones import (
    ComodidadOut,
    Dinero,
    EnlaceOut,
    FotoOut,
    PoliticaOut,
    PrestadorOut,
)
from app.api.v1.reservas import ReservaOut, _reserva_out, exigir_telefono
from app.core.config import get_settings
from app.core.database import get_db
from app.models import Publicacion, TurnoExcursion, Unidad, Usuario
from app.models.enums import EstadoPublicacion, ModoReserva
from app.services import busqueda, politicas, reservas, salidas
from app.services import excursiones as svc
from app.services import reservas_excursion as rx
from app.services import salones as salones_svc
from app.services.privacidad import aproximar

router = APIRouter(prefix="/excursiones", tags=["excursiones"])

#: Cuántos días de salidas se piden por vez: alcanza para un calendario mensual.
DIAS_POR_CONSULTA = 62


class PrecioPasajeroOut(BaseModel):
    id: uuid.UUID
    nombre: str
    descripcion: str | None
    edad_desde: int | None
    edad_hasta: int | None
    precio: Dinero
    ocupa_lugar: bool


class SalidaOut(BaseModel):
    turno_id: uuid.UUID | None
    salida_id: uuid.UUID | None
    fecha: date
    nombre: str
    inicio: datetime
    fin: datetime
    cupo: int
    libres: int
    minimo_personas: int


class SalidasOut(BaseModel):
    unidad_id: uuid.UUID
    maximo_por_reserva: int
    precios: list[PrecioPasajeroOut]
    politica_cancelacion: PoliticaOut | None
    reintegro_si_no_sale: int
    salidas: list[SalidaOut]


class PasajerosPedido(BaseModel):
    categoria_id: uuid.UUID
    cantidad: Annotated[int, Field(ge=0, le=500)]


class PedidoExcursion(BaseModel):
    unidad_id: uuid.UUID
    fecha: date
    turno_id: uuid.UUID | None = None
    salida_id: uuid.UUID | None = None
    pasajeros: list[PasajerosPedido] = Field(min_length=1, max_length=20)


class NuevaReservaExcursion(PedidoExcursion):
    acepta_terminos: bool = False
    telefono: Annotated[str | None, Field(default=None, max_length=30)] = None


class LineaPasajeroOut(BaseModel):
    concepto: str
    cantidad: int
    precio_unitario: Dinero
    monto: Dinero


class CotizacionExcursionOut(BaseModel):
    salida: SalidaOut
    lineas: list[LineaPasajeroOut]
    personas: int
    lugares: int
    subtotal: Dinero
    cargo_servicio: Dinero
    total: Dinero
    sena: Dinero | None
    a_pagar_ahora: Dinero
    saldo_con_prestador: Dinero | None


class PrecioDesdeOut(BaseModel):
    monto: Dinero
    detalle: str


class ExcursionResultadoOut(BaseModel):
    slug: str
    titulo: str
    subtipo: str | None
    localidad: str
    provincia: str
    lat: float | None = Field(description="Aproximada (~1 km)")
    lon: float | None
    fotos: list[FotoOut]
    comodidades: list[str]
    maximo_por_reserva: int
    precio_desde: PrecioDesdeOut | None
    proxima_salida: datetime | None = Field(
        description="Con fecha: la primera de ese día; sin fecha: la próxima en 60 días"
    )
    salidas_del_dia: int = Field(description="Cuántas salen ese día con lugar (con fecha)")
    confirmacion_inmediata: bool
    es_demo: bool


class BusquedaExcursionesOut(BaseModel):
    total: int
    pagina: int
    paginas: int
    resultados: list[ExcursionResultadoOut]


class DestinoExcursionOut(BaseModel):
    nombre: str
    slug: str
    provincia: str
    excursiones: int


class TurnoFichaOut(BaseModel):
    nombre: str
    dias_semana: list[int]
    hora_inicio: str
    duracion_minutos: int
    minimo_personas: int


class ActividadOut(BaseModel):
    id: uuid.UUID
    nombre: str
    maximo_por_reserva: int
    precios: list[PrecioPasajeroOut]
    turnos: list[TurnoFichaOut]


class ExcursionFichaOut(BaseModel):
    publicacion_id: uuid.UUID
    slug: str
    titulo: str
    descripcion: str
    para_tener_en_cuenta: str | None
    subtipo: str | None
    localidad: str
    localidad_slug: str
    provincia: str
    zona: str | None
    lat: float | None = Field(description="Aproximada (~1 km): la exacta, con la reserva")
    lon: float | None
    confirmacion_inmediata: bool
    porcentaje_sena: int | None
    reintegro_si_no_sale: int
    es_demo: bool
    prestador: PrestadorOut
    politica_cancelacion: PoliticaOut | None
    fotos: list[FotoOut]
    comodidades: list[ComodidadOut]
    actividades: list[ActividadOut]
    alojamientos_del_anfitrion: list[EnlaceOut]
    moneda: str = "ARS"


def _fecha_reservable(fecha: date | None) -> None:
    """Ni pasado ni más allá de los 12 meses en que se reserva."""
    if fecha is None:
        return
    if fecha < salidas.hoy():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ese día ya pasó")
    if (fecha - salidas.hoy()).days > salidas.VENTANA_DIAS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Se puede reservar hasta 12 meses antes"
        )


def _precio_out(c) -> PrecioPasajeroOut:
    return PrecioPasajeroOut(
        id=c.id, nombre=c.nombre, descripcion=c.descripcion, edad_desde=c.edad_desde,
        edad_hasta=c.edad_hasta, precio=c.precio, ocupa_lugar=c.ocupa_lugar,
    )


def _unidad(db: Session, unidad_id: uuid.UUID) -> Unidad:
    """Una excursión publicada. Cualquier otra cosa es 404, sin decir qué es."""
    unidad = db.scalar(
        select(Unidad)
        .where(Unidad.id == unidad_id)
        .options(
            selectinload(Unidad.publicacion).selectinload(Publicacion.prestador),
            selectinload(Unidad.publicacion).selectinload(Publicacion.tipo_servicio),
            selectinload(Unidad.publicacion).selectinload(Publicacion.politica_cancelacion),
            selectinload(Unidad.publicacion).selectinload(Publicacion.localidad),
        )
    )
    if (
        unidad is None
        or not unidad.activa
        or unidad.publicacion.estado is not EstadoPublicacion.APROBADA
        or unidad.publicacion.tipo_servicio.modo_reserva is not ModoReserva.TURNO_CUPO
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa excursión")
    return unidad


def _salida_out(s: salidas.Salida) -> SalidaOut:
    return SalidaOut(
        turno_id=s.turno_id, salida_id=s.salida_id, fecha=s.fecha, nombre=s.nombre,
        inicio=s.inicio, fin=s.fin, cupo=s.cupo, libres=max(s.libres, 0),
        minimo_personas=s.minimo_personas,
    )


def _pedido(datos: PedidoExcursion) -> dict[uuid.UUID, int]:
    pedido: dict[uuid.UUID, int] = {}
    for p in datos.pasajeros:
        pedido[p.categoria_id] = pedido.get(p.categoria_id, 0) + p.cantidad
    return pedido


@router.get("/buscar", response_model=BusquedaExcursionesOut)
def buscar(
    localidad: Annotated[str | None, Query(max_length=80)] = None,
    provincia: Annotated[str | None, Query(max_length=80)] = None,
    fecha: date | None = None,
    personas: Annotated[int, Query(ge=1, le=salidas.CUPO_MAXIMO)] = 1,
    subtipo: Annotated[list[str] | None, Query(max_length=10)] = None,
    comodidad: Annotated[list[str] | None, Query(max_length=10)] = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=svc.POR_PAGINA_MAX)] = 24,
    db: Session = Depends(get_db),
) -> BusquedaExcursionesOut:
    """Excursiones por destino y personas. Con fecha, solo las que salen ese día con lugar."""
    _fecha_reservable(fecha)
    p = svc.buscar(
        db, localidad=localidad, provincia=provincia, fecha=fecha, personas=personas,
        subtipos=tuple(subtipo or ()), comodidades=tuple(comodidad or ()),
        pagina=pagina, por_pagina=por_pagina,
    )
    puntos = busqueda.coordenadas(db, {r.publicacion.id for r in p.resultados})
    return BusquedaExcursionesOut(
        total=p.total,
        pagina=p.pagina,
        paginas=p.paginas,
        resultados=[
            ExcursionResultadoOut(
                slug=r.publicacion.slug,
                titulo=r.publicacion.titulo,
                subtipo=r.publicacion.subtipo.nombre if r.publicacion.subtipo else None,
                localidad=r.publicacion.localidad.nombre,
                provincia=r.publicacion.localidad.provincia.nombre,
                lat=aproximar(puntos.get(r.publicacion.id, (None, None))[0]),
                lon=aproximar(puntos.get(r.publicacion.id, (None, None))[1]),
                fotos=[
                    FotoOut(url=f.url, descripcion=f.descripcion)
                    for f in sorted(r.publicacion.fotos, key=lambda x: x.orden)[:4]
                ],
                comodidades=sorted(c.codigo for c in r.publicacion.comodidades),
                maximo_por_reserva=r.maximo_por_reserva,
                precio_desde=(
                    PrecioDesdeOut(monto=r.precio_desde.monto, detalle=r.precio_desde.detalle)
                    if r.precio_desde
                    else None
                ),
                proxima_salida=r.proxima_salida.inicio if r.proxima_salida else None,
                salidas_del_dia=len(r.salidas_del_dia),
                confirmacion_inmediata=r.publicacion.confirmacion_inmediata,
                es_demo=r.publicacion.es_demo,
            )
            for r in p.resultados
        ],
    )


@router.get("/destinos", response_model=list[DestinoExcursionOut])
def destinos(db: Session = Depends(get_db)) -> list[DestinoExcursionOut]:
    return [
        DestinoExcursionOut(nombre=loc.nombre, slug=loc.slug, provincia=prov.nombre, excursiones=n)
        for loc, prov, n in svc.destinos(db)
    ]


@router.get("/ficha/{slug}", response_model=ExcursionFichaOut)
def ficha(slug: str, db: Session = Depends(get_db)) -> ExcursionFichaOut:
    """Todo sobre una excursión. Cuándo sale y con cuántos lugares lo dice `salidas`."""
    try:
        p = svc.obtener(db, slug)
    except svc.NoEncontrada as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa excursión") from e
    lat, lon = busqueda.coordenadas(db, {p.id}).get(p.id, (None, None))
    politica = politicas.vigente(p)
    precios = svc.precios_de(db, list(p.unidades))
    utiles = svc.actividades(p, precios)
    turnos = {
        u.id: sorted(
            db.scalars(
                select(TurnoExcursion).where(
                    TurnoExcursion.unidad_id == u.id, TurnoExcursion.activo.is_(True)
                )
            ),
            key=lambda t: t.hora_inicio,
        )
        for u in utiles
    }
    return ExcursionFichaOut(
        publicacion_id=p.id,
        slug=p.slug,
        titulo=p.titulo,
        descripcion=p.descripcion,
        para_tener_en_cuenta=p.reglas_casa,
        subtipo=p.subtipo.nombre if p.subtipo else None,
        localidad=p.localidad.nombre,
        localidad_slug=p.localidad.slug,
        provincia=p.localidad.provincia.nombre,
        zona=p.zona.nombre if p.zona else None,
        lat=aproximar(lat),
        lon=aproximar(lon),
        confirmacion_inmediata=p.confirmacion_inmediata,
        porcentaje_sena=(
            p.porcentaje_sena if p.porcentaje_sena is not None else p.prestador.porcentaje_sena
        ) or None,
        reintegro_si_no_sale=p.reintegro_si_no_sale,
        es_demo=p.es_demo,
        prestador=PrestadorOut(
            razon_social=p.prestador.razon_social,
            verificado=p.prestador.verificado,
            publica_desde=p.prestador.fecha_alta.year,
        ),
        politica_cancelacion=(
            PoliticaOut(
                codigo=politica["codigo"], nombre=politica["nombre"],
                descripcion=politica["descripcion"], tramos=politica["tramos"],
            )
            if politica
            else None
        ),
        fotos=[
            FotoOut(url=f.url, descripcion=f.descripcion)
            for f in sorted(p.fotos, key=lambda x: x.orden)
        ],
        comodidades=[ComodidadOut(codigo=c.codigo, nombre=c.nombre) for c in p.comodidades],
        actividades=[
            ActividadOut(
                id=u.id,
                nombre=u.nombre,
                maximo_por_reserva=u.capacidad,
                precios=[_precio_out(c) for c in precios[u.id]],
                turnos=[
                    TurnoFichaOut(
                        nombre=t.nombre, dias_semana=t.dias_semana,
                        hora_inicio=t.hora_inicio.strftime("%H:%M"),
                        duracion_minutos=t.duracion_minutos,
                        minimo_personas=t.minimo_personas,
                    )
                    for t in turnos[u.id]
                ],
            )
            for u in utiles
        ],
        alojamientos_del_anfitrion=[
            EnlaceOut(titulo=x.titulo, slug=x.slug)
            for x in salones_svc.del_mismo_anfitrion(db, p.prestador_id, ModoReserva.NOCHES)
        ],
    )


@router.get("/unidades/{unidad_id}/salidas", response_model=SalidasOut)
def ver_salidas(
    unidad_id: uuid.UUID,
    desde: date,
    hasta: Annotated[date | None, Query()] = None,
    db: Session = Depends(get_db),
) -> SalidasOut:
    """Las salidas con lugar entre dos días, los precios y la política."""
    unidad = _unidad(db, unidad_id)
    hasta = hasta or desde + timedelta(days=30)
    if hasta < desde or (hasta - desde).days > DIAS_POR_CONSULTA:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Pedí hasta {DIAS_POR_CONSULTA} días de salidas por vez",
        )
    politica = politicas.vigente(unidad.publicacion)
    return SalidasOut(
        unidad_id=unidad.id,
        maximo_por_reserva=unidad.capacidad,
        precios=[_precio_out(c) for c in rx.categorias(db, unidad)],
        politica_cancelacion=(
            PoliticaOut(
                codigo=politica["codigo"], nombre=politica["nombre"],
                descripcion=politica["descripcion"], tramos=politica["tramos"],
            )
            if politica
            else None
        ),
        reintegro_si_no_sale=unidad.publicacion.reintegro_si_no_sale,
        salidas=[
            _salida_out(s)
            for s in salidas.salidas(db, unidad, desde, hasta)
            if s.libres > 0
        ],
    )


@router.post("/cotizacion", response_model=CotizacionExcursionOut)
def cotizacion(
    datos: PedidoExcursion, db: Session = Depends(get_db)
) -> CotizacionExcursionOut:
    """Cuánto sale ir y cuánto se paga ahora. No reserva nada."""
    unidad = _unidad(db, datos.unidad_id)
    try:
        cot = rx.cotizar_excursion(
            db, unidad, datos.fecha, _pedido(datos), datos.turno_id, datos.salida_id
        )
    except reservas.NoSePuedeReservar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return CotizacionExcursionOut(
        salida=_salida_out(cot.salida),
        lineas=[
            LineaPasajeroOut(
                concepto=ln.concepto, cantidad=ln.cantidad,
                precio_unitario=ln.precio_unitario, monto=ln.monto,
            )
            for ln in cot.precio.lineas
        ],
        personas=cot.precio.personas,
        lugares=cot.precio.lugares,
        subtotal=cot.precio.subtotal,
        cargo_servicio=cot.comision.cargo_viajero,
        total=cot.total_viajero,
        sena=cot.sena,
        a_pagar_ahora=cot.sena or cot.total_viajero,
        saldo_con_prestador=cot.total_viajero - cot.sena if cot.sena else None,
    )


@router.post("/reservas", response_model=ReservaOut, status_code=status.HTTP_201_CREATED)
def reservar(
    datos: NuevaReservaExcursion,
    usuario: Usuario = Depends(con_email_verificado),
    db: Session = Depends(get_db),
) -> ReservaOut:
    """Crea la reserva y retiene los lugares mientras se paga."""
    if not datos.acepta_terminos:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Hay que aceptar los términos y la política de cancelación para reservar",
        )
    unidad = _unidad(db, datos.unidad_id)
    exigir_telefono(db, usuario, datos.telefono)
    try:
        reserva = rx.crear_excursion(
            db, usuario, unidad, datos.fecha, _pedido(datos), datos.turno_id, datos.salida_id
        )
    except reservas.FechasTomadas as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except reservas.NoSePuedeReservar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    reserva.acepto_terminos_en = datetime.now(UTC)
    reserva.version_terminos = get_settings().version_terminos
    db.commit()
    return _reserva_out(reservas.traer(db, reserva.codigo), "viajero")
