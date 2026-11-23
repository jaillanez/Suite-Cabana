"""Salones de eventos para el viajero (docs/04 §5): qué está libre un día, cuánto
sale un evento, y reservarlo con seña.

Toda la cuenta la hace el backend (CLAUDE.md §3): el frontend muestra el
desglose que devuelve `cotizacion` y no recalcula nada.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
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
from app.api.v1.reservas import ReservaOut, _reserva_out
from app.core.config import get_settings
from app.core.database import get_db
from app.models import Localidad, Publicacion, Unidad, Usuario
from app.models.enums import EstadoPublicacion, ModoReserva
from app.services import busqueda, horarios, reservas
from app.services import precios_eventos as pe
from app.services import salones as svc
from app.services.privacidad import aproximar

router = APIRouter(prefix="/salones", tags=["salones"])

#: Cuántas unidades del anfitrión se ofrecen, como mucho, para sumar al salón.
TOPE_SUMABLES = 24


# --- Formas ---


class FranjaOut(BaseModel):
    id: uuid.UUID
    nombre: str
    inicio: datetime
    fin: datetime
    precio: Dinero
    libre: bool


class PorHorasOut(BaseModel):
    precio_hora: Dinero
    horas_minimas: int
    apertura: datetime
    cierre: datetime
    recargo_nocturno_desde: str | None
    recargo_nocturno_porcentaje: Decimal


class TramoOcupado(BaseModel):
    inicio: datetime
    fin: datetime


class AdicionalOut(BaseModel):
    id: uuid.UUID
    nombre: str
    descripcion: str | None
    precio: Dinero
    por_persona: bool


class DisponibilidadOut(BaseModel):
    unidad_id: uuid.UUID
    dia: date
    capacidad: int
    capacidad_sentados: int | None
    preparacion_minutos: int
    franjas: list[FranjaOut]
    por_horas: PorHorasOut | None
    ocupado: list[TramoOcupado] = Field(
        description="Lo tomado ese día, incluido el tiempo de preparación"
    )
    adicionales: list[AdicionalOut]


class EstadiaPedido(BaseModel):
    """Noches en una cabaña del mismo anfitrión, sumadas al evento (paquete)."""

    unidad_id: uuid.UUID
    desde: date
    hasta: date
    adultos: Annotated[int, Field(ge=1, le=30)] = 2
    menores: Annotated[int, Field(ge=0, le=30)] = 0
    mascotas: Annotated[int, Field(ge=0, le=10)] = 0


class PedidoEvento(BaseModel):
    unidad_id: uuid.UUID
    dia: date
    invitados: Annotated[int, Field(ge=1, le=5000)]
    franja_id: uuid.UUID | None = None
    hora_inicio: time | None = None
    horas: Annotated[int | None, Field(ge=1, le=24)] = None
    adicionales: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    alojamientos: list[EstadiaPedido] = Field(
        default_factory=list, max_length=reservas.MAX_ESTADIAS
    )


class NuevaReservaEvento(PedidoEvento):
    acepta_terminos: bool = False


class LineaOut(BaseModel):
    concepto: str
    monto: Dinero


class EstadiaCotizadaOut(BaseModel):
    unidad_id: uuid.UUID
    unidad: str
    publicacion: str
    desde: date
    hasta: date
    noches: int
    personas: int
    subtotal: Dinero
    cargo_servicio: Dinero
    total: Dinero


class CotizacionEventoOut(BaseModel):
    inicio: datetime
    fin: datetime
    invitados: int
    alquiler: Dinero
    lineas: list[LineaOut]
    subtotal: Dinero = Field(description="Lo que cobra el anfitrión por el evento")
    cargo_servicio: Dinero = Field(description="Cargo de servicio del evento")
    total_evento: Dinero = Field(description="El evento solo, todo incluido")
    alojamientos: list[EstadiaCotizadaOut] = Field(
        description="Las noches sumadas al evento (paquete)"
    )
    total: Dinero = Field(description="Lo que cuesta todo, evento y alojamientos")
    sena: Dinero | None = Field(description="Lo que se paga online para reservar")
    a_pagar_ahora: Dinero
    saldo_con_anfitrion: Dinero | None


class AlojamientoSumableOut(BaseModel):
    """Una unidad del mismo anfitrión que se puede sumar al evento."""

    unidad_id: uuid.UUID
    unidad: str
    publicacion: str
    slug: str
    capacidad: int
    foto: str | None
    libre: bool
    total: Dinero | None = Field(description="Cuánto suma, si está libre")
    motivo: str | None = Field(description="Por qué no se puede sumar")


class PrecioDesdeOut(BaseModel):
    monto: Dinero
    detalle: str


class SalonResultadoOut(BaseModel):
    slug: str
    titulo: str
    subtipo: str | None
    localidad: str
    provincia: str
    lat: float | None = Field(description="Aproximada (~1 km)")
    lon: float | None
    fotos: list[FotoOut]
    comodidades: list[str]
    capacidad_maxima: int
    sentados_maximo: int | None
    precio_desde: PrecioDesdeOut | None
    confirmacion_inmediata: bool
    disponible: bool | None = Field(description="null si no se pidió día")
    es_demo: bool


class BusquedaSalonesOut(BaseModel):
    total: int
    pagina: int
    paginas: int
    resultados: list[SalonResultadoOut]


class DestinoSalonOut(BaseModel):
    nombre: str
    slug: str
    provincia: str
    salones: int


class FranjaFichaOut(BaseModel):
    id: uuid.UUID
    nombre: str
    hora_inicio: str
    hora_fin: str
    precio: Dinero
    termina_al_dia_siguiente: bool


class PorHorasFichaOut(BaseModel):
    precio_hora: Dinero
    horas_minimas: int
    hora_apertura: str
    hora_cierre: str


class EspacioOut(BaseModel):
    id: uuid.UUID
    nombre: str
    capacidad: int
    capacidad_sentados: int | None
    capacidad_base: int | None
    cargo_persona_extra: Dinero
    preparacion_minutos: int
    franjas: list[FranjaFichaOut]
    por_horas: PorHorasFichaOut | None
    adicionales: list[AdicionalOut]


class SalonFichaOut(BaseModel):
    publicacion_id: uuid.UUID
    slug: str
    titulo: str
    descripcion: str
    reglas: str | None
    subtipo: str | None
    localidad: str
    localidad_slug: str
    provincia: str
    zona: str | None
    lat: float | None = Field(description="Aproximada (~1 km): la exacta, con la reserva")
    lon: float | None
    confirmacion_inmediata: bool
    porcentaje_sena: int | None
    es_demo: bool
    prestador: PrestadorOut
    politica_cancelacion: PoliticaOut | None
    fotos: list[FotoOut]
    comodidades: list[ComodidadOut]
    espacios: list[EspacioOut]
    alojamientos_del_anfitrion: list[EnlaceOut]
    moneda: str = "ARS"


# --- Helpers ---


def _unidad(db: Session, unidad_id: uuid.UUID) -> Unidad:
    unidad = db.scalar(
        select(Unidad)
        .where(Unidad.id == unidad_id)
        .options(
            selectinload(Unidad.franjas),
            selectinload(Unidad.tarifa_horaria),
            selectinload(Unidad.adicionales),
            selectinload(Unidad.publicacion).selectinload(Publicacion.prestador),
            selectinload(Unidad.publicacion).selectinload(Publicacion.tipo_servicio),
            selectinload(Unidad.publicacion).selectinload(Publicacion.politica_cancelacion),
            selectinload(Unidad.publicacion)
            .selectinload(Publicacion.localidad)
            .selectinload(Localidad.provincia),
        )
    )
    p = unidad.publicacion if unidad else None
    if (
        unidad is None
        or not unidad.activa
        or p.estado is not EstadoPublicacion.APROBADA
        or p.tipo_servicio.modo_reserva is not ModoReserva.HORAS
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese salón")
    return unidad


def _estadias(db: Session, pedidos: list[EstadiaPedido]) -> list[reservas.Estadia]:
    """Las unidades de alojamiento pedidas. Que sean del mismo anfitrión, que se
    reserven por noches y que estén libres lo decide el motor de reservas."""
    if not pedidos:
        return []
    unidades = {
        u.id: u
        for u in db.scalars(
            select(Unidad)
            .where(Unidad.id.in_({e.unidad_id for e in pedidos}))
            .options(
                selectinload(Unidad.tarifas),
                selectinload(Unidad.publicacion).selectinload(Publicacion.prestador),
                selectinload(Unidad.publicacion).selectinload(Publicacion.tipo_servicio),
                selectinload(Unidad.publicacion).selectinload(Publicacion.politica_cancelacion),
                selectinload(Unidad.publicacion)
                .selectinload(Publicacion.localidad)
                .selectinload(Localidad.provincia),
            )
        )
    }
    faltan = [e for e in pedidos if e.unidad_id not in unidades]
    if faltan:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "No encontramos uno de los alojamientos"
        )
    return [
        reservas.Estadia(
            unidades[e.unidad_id], e.desde, e.hasta, e.adultos, e.menores, e.mascotas
        )
        for e in pedidos
    ]


def _cotizar(db: Session, datos: PedidoEvento) -> reservas.CotizacionPaquete:
    unidad = _unidad(db, datos.unidad_id)
    try:
        return reservas.cotizar_paquete(
            db, unidad, datos.dia, datos.invitados,
            franja_id=datos.franja_id, hora_inicio=datos.hora_inicio, horas=datos.horas,
            adicionales=datos.adicionales, estadias=_estadias(db, datos.alojamientos),
        )
    except reservas.NoSePuedeReservar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


# --- Endpoints ---


@router.get("/buscar", response_model=BusquedaSalonesOut)
def buscar(
    localidad: Annotated[str | None, Query(max_length=80)] = None,
    provincia: Annotated[str | None, Query(max_length=80)] = None,
    dia: date | None = None,
    invitados: Annotated[int, Query(ge=1, le=5000)] = 1,
    subtipo: Annotated[list[str] | None, Query()] = None,
    comodidad: Annotated[list[str] | None, Query()] = None,
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=svc.POR_PAGINA_MAX)] = 24,
    db: Session = Depends(get_db),
) -> BusquedaSalonesOut:
    """Salones por destino e invitados. Con día, solo los que tienen lugar ese día."""
    if dia is not None and dia < date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ese día ya pasó")
    p = svc.buscar(
        db, localidad=localidad, provincia=provincia, dia=dia, invitados=invitados,
        subtipos=tuple(subtipo or ()), comodidades=tuple(comodidad or ()),
        pagina=pagina, por_pagina=por_pagina,
    )
    puntos = busqueda.coordenadas(db, {r.publicacion.id for r in p.resultados})
    return BusquedaSalonesOut(
        total=p.total,
        pagina=p.pagina,
        paginas=p.paginas,
        resultados=[
            SalonResultadoOut(
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
                capacidad_maxima=r.capacidad_maxima,
                sentados_maximo=r.sentados_maximo,
                precio_desde=(
                    PrecioDesdeOut(monto=r.precio_desde.monto, detalle=r.precio_desde.detalle)
                    if r.precio_desde
                    else None
                ),
                confirmacion_inmediata=r.publicacion.confirmacion_inmediata,
                disponible=r.disponible,
                es_demo=r.publicacion.es_demo,
            )
            for r in p.resultados
        ],
    )


@router.get("/destinos", response_model=list[DestinoSalonOut])
def destinos(db: Session = Depends(get_db)) -> list[DestinoSalonOut]:
    return [
        DestinoSalonOut(nombre=loc.nombre, slug=loc.slug, provincia=prov.nombre, salones=n)
        for loc, prov, n in svc.destinos(db)
    ]


@router.get("/ficha/{slug}", response_model=SalonFichaOut)
def ficha(slug: str, db: Session = Depends(get_db)) -> SalonFichaOut:
    """Todo sobre un salón. Qué está libre un día lo dice `disponibilidad`."""
    try:
        p = svc.obtener(db, slug)
    except svc.NoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese salón") from e
    lat, lon = busqueda.coordenadas(db, {p.id}).get(p.id, (None, None))
    politica = p.politica_cancelacion

    def hora(t: time) -> str:
        return t.strftime("%H:%M")

    return SalonFichaOut(
        publicacion_id=p.id,
        slug=p.slug,
        titulo=p.titulo,
        descripcion=p.descripcion,
        reglas=p.reglas_casa,
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
        es_demo=p.es_demo,
        prestador=PrestadorOut(
            razon_social=p.prestador.razon_social,
            verificado=p.prestador.verificado,
            publica_desde=p.prestador.fecha_alta.year,
        ),
        politica_cancelacion=(
            PoliticaOut(
                codigo=politica.codigo, nombre=politica.nombre,
                descripcion=politica.descripcion, tramos=politica.tramos,
            )
            if politica
            else None
        ),
        fotos=[
            FotoOut(url=f.url, descripcion=f.descripcion)
            for f in sorted(p.fotos, key=lambda x: x.orden)
        ],
        comodidades=[ComodidadOut(codigo=c.codigo, nombre=c.nombre) for c in p.comodidades],
        espacios=[
            EspacioOut(
                id=u.id,
                nombre=u.nombre,
                capacidad=u.capacidad,
                capacidad_sentados=u.capacidad_sentados,
                capacidad_base=u.capacidad_base,
                cargo_persona_extra=u.cargo_persona_extra,
                preparacion_minutos=u.preparacion_minutos or 0,
                franjas=[
                    FranjaFichaOut(
                        id=f.id, nombre=f.nombre, hora_inicio=hora(f.hora_inicio),
                        hora_fin=hora(f.hora_fin), precio=f.precio,
                        termina_al_dia_siguiente=f.hora_fin <= f.hora_inicio,
                    )
                    for f in sorted(u.franjas, key=lambda x: x.hora_inicio)
                    if f.activa
                ],
                por_horas=(
                    PorHorasFichaOut(
                        precio_hora=u.tarifa_horaria.precio_hora,
                        horas_minimas=u.tarifa_horaria.horas_minimas,
                        hora_apertura=hora(u.tarifa_horaria.hora_apertura),
                        hora_cierre=hora(u.tarifa_horaria.hora_cierre),
                    )
                    if reservas.tarifa_horas(u)
                    else None
                ),
                adicionales=[
                    AdicionalOut(
                        id=a.id, nombre=a.nombre, descripcion=a.descripcion, precio=a.precio,
                        por_persona=a.por_persona,
                    )
                    for a in u.adicionales
                    if a.activo
                ],
            )
            for u in svc.espacios(p)
        ],
        alojamientos_del_anfitrion=[
            EnlaceOut(titulo=x.titulo, slug=x.slug)
            for x in svc.del_mismo_anfitrion(db, p.prestador_id, ModoReserva.NOCHES)
        ],
    )


@router.get("/unidades/{unidad_id}/disponibilidad", response_model=DisponibilidadOut)
def disponibilidad(
    unidad_id: uuid.UUID,
    dia: Annotated[date, Query(description="Día del evento")],
    db: Session = Depends(get_db),
) -> DisponibilidadOut:
    """Turnos con su precio y si están libres, el horario por horas y lo ocupado.

    Muestra lo ocupado sin decir por quién ni por qué: al viajero le alcanza con
    saber que no está libre.
    """
    unidad = _unidad(db, unidad_id)
    franjas = [reservas.franja_plana(f) for f in unidad.franjas if f.activa]
    tarifa = reservas.tarifa_horas(unidad)
    salon = reservas.salon_plano(unidad)
    preparacion = timedelta(minutes=salon.preparacion_minutos)

    # La ventana a mirar: del inicio más temprano al fin más tardío de ese día.
    rangos = [f.rango(dia) for f in franjas] + ([tarifa.atencion(dia)] if tarifa else [])
    if rangos:
        desde = min(r[0] for r in rangos)
        hasta = max(r[1] for r in rangos) + preparacion
    else:
        desde = pe.en_hora(dia, time(0, 0))
        hasta = desde + timedelta(days=1)
    ahora = datetime.now(UTC)

    return DisponibilidadOut(
        unidad_id=unidad.id,
        dia=dia,
        capacidad=unidad.capacidad,
        capacidad_sentados=unidad.capacidad_sentados,
        preparacion_minutos=salon.preparacion_minutos,
        franjas=[
            FranjaOut(
                id=uuid.UUID(f.id),
                nombre=f.nombre,
                inicio=(r := f.rango(dia))[0],
                fin=r[1],
                precio=pe.precio_del_dia(f.precio, f.precios_dia_semana, dia),
                libre=r[0] > ahora
                and horarios.libre(db, unidad.id, r[0], r[1] + preparacion),
            )
            for f in sorted(franjas, key=lambda f: f.rango(dia)[0])
        ],
        por_horas=(
            PorHorasOut(
                precio_hora=pe.precio_del_dia(
                    tarifa.precio_hora, tarifa.precios_dia_semana, dia
                ),
                horas_minimas=tarifa.horas_minimas,
                apertura=tarifa.atencion(dia)[0],
                cierre=tarifa.atencion(dia)[1],
                recargo_nocturno_desde=(
                    tarifa.recargo_nocturno_desde.strftime("%H:%M")
                    if tarifa.recargo_nocturno_desde
                    else None
                ),
                recargo_nocturno_porcentaje=tarifa.recargo_nocturno_porcentaje,
            )
            if tarifa
            else None
        ),
        ocupado=[
            TramoOcupado(inicio=o.inicio, fin=o.fin)
            for o in horarios.ocupados(db, unidad.id, desde, hasta)
        ],
        adicionales=[
            AdicionalOut(
                id=a.id, nombre=a.nombre, descripcion=a.descripcion, precio=a.precio,
                por_persona=a.por_persona,
            )
            for a in unidad.adicionales
            if a.activo
        ],
    )


@router.post("/cotizacion", response_model=CotizacionEventoOut)
def cotizacion(datos: PedidoEvento, db: Session = Depends(get_db)) -> CotizacionEventoOut:
    """Cuánto sale el evento (y lo que se le sume) y cuánto se paga ahora. No
    reserva nada."""
    paquete = _cotizar(db, datos)
    cot = paquete.evento
    return CotizacionEventoOut(
        inicio=cot.precio.inicio,
        fin=cot.precio.fin,
        invitados=cot.precio.invitados,
        alquiler=cot.precio.alquiler,
        lineas=[LineaOut(concepto=ln.concepto, monto=ln.monto) for ln in cot.precio.lineas],
        subtotal=cot.precio.subtotal,
        cargo_servicio=cot.comision.cargo_viajero,
        total_evento=cot.total_viajero,
        alojamientos=[
            EstadiaCotizadaOut(
                unidad_id=e.unidad.id,
                unidad=e.unidad.nombre,
                publicacion=e.unidad.publicacion.titulo,
                desde=e.fecha_inicio,
                hasta=e.fecha_fin,
                noches=c.noches,
                personas=e.personas + e.menores,
                subtotal=c.precio.subtotal,
                cargo_servicio=c.comision.cargo_viajero,
                total=c.total_viajero,
            )
            for e, c in paquete.estadias
        ],
        total=paquete.total_viajero,
        sena=paquete.sena,
        a_pagar_ahora=paquete.sena or paquete.total_viajero,
        saldo_con_anfitrion=(
            paquete.total_viajero - paquete.sena if paquete.sena else None
        ),
    )


@router.get(
    "/unidades/{unidad_id}/alojamientos", response_model=list[AlojamientoSumableOut]
)
def alojamientos_sumables(
    unidad_id: uuid.UUID,
    desde: date,
    hasta: date,
    personas: Annotated[int, Query(ge=1, le=30)] = 2,
    db: Session = Depends(get_db),
) -> list[AlojamientoSumableOut]:
    """Las cabañas del mismo anfitrión que el salón, con su precio para esas
    noches y si están libres: lo que se puede sumar al evento (docs/04 S11)."""
    salon = _unidad(db, unidad_id)
    if not desde < hasta or (hasta - desde).days > reservas.MAX_NOCHES_PAQUETE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Elegí entre 1 y {reservas.MAX_NOCHES_PAQUETE} noches",
        )
    if desde < date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Esa fecha ya pasó")
    publicaciones = svc.del_mismo_anfitrion(
        db, salon.publicacion.prestador_id, ModoReserva.NOCHES
    )
    # Es público y cotiza cada unidad: el costo de una llamada tiene techo
    # aunque el anfitrión cargue muchas unidades.
    unidades = [
        (p, u)
        for p in publicaciones
        for u in sorted(p.unidades, key=lambda x: x.nombre)
        if u.activa
    ][:TOPE_SUMABLES]
    salida: list[AlojamientoSumableOut] = []
    for p, u in unidades:
        libre = reservas._libre(db, u.id, desde, hasta)
        total, motivo = None, None
        if not libre:
            motivo = "Ocupada esas noches"
        else:
            try:
                total = reservas.cotizar(
                    db, u, desde, hasta, min(personas, u.capacidad)
                ).total_viajero
            except reservas.NoSePuedeReservar as e:
                motivo = str(e)
        salida.append(
            AlojamientoSumableOut(
                unidad_id=u.id,
                unidad=u.nombre,
                publicacion=p.titulo,
                slug=p.slug,
                capacidad=u.capacidad,
                foto=p.fotos[0].url if p.fotos else None,
                libre=libre and total is not None,
                total=total,
                motivo=motivo,
            )
        )
    # Primero lo que se puede sumar; lo ocupado queda abajo, con su motivo.
    salida.sort(key=lambda x: not x.libre)
    return salida


@router.post("/reservas", response_model=ReservaOut, status_code=status.HTTP_201_CREATED)
def reservar(
    datos: NuevaReservaEvento,
    usuario: Usuario = Depends(con_email_verificado),
    db: Session = Depends(get_db),
) -> ReservaOut:
    """Crea la reserva del evento y retiene el horario mientras se paga la seña."""
    if not datos.acepta_terminos:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Hay que aceptar los términos y la política de cancelación para reservar",
        )
    unidad = _unidad(db, datos.unidad_id)
    try:
        reserva = reservas.crear_evento(
            db, usuario, unidad, datos.dia, datos.invitados,
            franja_id=datos.franja_id, hora_inicio=datos.hora_inicio, horas=datos.horas,
            adicionales=datos.adicionales, estadias=_estadias(db, datos.alojamientos),
        )
    except reservas.FechasTomadas as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except reservas.NoSePuedeReservar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    reserva.acepto_terminos_en = datetime.now(UTC)
    reserva.version_terminos = get_settings().version_terminos
    db.commit()
    return _reserva_out(reservas.traer(db, reserva.codigo))
