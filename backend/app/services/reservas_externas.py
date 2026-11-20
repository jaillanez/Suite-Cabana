"""Ventas que entraron por fuera: por mail de la plataforma o cerradas a mano.

La promesa del producto es cero dobles reservas (docs/00 §7). Una venta por
Despegar o por WhatsApp la rompe igual que cualquier otra si nadie la carga, y
son justamente las que ninguna sincronización trae sola.

Acá entran, y al entrar tapan esa noche en todas las otras plataformas: el
bloqueo que crean sale por el iCal que exportamos.
"""

from __future__ import annotations

import difflib
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import BloqueoFecha, Publicacion, ReservaExterna, Unidad
from app.models.enums import EstadoReservaExterna, OrigenBloqueo, OrigenReservaExterna
from app.services import canales
from app.services.calendario import rango
from app.services.correo.analisis import Lectura


class FechasOcupadas(Exception):
    """Esa unidad ya tiene algo en esas noches."""


@dataclass
class Resultado:
    reserva: ReservaExterna
    #: Falso cuando el mismo mail ya se había cargado antes.
    nueva: bool
    #: Qué pasó, en palabras, para mostrárselo al anfitrión.
    detalle: str


def unidades_de(db: Session, prestador_id: uuid.UUID) -> list[Unidad]:
    return list(
        db.scalars(
            select(Unidad)
            .join(Publicacion)
            .where(Publicacion.prestador_id == prestador_id)
            .order_by(Unidad.nombre)
        )
    )


def adivinar_unidad(nombre: str | None, unidades: list[Unidad]) -> Unidad | None:
    """Encuentra la unidad que nombra el mail.

    Con una sola unidad no hay nada que adivinar. Con varias, se compara por
    parecido y se exige un mínimo: preferimos dejarla para revisar antes que
    bloquearle las fechas a la cabaña equivocada.
    """
    if len(unidades) == 1:
        return unidades[0]
    if not nombre or not unidades:
        return None
    buscado = nombre.strip().lower()
    for unidad in unidades:
        if unidad.nombre.strip().lower() == buscado:
            return unidad
    parecidas = sorted(
        unidades,
        key=lambda u: difflib.SequenceMatcher(None, buscado, u.nombre.lower()).ratio(),
        reverse=True,
    )
    mejor = parecidas[0]
    puntaje = difflib.SequenceMatcher(None, buscado, mejor.nombre.lower()).ratio()
    if puntaje < 0.72:
        return None
    # Empate: dos unidades igual de parecidas no se desempatan solas.
    if len(parecidas) > 1:
        segundo = difflib.SequenceMatcher(None, buscado, parecidas[1].nombre.lower()).ratio()
        if puntaje - segundo < 0.08:
            return None
    return mejor


def _etiqueta(reserva: ReservaExterna) -> str:
    """Lo que se lee en el calendario: primero quién viene, si no de dónde vino."""
    if reserva.huesped:
        return reserva.huesped[:200]
    plataforma = canales.POR_CODIGO.get(reserva.plataforma)
    return plataforma.nombre if plataforma else "Reserva externa"


def _bloquear(db: Session, reserva: ReservaExterna) -> None:
    """Crea el bloqueo. La colisión la detecta la base, no un `if`."""
    db.add(
        BloqueoFecha(
            unidad_id=reserva.unidad_id,
            rango=rango(reserva.fecha_inicio, reserva.fecha_fin),
            origen=OrigenBloqueo.EXTERNA,
            reserva_externa_id=reserva.id,
            activo=True,
            nota=_etiqueta(reserva),
        )
    )
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise FechasOcupadas(
            "Esas noches ya están tomadas en esa unidad. Revisá el calendario: puede "
            "ser la misma reserva cargada dos veces, o una venta doble de verdad."
        ) from e


