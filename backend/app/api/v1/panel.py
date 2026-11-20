"""Paneles: favoritos del viajero, cobros del prestador, control del operador.

docs/01 §5 R10. Cada rol ve lo suyo y nada más:

- El viajero, sus favoritos.
- El prestador, cuánto cobró y cuánta comisión se le descontó, con el detalle por
  reserva. Es la única forma de que pueda controlar la liquidación.
- El operador, todas las reservas y comisiones con filtros y exportación.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import operador, prestador_actual, usuario_actual
from app.api.v1.publicaciones import Dinero, FotoOut
from app.core.database import get_db
from app.models import (
    ComisionAplicada,
    Favorito,
    ItemReserva,
    Localidad,
    Prestador,
    Publicacion,
    Reserva,
    Unidad,
    Usuario,
)
from app.models.enums import EstadoReserva

router = APIRouter(tags=["paneles"])

# Estados en los que el dinero ya se capturó. Una reserva rechazada o cancelada
# pasa a CANCELADA y sale sola de estos totales.
CON_PLATA = (
    EstadoReserva.PENDIENTE_APROBACION,
    EstadoReserva.CONFIRMADA,
    EstadoReserva.COMPLETADA,
    EstadoReserva.EN_RECLAMO,
)


# --- Favoritos (docs/01 §4, historia 8) ---


class FavoritoOut(BaseModel):
    publicacion_id: uuid.UUID
    slug: str
    titulo: str
    localidad: str
    provincia: str
    subtipo: str | None
    capacidad_maxima: int
    fotos: list[FotoOut]


@router.get("/favoritos", response_model=list[FavoritoOut])
def mis_favoritos(
    usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)
) -> list[FavoritoOut]:
    publicaciones = db.scalars(
        select(Publicacion)
        .join(Favorito, Favorito.publicacion_id == Publicacion.id)
        .where(Favorito.usuario_id == usuario.id)
        .options(
            selectinload(Publicacion.fotos),
            selectinload(Publicacion.subtipo),
            selectinload(Publicacion.unidades),
            selectinload(Publicacion.localidad).selectinload(Localidad.provincia),
        )
        .order_by(Favorito.creado_en.desc())
    ).unique()
    return [
        FavoritoOut(
            publicacion_id=p.id,
            slug=p.slug,
            titulo=p.titulo,
            localidad=p.localidad.nombre,
            provincia=p.localidad.provincia.nombre,
            subtipo=p.subtipo.nombre if p.subtipo else None,
            capacidad_maxima=max((u.capacidad for u in p.unidades if u.activa), default=0),
            fotos=[FotoOut(url=f.url, descripcion=f.descripcion) for f in p.fotos[:1]],
        )
        for p in publicaciones
    ]


@router.put("/favoritos/{publicacion_id}", status_code=status.HTTP_204_NO_CONTENT)
def guardar_favorito(
    publicacion_id: uuid.UUID,
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
) -> Response:
    if db.get(Publicacion, publicacion_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese alojamiento")
    existente = db.scalar(
        select(Favorito).where(
            Favorito.usuario_id == usuario.id, Favorito.publicacion_id == publicacion_id
        )
    )
    if existente is None:
        db.add(Favorito(usuario_id=usuario.id, publicacion_id=publicacion_id))
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/favoritos/{publicacion_id}", status_code=status.HTTP_204_NO_CONTENT)
def sacar_favorito(
    publicacion_id: uuid.UUID,
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
) -> Response:
    favorito = db.scalar(
        select(Favorito).where(
            Favorito.usuario_id == usuario.id, Favorito.publicacion_id == publicacion_id
        )
    )
    if favorito is not None:
        db.delete(favorito)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Cobros del prestador (docs/01 §4, historia 15) ---


class LineaCobro(BaseModel):
    codigo: str
    estado: EstadoReserva
    alojamiento: str
    unidad: str
    fecha_inicio: date
    fecha_fin: date
    paga_el_viajero: Dinero
    tu_precio: Dinero
    comision: Dinero
    iva_comision: Dinero
    te_queda: Dinero
    regla: str
    pagado: bool


class ResumenCobros(BaseModel):
    reservas: int
    paga_el_viajero: Dinero
    tu_precio: Dinero
    comision: Dinero
    te_queda: Dinero
    lineas: list[LineaCobro]


@router.get("/mis-cobros", response_model=ResumenCobros)
def mis_cobros(
    desde: date | None = None,
    hasta: date | None = None,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> ResumenCobros:
    """Cuánto entró, cuánta comisión se descontó y cuánto queda, reserva por reserva."""
    consulta = (
        select(ItemReserva)
        .join(Reserva, ItemReserva.reserva_id == Reserva.id)
        .where(
            ItemReserva.prestador_id == prestador.id,
            # También las que esperan tu respuesta: el viajero ya pagó y esa
            # plata está capturada. Si la rechazás pasa a cancelada y sale sola.
            Reserva.estado.in_(CON_PLATA),
        )
        .options(
            selectinload(ItemReserva.reserva).selectinload(Reserva.pagos),
            selectinload(ItemReserva.comision),
            selectinload(ItemReserva.unidad).selectinload(Unidad.publicacion),
        )
        .order_by(ItemReserva.fecha_inicio.desc())
    )
    if desde:
        consulta = consulta.where(ItemReserva.fecha_inicio >= desde)
    if hasta:
        consulta = consulta.where(ItemReserva.fecha_inicio <= hasta)

    lineas: list[LineaCobro] = []
    totales = {"viajero": Decimal(0), "precio": Decimal(0), "comision": Decimal(0)}
    for item in db.scalars(consulta).unique():
        c = item.comision
        descuento = c.descuento_prestador if c else Decimal(0)
        lineas.append(
            LineaCobro(
                codigo=item.reserva.codigo,
                estado=item.reserva.estado,
                alojamiento=item.unidad.publicacion.titulo,
                unidad=item.unidad.nombre,
                fecha_inicio=item.fecha_inicio,
                fecha_fin=item.fecha_fin,
                paga_el_viajero=item.reserva.total,
                tu_precio=item.subtotal,
                comision=c.comision_neta if c else Decimal(0),
                iva_comision=c.iva if c else Decimal(0),
                te_queda=item.subtotal - descuento,
                regla=str(c.regla_snapshot.get("nombre", "")) if c else "",
                pagado=any(p.estado == "aprobado" for p in item.reserva.pagos),
            )
        )
        totales["viajero"] += item.reserva.total
        totales["precio"] += item.subtotal
        totales["comision"] += descuento

    return ResumenCobros(
        reservas=len(lineas),
        paga_el_viajero=totales["viajero"],
        tu_precio=totales["precio"],
        comision=totales["comision"],
        te_queda=totales["precio"] - totales["comision"],
        lineas=lineas,
    )


# --- Control del operador (docs/01 §4, historia 19) ---


class LineaOperador(BaseModel):
    codigo: str
    estado: EstadoReserva
    creada_en: date
    viajero: str
    prestador: str
    alojamiento: str
    localidad: str
    fecha_inicio: date
    fecha_fin: date
    total: Dinero
    comision: Dinero
    iva: Dinero
    al_prestador: Dinero
    pasarela: str | None
    pagado: bool


class ResumenOperacion(BaseModel):
    reservas: int
    facturado: Dinero
    comision: Dinero
    iva: Dinero
    lineas: list[LineaOperador]


def _lineas_operador(
    db: Session,
    estado: EstadoReserva | None,
    desde: date | None,
    hasta: date | None,
    limite: int = 500,
) -> list[LineaOperador]:
    consulta = (
        select(ItemReserva)
        .join(Reserva, ItemReserva.reserva_id == Reserva.id)
        .options(
            selectinload(ItemReserva.reserva).selectinload(Reserva.pagos),
            selectinload(ItemReserva.comision),
            selectinload(ItemReserva.unidad)
            .selectinload(Unidad.publicacion)
            .selectinload(Publicacion.prestador),
            selectinload(ItemReserva.unidad)
            .selectinload(Unidad.publicacion)
            .selectinload(Publicacion.localidad),
        )
        .order_by(Reserva.creado_en.desc())
        .limit(limite)
    )
    if estado:
        consulta = consulta.where(Reserva.estado == estado)
    if desde:
        consulta = consulta.where(ItemReserva.fecha_inicio >= desde)
    if hasta:
        consulta = consulta.where(ItemReserva.fecha_inicio <= hasta)

    salida = []
    for item in db.scalars(consulta).unique():
        reserva = item.reserva
        c = item.comision
        viajero = db.get(Usuario, reserva.usuario_id)
        pago = next((p for p in reserva.pagos if p.estado == "aprobado"), None)
        salida.append(
            LineaOperador(
                codigo=reserva.codigo,
                estado=reserva.estado,
                creada_en=reserva.creado_en.date(),
                viajero=f"{viajero.nombre} {viajero.apellido}" if viajero else "—",
                prestador=item.unidad.publicacion.prestador.razon_social,
                alojamiento=item.unidad.publicacion.titulo,
                localidad=item.unidad.publicacion.localidad.nombre,
                fecha_inicio=item.fecha_inicio,
                fecha_fin=item.fecha_fin,
                total=reserva.total,
                comision=c.comision_neta if c else Decimal(0),
                iva=c.iva if c else Decimal(0),
                al_prestador=item.subtotal - (c.descuento_prestador if c else Decimal(0)),
                pasarela=pago.pasarela if pago else None,
                pagado=pago is not None,
            )
        )
    return salida


@router.get("/admin/reservas", response_model=ResumenOperacion)
def reservas_operador(
    estado: Annotated[EstadoReserva | None, Query()] = None,
    desde: date | None = None,
    hasta: date | None = None,
    _: Usuario = Depends(operador),
    db: Session = Depends(get_db),
) -> ResumenOperacion:
    lineas = _lineas_operador(db, estado, desde, hasta)
    return ResumenOperacion(
        reservas=len(lineas),
        facturado=sum((x.total for x in lineas), Decimal(0)),
        comision=sum((x.comision for x in lineas), Decimal(0)),
        iva=sum((x.iva for x in lineas), Decimal(0)),
        lineas=lineas,
    )


@router.get("/admin/reservas.csv", response_class=Response)
def exportar_reservas(
    estado: Annotated[EstadoReserva | None, Query()] = None,
    desde: date | None = None,
    hasta: date | None = None,
    _: Usuario = Depends(operador),
    db: Session = Depends(get_db),
) -> Response:
    """La misma vista, descargable. docs/01 §4 historia 19 pide exportación."""
    lineas = _lineas_operador(db, estado, desde, hasta, limite=5000)
    salida = io.StringIO()
    # Separador punto y coma: Excel en español no parte por coma.
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(
        [
            "codigo", "estado", "creada", "viajero", "prestador", "alojamiento",
            "localidad", "desde", "hasta", "total", "comision", "iva",
            "al_prestador", "pasarela", "pagado",
        ]
    )
    for x in lineas:
        escritor.writerow(
            [
                x.codigo, x.estado.value, x.creada_en, x.viajero, x.prestador, x.alojamiento,
                x.localidad, x.fecha_inicio, x.fecha_fin,
                f"{x.total:.2f}".replace(".", ","),
                f"{x.comision:.2f}".replace(".", ","),
                f"{x.iva:.2f}".replace(".", ","),
                f"{x.al_prestador:.2f}".replace(".", ","),
                x.pasarela or "", "si" if x.pagado else "no",
            ]
        )
    return Response(
        content="﻿" + salida.getvalue(),  # BOM: Excel reconoce el UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="reservas.csv"'},
    )


class ResumenComisiones(BaseModel):
    reservas: int
    base: Dinero
    comision_neta: Dinero
    iva: Dinero
    comision_total: Dinero
    la_paga_el_viajero: Dinero
    la_absorbe_el_prestador: Dinero


@router.get("/admin/comisiones", response_model=ResumenComisiones)
def comisiones_operador(
    _: Usuario = Depends(operador), db: Session = Depends(get_db)
) -> ResumenComisiones:
    """Lo que la plataforma cobró, sumando los snapshots de cada reserva."""
    fila = db.execute(
        select(
            func.count(ComisionAplicada.id),
            func.coalesce(func.sum(ComisionAplicada.base), 0),
            func.coalesce(func.sum(ComisionAplicada.comision_neta), 0),
            func.coalesce(func.sum(ComisionAplicada.iva), 0),
            func.coalesce(func.sum(ComisionAplicada.comision_total), 0),
            func.coalesce(func.sum(ComisionAplicada.cargo_viajero), 0),
            func.coalesce(func.sum(ComisionAplicada.descuento_prestador), 0),
        )
        .select_from(ComisionAplicada)
        .join(ItemReserva, ComisionAplicada.item_reserva_id == ItemReserva.id)
        .join(Reserva, ItemReserva.reserva_id == Reserva.id)
        .where(Reserva.estado.in_(CON_PLATA))
    ).one()
    return ResumenComisiones(
        reservas=fila[0],
        base=fila[1],
        comision_neta=fila[2],
        iva=fila[3],
        comision_total=fila[4],
        la_paga_el_viajero=fila[5],
        la_absorbe_el_prestador=fila[6],
    )
