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
from app.api.v1.publicaciones import Dinero, PoliticaOut
from app.api.v1.reservas import ReservaOut, _reserva_out, exigir_telefono
from app.core.config import get_settings
from app.core.database import get_db
from app.models import Publicacion, Unidad, Usuario
from app.models.enums import EstadoPublicacion, ModoReserva
from app.services import politicas, reservas, salidas
from app.services import reservas_excursion as rx

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
        precios=[
            PrecioPasajeroOut(
                id=c.id, nombre=c.nombre, descripcion=c.descripcion, edad_desde=c.edad_desde,
                edad_hasta=c.edad_hasta, precio=c.precio, ocupa_lugar=c.ocupa_lugar,
            )
            for c in rx.categorias(db, unidad)
        ],
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
