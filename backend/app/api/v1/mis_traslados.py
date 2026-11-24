"""Traslados del prestador (docs/06, etapa 3): lugares, tramos fijos y la tarifa y
reglas de cada vehículo.

Vive bajo `/mis-publicaciones/{id}` como el resto del editor y cada cambio
devuelve la publicación entera (lo que pinta el editor). La agenda de cada
vehículo es la misma que la de un espacio de salón (`agenda-horaria`).

Nada se borra de verdad: un lugar o un tramo que ya se usó en una reserva queda
en su desglose, y se desactiva. Volver a cargar el mismo lo reactiva.
"""

from __future__ import annotations

import uuid
from datetime import time
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import prestador_actual
from app.api.v1.mis_publicaciones import (
    Precio,
    PublicacionOut,
    _mia,
    _respuesta,
    _unidad_de,
)
from app.core.database import get_db
from app.models import LugarTraslado, Prestador, Publicacion, TarifaTraslado, TramoTraslado, Unidad
from app.models.enums import ModoReserva

router = APIRouter(prefix="/mis-publicaciones", tags=["mis traslados"])

MAX_LUGARES = 40
MAX_TRAMOS = 60

Monto = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]


# --- Formas ---


class NuevoLugar(BaseModel):
    nombre: Annotated[str, Field(min_length=2, max_length=120)]
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]
    es_base: bool = False


class CambioLugar(BaseModel):
    nombre: Annotated[str | None, Field(default=None, min_length=2, max_length=120)] = None
    lat: Annotated[float | None, Field(default=None, ge=-90, le=90)] = None
    lon: Annotated[float | None, Field(default=None, ge=-180, le=180)] = None
    es_base: bool | None = None

    @model_validator(mode="after")
    def _punto_entero(self) -> CambioLugar:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("El punto necesita latitud y longitud")
        return self


class NuevoTramo(BaseModel):
    origen_id: uuid.UUID
    destino_id: uuid.UUID
    precio: Precio
    por_persona: bool = False
    duracion_minutos: Annotated[int, Field(ge=5, le=2880)]
    ambos_sentidos: bool = True

    @model_validator(mode="after")
    def _distintos(self) -> NuevoTramo:
        if self.origen_id == self.destino_id:
            raise ValueError("El origen y el destino tienen que ser distintos")
        return self


class TarifaTrasladoIn(BaseModel):
    """La tarifa por km y las reglas del vehículo. Sin `precio_km`, el vehículo
    cobra solo los tramos fijos."""

    precio_km: Precio | None = None
    bajada: Monto = Decimal(0)
    minimo: Monto = Decimal(0)
    radio_km: Annotated[int | None, Field(default=None, ge=1, le=2000)] = None
    factor_ruta: Annotated[Decimal, Field(ge=1, le=3, decimal_places=2)] = Decimal("1.3")
    velocidad_kmh: Annotated[int, Field(ge=10, le=150)] = 60
    recargo_nocturno_desde: time | None = None
    recargo_nocturno_hasta: time | None = None
    recargo_nocturno_porcentaje: Annotated[
        Decimal, Field(ge=0, le=200, decimal_places=2)
    ] = Decimal(0)
    vuelve_a_base: bool = True
    anticipacion_minima_horas: Annotated[int, Field(ge=0, le=720)] = 12

    @model_validator(mode="after")
    def _recargo_completo(self) -> TarifaTrasladoIn:
        desde, hasta = self.recargo_nocturno_desde, self.recargo_nocturno_hasta
        if self.recargo_nocturno_porcentaje > 0:
            if desde is None or hasta is None:
                raise ValueError("El recargo nocturno necesita desde qué hora y hasta cuál")
            if desde == hasta:
                raise ValueError("El recargo nocturno no puede empezar y terminar a la misma hora")
        return self


# --- Ayudantes ---


def _de_traslados(db: Session, publicacion_id, prestador) -> Publicacion:
    p = _mia(publicacion_id, prestador, db, editable=True)
    if p.tipo_servicio.modo_reserva is not ModoReserva.TRAMO:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esto es para traslados: lugares, tramos y vehículos"
        )
    return p


def _bloquear(db: Session, modelo, id_) -> None:
    """Serializa los altas de una misma publicación o vehículo: sin esto, pedidos
    simultáneos cuentan antes de que el otro inserte y pasan juntos el tope."""
    db.execute(select(modelo.id).where(modelo.id == id_).with_for_update())


def _punto(lat: float, lon: float) -> str:
    return f"SRID=4326;POINT({lon} {lat})"


def _lugar_de(db: Session, p: Publicacion, lugar_id: uuid.UUID) -> LugarTraslado:
    lugar = db.get(LugarTraslado, lugar_id)
    if lugar is None or lugar.publicacion_id != p.id or not lugar.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese lugar")
    return lugar


def _activos(db: Session, p: Publicacion) -> list[LugarTraslado]:
    return list(
        db.scalars(
            select(LugarTraslado).where(
                LugarTraslado.publicacion_id == p.id, LugarTraslado.activo.is_(True)
            )
        )
    )


def _una_sola_base(db: Session, p: Publicacion, base: LugarTraslado) -> None:
    for otro in _activos(db, p):
        if otro.id != base.id:
            otro.es_base = False


def _vehiculo(db: Session, p: Publicacion, unidad_id: uuid.UUID) -> Unidad:
    return _unidad_de(db, p, unidad_id)


# --- Lugares ---


