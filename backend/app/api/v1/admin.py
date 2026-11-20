"""Aprobación de publicaciones por el operador (docs/01 §5 R2, R10).

Ninguna publicación es visible sin que una persona la apruebe. El rechazo exige
motivo: el prestador tiene que saber qué corregir, y sin eso la moderación se
convierte en un rebote sin explicación.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import operador
from app.core.database import get_db
from app.models import Localidad, Publicacion, Unidad, Usuario
from app.models.enums import EstadoPublicacion
from app.services import edicion

router = APIRouter(prefix="/admin", tags=["operador"])


class Rechazo(BaseModel):
    motivo: Annotated[str, Field(min_length=5, max_length=500)]


class EnRevisionOut(BaseModel):
    id: uuid.UUID
    slug: str
    titulo: str
    descripcion: str
    estado: EstadoPublicacion
    prestador: str
    prestador_verificado: bool
    localidad: str
    provincia: str
    fotos: list[str]
    unidades: int
    capacidad_maxima: int
    comodidades: list[str]
    motivo_rechazo: str | None


class Pendientes(BaseModel):
    en_revision: int
    aprobadas: int
    rechazadas: int
    borradores: int


def _salida(p: Publicacion) -> EnRevisionOut:
    activas = [u for u in p.unidades if u.activa]
    return EnRevisionOut(
        id=p.id,
        slug=p.slug,
        titulo=p.titulo,
        descripcion=p.descripcion,
        estado=p.estado,
        prestador=p.prestador.razon_social,
        prestador_verificado=p.prestador.verificado,
        localidad=p.localidad.nombre,
        provincia=p.localidad.provincia.nombre,
        fotos=[f.url for f in sorted(p.fotos, key=lambda x: x.orden)],
        unidades=len(activas),
        capacidad_maxima=max((u.capacidad for u in activas), default=0),
        comodidades=sorted(c.codigo for c in p.comodidades),
        motivo_rechazo=p.motivo_rechazo,
    )


def _traer(publicacion_id: uuid.UUID, db: Session) -> Publicacion:
    p = db.scalar(
        select(Publicacion)
        .where(Publicacion.id == publicacion_id)
        .options(
            selectinload(Publicacion.fotos),
            selectinload(Publicacion.comodidades),
            selectinload(Publicacion.prestador),
            selectinload(Publicacion.unidades).selectinload(Unidad.tarifas),
            selectinload(Publicacion.localidad).selectinload(Localidad.provincia),
        )
    )
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa publicación")
    return p


@router.get("/publicaciones/resumen", response_model=Pendientes)
def resumen(_: Usuario = Depends(operador), db: Session = Depends(get_db)) -> Pendientes:
    def cuantas(estado: EstadoPublicacion) -> int:
        return db.scalar(
            select(func.count(Publicacion.id)).where(Publicacion.estado == estado)
        ) or 0

    return Pendientes(
        en_revision=cuantas(EstadoPublicacion.EN_REVISION),
        aprobadas=cuantas(EstadoPublicacion.APROBADA),
        rechazadas=cuantas(EstadoPublicacion.RECHAZADA),
        borradores=cuantas(EstadoPublicacion.BORRADOR),
    )


@router.get("/publicaciones", response_model=list[EnRevisionOut])
def listar(
    estado: Annotated[EstadoPublicacion, Query()] = EstadoPublicacion.EN_REVISION,
    _: Usuario = Depends(operador),
    db: Session = Depends(get_db),
) -> list[EnRevisionOut]:
    filas = db.scalars(
        select(Publicacion)
        .where(Publicacion.estado == estado)
        .options(
            selectinload(Publicacion.fotos),
            selectinload(Publicacion.comodidades),
            selectinload(Publicacion.prestador),
            selectinload(Publicacion.unidades),
            selectinload(Publicacion.localidad).selectinload(Localidad.provincia),
        )
        .order_by(Publicacion.actualizado_en)
    ).unique()
    return [_salida(p) for p in filas]


@router.post("/publicaciones/{publicacion_id}/aprobar", response_model=EnRevisionOut)
def aprobar(
    publicacion_id: uuid.UUID,
    _: Usuario = Depends(operador),
    db: Session = Depends(get_db),
) -> EnRevisionOut:
    p = _traer(publicacion_id, db)
    faltantes = edicion.faltantes(db, p)
    if faltantes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"mensaje": "No se puede aprobar: está incompleta", "faltantes": faltantes},
        )
    try:
        edicion.aprobar(p)
    except edicion.TransicionInvalida as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    db.commit()
    return _salida(_traer(publicacion_id, db))


@router.post("/publicaciones/{publicacion_id}/rechazar", response_model=EnRevisionOut)
def rechazar(
    publicacion_id: uuid.UUID,
    datos: Rechazo,
    _: Usuario = Depends(operador),
    db: Session = Depends(get_db),
) -> EnRevisionOut:
    p = _traer(publicacion_id, db)
    try:
        edicion.rechazar(p, datos.motivo)
    except edicion.TransicionInvalida as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    db.commit()
    return _salida(_traer(publicacion_id, db))
