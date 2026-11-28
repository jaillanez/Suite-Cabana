"""Traslados para el viajero (docs/06, etapas 2 y 4): buscar, ver la ficha,
comparar vehículos para un viaje, cuánto sale (y su vuelta), reservar y corregir
el vuelo.

Toda la cuenta la hace el backend (CLAUDE.md §3): la web muestra lo que devuelve
`cotizacion` y no recalcula nada.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
from app.api.v1.reservas import ReservaOut, _mia, _reserva_out, exigir_telefono
from app.core.config import get_settings
from app.core.database import get_db
from app.models import Publicacion, Unidad, Usuario
from app.models.enums import EstadoPublicacion, ModoReserva
from app.services import busqueda, politicas, reservas, traslados
from app.services import precios_traslado as pt
from app.services import reservas_traslado as rt
from app.services import salones as salones_svc
from app.services import traslados_viajero as svc
from app.services.privacidad import aproximar

router = APIRouter(prefix="/traslados", tags=["traslados"])


class ExtremoIn(BaseModel):
    """Un lugar del prestador (`lugar_id`) o un punto del mapa con su dirección."""

    lugar_id: uuid.UUID | None = None
    lat: Annotated[float | None, Field(default=None, ge=-90, le=90)] = None
    lon: Annotated[float | None, Field(default=None, ge=-180, le=180)] = None
    direccion: Annotated[str | None, Field(default=None, max_length=rt.DIRECCION_MAX)] = None


class ViajeIn(BaseModel):
    """Un viaje armado: de dónde, adónde, cuándo, quiénes y, si hay, la vuelta."""

    origen: ExtremoIn
    destino: ExtremoIn
    inicio: datetime
    pasajeros: Annotated[int, Field(ge=1, le=100)]
    valijas: Annotated[int, Field(default=0, ge=0, le=100)] = 0
    #: Con vuelta: el mismo vehículo, del destino al origen, a esta hora.
    vuelta_inicio: datetime | None = None
    vuelo_ida: Annotated[str | None, Field(default=None, max_length=rt.VUELO_MAX)] = None
    vuelo_vuelta: Annotated[str | None, Field(default=None, max_length=rt.VUELO_MAX)] = None
    notas: Annotated[str | None, Field(default=None, max_length=rt.NOTAS_MAX)] = None


class PedidoTraslado(ViajeIn):
    unidad_id: uuid.UUID


class PedidoOpciones(ViajeIn):
    publicacion_id: uuid.UUID


class NuevaReservaTraslado(PedidoTraslado):
    acepta_terminos: bool = False
    telefono: Annotated[str | None, Field(default=None, max_length=30)] = None


class LineaOut(BaseModel):
    concepto: str
    monto: Dinero


class ViajeOut(BaseModel):
    sentido: str
    origen: str
    destino: str
    cobro: str
    inicio: datetime
    llegada: datetime
    km: float | None
    lineas: list[LineaOut]
    subtotal: Dinero
    cargo_servicio: Dinero
    total: Dinero


class CotizacionTrasladoOut(BaseModel):
    viajes: list[ViajeOut]
    pasajeros: int
    valijas: int
    subtotal: Dinero
    cargo_servicio: Dinero
    total: Dinero
    sena: Dinero | None
    a_pagar_ahora: Dinero
    saldo_con_prestador: Dinero | None


class DatosViajeIn(BaseModel):
    """Lo que se corrige después de reservar. `None` deja el valor como está; un
    texto vacío lo borra."""

    vuelo_ida: Annotated[str | None, Field(default=None, max_length=rt.VUELO_MAX)] = None
    vuelo_vuelta: Annotated[str | None, Field(default=None, max_length=rt.VUELO_MAX)] = None
    notas: Annotated[str | None, Field(default=None, max_length=rt.NOTAS_MAX)] = None


def _unidad(db: Session, unidad_id: uuid.UUID) -> Unidad:
    """Un vehículo de un traslado publicado. Cualquier otra cosa es 404."""
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
        or unidad.publicacion.tipo_servicio.modo_reserva is not ModoReserva.TRAMO
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese traslado")
    return unidad


def _extremo(e: ExtremoIn) -> rt.Extremo:
    if (e.lat is None) != (e.lon is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "El punto necesita latitud y longitud"
        )
    punto = pt.Punto(e.lat, e.lon) if e.lat is not None else None
    return rt.Extremo(lugar_id=e.lugar_id, punto=punto, direccion=e.direccion)


def _pedido(d: ViajeIn) -> rt.Pedido:
    return rt.Pedido(
        origen=_extremo(d.origen), destino=_extremo(d.destino), inicio=d.inicio,
        pasajeros=d.pasajeros, valijas=d.valijas, vuelta_inicio=d.vuelta_inicio,
        vuelo_ida=d.vuelo_ida, vuelo_vuelta=d.vuelo_vuelta, notas=d.notas,
    )


def _cotizacion_out(cot: rt.CotizacionTraslado, datos: ViajeIn) -> CotizacionTrasladoOut:
    return CotizacionTrasladoOut(
        viajes=[
            ViajeOut(
                sentido=v.sentido, origen=v.origen, destino=v.destino, cobro=v.cobro,
                inicio=v.precio.inicio, llegada=v.precio.llegada,
                km=float(v.precio.km) if v.precio.km is not None else None,
                lineas=[LineaOut(concepto=ln.concepto, monto=ln.monto) for ln in v.precio.lineas],
                subtotal=v.precio.subtotal, cargo_servicio=v.comision.cargo_viajero,
                total=v.total,
            )
            for v in cot.viajes
        ],
        pasajeros=datos.pasajeros,
        valijas=datos.valijas,
        subtotal=cot.subtotal,
        cargo_servicio=cot.cargo_servicio,
        total=cot.total_viajero,
        sena=cot.sena,
        a_pagar_ahora=cot.sena or cot.total_viajero,
        saldo_con_prestador=cot.total_viajero - cot.sena if cot.sena else None,
    )


@router.post("/cotizacion", response_model=CotizacionTrasladoOut)
def cotizacion(
    datos: PedidoTraslado, db: Session = Depends(get_db)
) -> CotizacionTrasladoOut:
    """Cuánto sale el viaje (y la vuelta) en un vehículo y cuánto se paga ahora.
    No reserva nada."""
    unidad = _unidad(db, datos.unidad_id)
    try:
        cot = rt.cotizar_traslado(db, unidad, _pedido(datos))
    except reservas.NoSePuedeReservar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return _cotizacion_out(cot, datos)


@router.post("/reservas", response_model=ReservaOut, status_code=status.HTTP_201_CREATED)
def reservar(
    datos: NuevaReservaTraslado,
    usuario: Usuario = Depends(con_email_verificado),
    db: Session = Depends(get_db),
) -> ReservaOut:
    """Crea la reserva y retiene el vehículo (ida y vuelta) mientras se paga."""
    if not datos.acepta_terminos:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Hay que aceptar los términos y la política de cancelación para reservar",
        )
    unidad = _unidad(db, datos.unidad_id)
    exigir_telefono(db, usuario, datos.telefono)
    try:
        reserva = rt.crear_traslado(db, usuario, unidad, _pedido(datos))
    except reservas.FechasTomadas as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except reservas.NoSePuedeReservar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    reserva.acepto_terminos_en = datetime.now(UTC)
    reserva.version_terminos = get_settings().version_terminos
    db.commit()
    return _reserva_out(reservas.traer(db, reserva.codigo), "viajero")


@router.patch("/reservas/{codigo}/viaje", response_model=ReservaOut)
def cambiar_viaje(
    codigo: str,
    datos: DatosViajeIn,
    usuario: Usuario = Depends(con_email_verificado),
    db: Session = Depends(get_db),
) -> ReservaOut:
    """El viajero corrige el vuelo o las notas de los viajes que no salieron."""
    reserva = _mia(codigo, usuario, db)
    try:
        rt.cambiar_datos(db, reserva, datos.vuelo_ida, datos.vuelo_vuelta, datos.notas)
    except reservas.NoSePuedeReservar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except reservas.TransicionInvalida as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    db.commit()
    return _reserva_out(reservas.traer(db, reserva.codigo), "viajero")


# --- Buscar y ver (etapa 4) ---


class PrecioDesdeOut(BaseModel):
    monto: Dinero
    detalle: str


class RecorridoOut(BaseModel):
    origen: str
    destino: str
    precio: Dinero
    por_persona: bool
    duracion_minutos: int
    ambos_sentidos: bool


class TrasladoResultadoOut(BaseModel):
    slug: str
    titulo: str
    subtipo: str | None
    localidad: str
    provincia: str
    lat: float | None = Field(description="Aproximada (~1 km)")
    lon: float | None
    fotos: list[FotoOut]
    comodidades: list[str]
    vehiculos: int
    pasajeros_maximo: int
    valijas_maximo: int | None = Field(description="Nulo: algún vehículo no tiene límite")
    precio_desde: PrecioDesdeOut | None
    recorridos: list[str] = Field(description="Hasta 3, para la tarjeta: 'Aeropuerto → Centro'")
    por_km: bool
    confirmacion_inmediata: bool
    es_demo: bool


class BusquedaTrasladosOut(BaseModel):
    total: int
    pagina: int
    paginas: int
    resultados: list[TrasladoResultadoOut]


class DestinoTrasladoOut(BaseModel):
    nombre: str
    slug: str
    provincia: str
    traslados: int


class LugarFichaOut(BaseModel):
    id: uuid.UUID
    nombre: str


class PorKmOut(BaseModel):
    precio_km: Dinero
    bajada: Dinero
    minimo: Dinero
    radio_km: int | None


class RecargoOut(BaseModel):
    desde: str
    hasta: str
    porcentaje: Dinero


class VehiculoFichaOut(BaseModel):
    id: uuid.UUID
    nombre: str
    pasajeros: int
    valijas: int | None
    recorridos: list[RecorridoOut]
    por_km: PorKmOut | None
    recargo_nocturno: RecargoOut | None
    anticipacion_minima_horas: int


class TrasladoFichaOut(BaseModel):
    publicacion_id: uuid.UUID
    slug: str
    titulo: str
    descripcion: str
    para_tener_en_cuenta: str | None
    subtipo: str | None
    localidad: str
    localidad_slug: str
    provincia: str
    lat: float | None = Field(description="Aproximada (~1 km)")
    lon: float | None
    confirmacion_inmediata: bool
    porcentaje_sena: int | None
    es_demo: bool
    prestador: PrestadorOut
    politica_cancelacion: PoliticaOut | None
    fotos: list[FotoOut]
    comodidades: list[ComodidadOut]
    lugares: list[LugarFichaOut]
    vehiculos: list[VehiculoFichaOut]
    alojamientos_del_anfitrion: list[EnlaceOut]
    moneda: str = "ARS"


class OpcionOut(BaseModel):
    unidad_id: uuid.UUID
    nombre: str
    pasajeros: int
    valijas: int | None
    disponible: bool
    motivo: str | None = Field(description="Por qué no se puede, si no se puede")
    cotizacion: CotizacionTrasladoOut | None


def _recorrido_out(r: svc.Recorrido) -> RecorridoOut:
    return RecorridoOut(
        origen=r.origen, destino=r.destino, precio=r.precio, por_persona=r.por_persona,
        duracion_minutos=r.duracion_minutos, ambos_sentidos=r.ambos_sentidos,
    )


def _flecha(r: svc.Recorrido) -> str:
    return f"{r.origen} {'↔' if r.ambos_sentidos else '→'} {r.destino}"


@router.get("/buscar", response_model=BusquedaTrasladosOut)
def buscar(
    localidad: Annotated[str | None, Query(max_length=80)] = None,
    provincia: Annotated[str | None, Query(max_length=80)] = None,
    pasajeros: Annotated[int, Query(ge=1, le=100)] = 1,
    valijas: Annotated[int, Query(ge=0, le=200)] = 0,
    lugar: Annotated[str | None, Query(max_length=60)] = None,
    subtipo: Annotated[list[str] | None, Query(max_length=10)] = None,
    comodidad: Annotated[list[str] | None, Query(max_length=10)] = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=svc.POR_PAGINA_MAX)] = 24,
    db: Session = Depends(get_db),
) -> BusquedaTrasladosOut:
    """Traslados de un destino donde entran los pasajeros y las valijas. Si el
    vehículo está libre se sabe en la ficha, con el viaje armado (`opciones`)."""
    p = svc.buscar(
        db, localidad=localidad, provincia=provincia, pasajeros=pasajeros, valijas=valijas,
        lugar=lugar, subtipos=tuple(subtipo or ()), comodidades=tuple(comodidad or ()),
        pagina=pagina, por_pagina=por_pagina,
    )
    puntos = busqueda.coordenadas(db, {r.publicacion.id for r in p.resultados})
    return BusquedaTrasladosOut(
        total=p.total,
        pagina=p.pagina,
        paginas=p.paginas,
        resultados=[
            TrasladoResultadoOut(
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
                vehiculos=len(r.vehiculos),
                pasajeros_maximo=r.pasajeros_maximo,
                valijas_maximo=r.valijas_maximo,
                precio_desde=(
                    PrecioDesdeOut(monto=r.precio_desde.monto, detalle=r.precio_desde.detalle)
                    if r.precio_desde
                    else None
                ),
                recorridos=list(
                    dict.fromkeys(_flecha(x) for v in r.vehiculos for x in v.recorridos)
                )[:3],
                por_km=any(v.por_km for v in r.vehiculos),
                confirmacion_inmediata=r.publicacion.confirmacion_inmediata,
                es_demo=r.publicacion.es_demo,
            )
            for r in p.resultados
        ],
    )


@router.get("/destinos", response_model=list[DestinoTrasladoOut])
def destinos(db: Session = Depends(get_db)) -> list[DestinoTrasladoOut]:
    return [
        DestinoTrasladoOut(nombre=loc.nombre, slug=loc.slug, provincia=prov.nombre, traslados=n)
        for loc, prov, n in svc.destinos(db)
    ]


def _vehiculo_out(v: svc.Vehiculo) -> VehiculoFichaOut:
    t = v.tarifa
    reglas = traslados.reglas_de(t)
    recargo = None
    if reglas.recargo_nocturno_porcentaje > 0 and reglas.recargo_nocturno_desde:
        recargo = RecargoOut(
            desde=reglas.recargo_nocturno_desde.strftime("%H:%M"),
            hasta=reglas.recargo_nocturno_hasta.strftime("%H:%M"),
            porcentaje=reglas.recargo_nocturno_porcentaje,
        )
    return VehiculoFichaOut(
        id=v.unidad.id,
        nombre=v.unidad.nombre,
        pasajeros=v.unidad.capacidad,
        valijas=v.unidad.equipaje,
        recorridos=[_recorrido_out(r) for r in v.recorridos],
        por_km=(
            PorKmOut(
                precio_km=reglas.precio_km, bajada=reglas.bajada, minimo=reglas.minimo,
                radio_km=reglas.radio_km,
            )
            if reglas.precio_km is not None
            else None
        ),
        recargo_nocturno=recargo,
        anticipacion_minima_horas=reglas.anticipacion_minima_horas,
    )


@router.get("/ficha/{slug}", response_model=TrasladoFichaOut)
def ficha(slug: str, db: Session = Depends(get_db)) -> TrasladoFichaOut:
    """Todo sobre un traslado: lugares, vehículos, recorridos y reglas. Cuánto sale un
    viaje y si el vehículo está libre lo dice `opciones`."""
    try:
        p = svc.obtener(db, slug)
    except svc.NoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese traslado") from e
    lat, lon = busqueda.coordenadas(db, {p.id}).get(p.id, (None, None))
    politica = politicas.vigente(p)
    return TrasladoFichaOut(
        publicacion_id=p.id,
        slug=p.slug,
        titulo=p.titulo,
        descripcion=p.descripcion,
        para_tener_en_cuenta=p.reglas_casa,
        subtipo=p.subtipo.nombre if p.subtipo else None,
        localidad=p.localidad.nombre,
        localidad_slug=p.localidad.slug,
        provincia=p.localidad.provincia.nombre,
        lat=aproximar(lat),
        lon=aproximar(lon),
        confirmacion_inmediata=p.confirmacion_inmediata,
        porcentaje_sena=(
            p.porcentaje_sena if p.porcentaje_sena is not None else p.prestador.porcentaje_sena
        ) or None,
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
        # Solo el nombre: el punto exacto de la base puede ser la casa del prestador.
        lugares=[LugarFichaOut(id=lg.id, nombre=lg.nombre) for lg in svc.lugares(db, p)],
        vehiculos=[_vehiculo_out(v) for v in svc.vehiculos_de(db, [p]).get(p.id, [])],
        alojamientos_del_anfitrion=[
            EnlaceOut(titulo=x.titulo, slug=x.slug)
            for x in salones_svc.del_mismo_anfitrion(db, p.prestador_id, ModoReserva.NOCHES)
        ],
    )


@router.post("/opciones", response_model=list[OpcionOut])
def opciones(datos: PedidoOpciones, db: Session = Depends(get_db)) -> list[OpcionOut]:
    """Para un viaje armado, cada vehículo del prestador: cuánto sale y si está
    libre, o por qué no. No reserva nada."""
    p = db.scalar(
        svc._publicados().where(Publicacion.id == datos.publicacion_id).options(*svc._opciones())
    )
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese traslado")
    return [
        OpcionOut(
            unidad_id=o.vehiculo.id,
            nombre=o.vehiculo.nombre,
            pasajeros=o.vehiculo.capacidad,
            valijas=o.vehiculo.equipaje,
            disponible=o.disponible,
            motivo=o.motivo,
            cotizacion=_cotizacion_out(o.cotizacion, datos) if o.cotizacion else None,
        )
        for o in svc.opciones(db, p, _pedido(datos))
    ]
