"""Traslados para el viajero (docs/06, etapa 2): cuánto sale un viaje (y su
vuelta), reservar y corregir el vuelo.

Toda la cuenta la hace el backend (CLAUDE.md §3): la web muestra lo que devuelve
`cotizacion` y no recalcula nada.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import con_email_verificado
from app.api.v1.publicaciones import Dinero
from app.api.v1.reservas import ReservaOut, _mia, _reserva_out, exigir_telefono
from app.core.config import get_settings
from app.core.database import get_db
from app.models import Publicacion, Unidad, Usuario
from app.models.enums import EstadoPublicacion, ModoReserva
from app.services import precios_traslado as pt
from app.services import reservas
from app.services import reservas_traslado as rt

router = APIRouter(prefix="/traslados", tags=["traslados"])


class ExtremoIn(BaseModel):
    """Un lugar del prestador (`lugar_id`) o un punto del mapa con su dirección."""

    lugar_id: uuid.UUID | None = None
    lat: Annotated[float | None, Field(default=None, ge=-90, le=90)] = None
    lon: Annotated[float | None, Field(default=None, ge=-180, le=180)] = None
    direccion: Annotated[str | None, Field(default=None, max_length=rt.DIRECCION_MAX)] = None


class PedidoTraslado(BaseModel):
    unidad_id: uuid.UUID
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


def _pedido(d: PedidoTraslado) -> rt.Pedido:
    return rt.Pedido(
        origen=_extremo(d.origen), destino=_extremo(d.destino), inicio=d.inicio,
        pasajeros=d.pasajeros, valijas=d.valijas, vuelta_inicio=d.vuelta_inicio,
        vuelo_ida=d.vuelo_ida, vuelo_vuelta=d.vuelo_vuelta, notas=d.notas,
    )


@router.post("/cotizacion", response_model=CotizacionTrasladoOut)
def cotizacion(
    datos: PedidoTraslado, db: Session = Depends(get_db)
) -> CotizacionTrasladoOut:
    """Cuánto sale el viaje (y la vuelta) y cuánto se paga ahora. No reserva nada."""
    unidad = _unidad(db, datos.unidad_id)
    try:
        cot = rt.cotizar_traslado(db, unidad, _pedido(datos))
    except reservas.NoSePuedeReservar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
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
