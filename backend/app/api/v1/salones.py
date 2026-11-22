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
from app.api.v1.publicaciones import Dinero
from app.api.v1.reservas import ReservaOut, _reserva_out
from app.core.config import get_settings
from app.core.database import get_db
from app.models import Localidad, Publicacion, Unidad, Usuario
from app.models.enums import EstadoPublicacion, ModoReserva
from app.services import horarios, reservas
from app.services import precios_eventos as pe

router = APIRouter(prefix="/salones", tags=["salones"])


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


class PedidoEvento(BaseModel):
    unidad_id: uuid.UUID
    dia: date
    invitados: Annotated[int, Field(ge=1, le=5000)]
    franja_id: uuid.UUID | None = None
    hora_inicio: time | None = None
    horas: Annotated[int | None, Field(ge=1, le=24)] = None
    adicionales: list[uuid.UUID] = Field(default_factory=list, max_length=30)


class NuevaReservaEvento(PedidoEvento):
    acepta_terminos: bool = False


class LineaOut(BaseModel):
    concepto: str
    monto: Dinero


class CotizacionEventoOut(BaseModel):
    inicio: datetime
    fin: datetime
    invitados: int
    alquiler: Dinero
    lineas: list[LineaOut]
    subtotal: Dinero = Field(description="Lo que cobra el anfitrión")
    cargo_servicio: Dinero
    total: Dinero = Field(description="Lo que cuesta el evento, todo incluido")
    sena: Dinero | None = Field(description="Lo que se paga online para reservar")
    a_pagar_ahora: Dinero
    saldo_con_anfitrion: Dinero | None


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


def _cotizar(db: Session, datos: PedidoEvento) -> reservas.CotizacionEvento:
    unidad = _unidad(db, datos.unidad_id)
    try:
        return reservas.cotizar_evento(
            db, unidad, datos.dia, datos.invitados,
            franja_id=datos.franja_id, hora_inicio=datos.hora_inicio, horas=datos.horas,
            adicionales=datos.adicionales,
        )
    except reservas.NoSePuedeReservar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


# --- Endpoints ---


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
    """Cuánto sale el evento y cuánto se paga ahora. No reserva nada."""
    cot = _cotizar(db, datos)
    a_pagar = cot.sena or cot.total_viajero
    return CotizacionEventoOut(
        inicio=cot.precio.inicio,
        fin=cot.precio.fin,
        invitados=cot.precio.invitados,
        alquiler=cot.precio.alquiler,
        lineas=[LineaOut(concepto=ln.concepto, monto=ln.monto) for ln in cot.precio.lineas],
        subtotal=cot.precio.subtotal,
        cargo_servicio=cot.comision.cargo_viajero,
        total=cot.total_viajero,
        sena=cot.sena,
        a_pagar_ahora=a_pagar,
        saldo_con_anfitrion=(cot.total_viajero - cot.sena) if cot.sena else None,
    )


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
            adicionales=datos.adicionales,
        )
    except reservas.FechasTomadas as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except reservas.NoSePuedeReservar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    reserva.acepto_terminos_en = datetime.now(UTC)
    reserva.version_terminos = get_settings().version_terminos
    db.commit()
    return _reserva_out(reservas.traer(db, reserva.codigo))