def registrar(
    db: Session,
    prestador_id: uuid.UUID,
    unidad: Unidad | None,
    lectura: Lectura,
    *,
    origen: OrigenReservaExterna,
    mensaje: dict | None = None,
) -> Resultado:
    """Guarda la reserva y, si está entera, bloquea las fechas.

    Es idempotente por `huella` dentro del prestador: el mismo mail reenviado
    tres veces deja una sola reserva. Los webhooks se reintentan, y la gente
    reenvía. La idempotencia va por prestador y no por unidad justamente porque
    el caso difícil —el mail que no dice la cabaña— no tiene unidad todavía.
    """
    if lectura.huella:
        ya = db.scalar(
            select(ReservaExterna).where(
                ReservaExterna.prestador_id == prestador_id,
                ReservaExterna.huella == lectura.huella,
            )
        )
        if ya is not None:
            return Resultado(ya, nueva=False, detalle="Ese mensaje ya estaba cargado.")

    faltantes = list(lectura.faltantes)
    if unidad is None:
        faltantes.append("a qué unidad corresponde")

    reserva = ReservaExterna(
        prestador_id=prestador_id,
        unidad_id=unidad.id if unidad else None,
        origen=origen,
        plataforma=lectura.plataforma,
        fecha_inicio=lectura.fecha_inicio,
        fecha_fin=lectura.fecha_fin,
        huesped=lectura.huesped,
        contacto=lectura.contacto,
        personas=lectura.personas,
        monto=lectura.monto,
        codigo_externo=lectura.codigo_externo,
        faltantes=faltantes or None,
        huella=lectura.huella or None,
        mensaje=mensaje,
        estado=(
            EstadoReservaExterna.CONFIRMADA if not faltantes else EstadoReservaExterna.POR_REVISAR
        ),
    )
    db.add(reserva)
    db.flush()

    if reserva.estado is EstadoReservaExterna.CONFIRMADA:
        _bloquear(db, reserva)
        return Resultado(
            reserva,
            nueva=True,
            detalle=f"Bloqueado del {reserva.fecha_inicio} al {reserva.fecha_fin}.",
        )
    return Resultado(
        reserva,
        nueva=True,
        detalle="Quedó para revisar: falta " + ", ".join(faltantes) + ".",
    )


def cargar_a_mano(
    db: Session,
    prestador_id: uuid.UUID,
    unidad: Unidad,
    *,
    fecha_inicio: date,
    fecha_fin: date,
    huesped: str | None = None,
    contacto: str | None = None,
    personas: int | None = None,
    monto: Decimal | None = None,
    plataforma: str = "particular",
    nota: str | None = None,
) -> ReservaExterna:
    """Una venta que cerró el anfitrión: WhatsApp, teléfono, un huésped que vuelve.

    No lleva comisión. No la vendimos nosotros; solo ocupa la noche.
    """
    if fecha_fin <= fecha_inicio:
        raise ValueError("La salida tiene que ser posterior a la entrada.")
    reserva = ReservaExterna(
        prestador_id=prestador_id,
        unidad_id=unidad.id,
        origen=OrigenReservaExterna.PARTICULAR,
        estado=EstadoReservaExterna.CONFIRMADA,
        plataforma=plataforma,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        huesped=huesped,
        contacto=contacto,
        personas=personas,
        monto=monto,
        nota=nota,
    )
    db.add(reserva)
    db.flush()
    _bloquear(db, reserva)
    return reserva


def completar(
    db: Session,
    reserva: ReservaExterna,
    *,
    unidad: Unidad | None = None,
    fecha_inicio: date | None = None,
    fecha_fin: date | None = None,
    huesped: str | None = None,
) -> ReservaExterna:
    """El anfitrión arregla a mano lo que el análisis no pudo leer."""
    if unidad is not None:
        reserva.unidad_id = unidad.id
    if fecha_inicio is not None:
        reserva.fecha_inicio = fecha_inicio
    if fecha_fin is not None:
        reserva.fecha_fin = fecha_fin
    if huesped is not None:
        reserva.huesped = huesped

    if reserva.unidad_id is None:
        raise ValueError("Falta decir a qué unidad corresponde.")
    if not (reserva.fecha_inicio and reserva.fecha_fin):
        raise ValueError("Faltan las fechas.")
    if reserva.fecha_fin <= reserva.fecha_inicio:
        raise ValueError("La salida tiene que ser posterior a la entrada.")

    reserva.faltantes = None
    reserva.estado = EstadoReservaExterna.CONFIRMADA
    db.flush()
    _bloquear(db, reserva)
    return reserva


def de(db: Session, prestador_id: uuid.UUID, estado: EstadoReservaExterna) -> list[ReservaExterna]:
    """Las reservas externas de un prestador en cierto estado."""
    return list(
        db.scalars(
            select(ReservaExterna)
            .where(
                ReservaExterna.prestador_id == prestador_id,
                ReservaExterna.estado == estado,
            )
            .order_by(ReservaExterna.creado_en.desc())
        )
    )


def descartar(db: Session, reserva: ReservaExterna) -> ReservaExterna:
    """La venta se cayó, o el mail no era una reserva. Libera las fechas."""
    for bloqueo in reserva.bloqueos:
        bloqueo.activo = False
    reserva.estado = EstadoReservaExterna.DESCARTADA
    db.flush()
    return reserva