@router.post("/{publicacion_id}/lugares-traslado", response_model=PublicacionOut, status_code=201)
def crear_lugar(
    publicacion_id: uuid.UUID,
    datos: NuevoLugar,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    """Un punto con nombre: "Aeropuerto", "Terminal", "Centro"."""
    p = _de_traslados(db, publicacion_id, prestador)
    _bloquear(db, Publicacion, p.id)
    nombre = datos.nombre.strip()
    activos = _activos(db, p)
    if len(activos) >= MAX_LUGARES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Hasta {MAX_LUGARES} lugares")
    if any(x.nombre.casefold() == nombre.casefold() for x in activos):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay un lugar con ese nombre")
    # El mismo nombre dado de baja antes: se reactiva (el nombre es único).
    lugar = db.scalar(
        select(LugarTraslado).where(
            LugarTraslado.publicacion_id == p.id, LugarTraslado.nombre == nombre
        )
    )
    if lugar is None:
        lugar = LugarTraslado(publicacion_id=p.id, nombre=nombre)
        db.add(lugar)
    lugar.activo = True
    lugar.ubicacion = _punto(datos.lat, datos.lon)
    lugar.es_base = datos.es_base
    db.flush()
    if datos.es_base:
        _una_sola_base(db, p, lugar)
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.patch("/{publicacion_id}/lugares-traslado/{lugar_id}", response_model=PublicacionOut)
def editar_lugar(
    publicacion_id: uuid.UUID,
    lugar_id: uuid.UUID,
    cambios: CambioLugar,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    """Mover el punto, renombrarlo o marcarlo como base. Las reservas ya hechas
    guardaron su precio y sus nombres: no cambian."""
    p = _de_traslados(db, publicacion_id, prestador)
    lugar = _lugar_de(db, p, lugar_id)
    if cambios.nombre is not None:
        nombre = cambios.nombre.strip()
        otro = db.scalar(
            select(LugarTraslado).where(
                LugarTraslado.publicacion_id == p.id,
                LugarTraslado.id != lugar.id,
                LugarTraslado.nombre == nombre,
            )
        )
        if otro is not None or any(
            x.nombre.casefold() == nombre.casefold() and x.id != lugar.id
            for x in _activos(db, p)
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay un lugar con ese nombre")
        lugar.nombre = nombre
    if cambios.lat is not None:
        lugar.ubicacion = _punto(cambios.lat, cambios.lon)
    if cambios.es_base is not None:
        lugar.es_base = cambios.es_base
        if cambios.es_base:
            _una_sola_base(db, p, lugar)
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.delete("/{publicacion_id}/lugares-traslado/{lugar_id}", response_model=PublicacionOut)
def quitar_lugar(
    publicacion_id: uuid.UUID,
    lugar_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    """Deja de ofrecerse, y con él los tramos que salen o llegan ahí."""
    p = _de_traslados(db, publicacion_id, prestador)
    lugar = _lugar_de(db, p, lugar_id)
    lugar.activo = False
    lugar.es_base = False
    for tramo in db.scalars(
        select(TramoTraslado).where(
            or_(TramoTraslado.origen_id == lugar.id, TramoTraslado.destino_id == lugar.id)
        )
    ):
        tramo.activo = False
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


# --- Tramos ---


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/tramos-traslado",
    response_model=PublicacionOut,
    status_code=201,
)
def crear_tramo(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: NuevoTramo,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    """Un recorrido fijo del vehículo con su precio: "Aeropuerto → Centro"."""
    p = _de_traslados(db, publicacion_id, prestador)
    unidad = _vehiculo(db, p, unidad_id)
    _lugar_de(db, p, datos.origen_id)
    _lugar_de(db, p, datos.destino_id)
    _bloquear(db, Unidad, unidad.id)
    activos = db.scalars(
        select(TramoTraslado.id).where(
            TramoTraslado.unidad_id == unidad.id, TramoTraslado.activo.is_(True)
        )
    ).all()
    if len(activos) >= MAX_TRAMOS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Hasta {MAX_TRAMOS} tramos por vehículo")
    tramo = db.scalar(
        select(TramoTraslado).where(
            TramoTraslado.unidad_id == unidad.id,
            TramoTraslado.origen_id == datos.origen_id,
            TramoTraslado.destino_id == datos.destino_id,
        )
    )
    if tramo is not None and tramo.activo:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ese recorrido ya tiene precio: quitalo para cargarlo de nuevo",
        )
    if tramo is None:
        tramo = TramoTraslado(unidad_id=unidad.id, **datos.model_dump())
        db.add(tramo)
    else:
        for campo, valor in datos.model_dump().items():
            setattr(tramo, campo, valor)
        tramo.activo = True
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.delete(
    "/{publicacion_id}/unidades/{unidad_id}/tramos-traslado/{tramo_id}",
    response_model=PublicacionOut,
)
def quitar_tramo(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    tramo_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    """Deja de ofrecerse. Las reservas guardan su precio en el desglose: no cambian."""
    p = _de_traslados(db, publicacion_id, prestador)
    unidad = _vehiculo(db, p, unidad_id)
    tramo = db.get(TramoTraslado, tramo_id)
    if tramo is None or tramo.unidad_id != unidad.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese tramo")
    tramo.activo = False
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


# --- Tarifa y reglas del vehículo ---


@router.put(
    "/{publicacion_id}/unidades/{unidad_id}/tarifa-traslado", response_model=PublicacionOut
)
def guardar_tarifa(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: TarifaTrasladoIn,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    """Reemplaza la tarifa por km y las reglas del vehículo, todo junto."""
    p = _de_traslados(db, publicacion_id, prestador)
    unidad = _vehiculo(db, p, unidad_id)
    tarifa = db.scalar(select(TarifaTraslado).where(TarifaTraslado.unidad_id == unidad.id))
    if tarifa is None:
        tarifa = TarifaTraslado(unidad_id=unidad.id)
        db.add(tarifa)
    for campo, valor in datos.model_dump().items():
        setattr(tarifa, campo, valor)
    db.commit()
    return _respuesta(db, publicacion_id, prestador)
