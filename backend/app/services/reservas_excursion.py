"""Reservar lugares en una salida de excursión (docs/05, etapa 2).

Sigue el mismo circuito que una estadía o un evento (`reservas`): cotización,
retención con vencimiento mientras se paga, confirmación con el pago y snapshot
de comisión y política. Lo propio de una excursión:

- El precio sale de los tipos de pasajero del prestador (`precios_excursion`).
- Lo que se retiene son lugares de una salida (`salidas.tomar`), no un rango.
- Si la salida no va —el prestador la suspende o no se llega al mínimo— se
  cancelan las reservas y se devuelve lo que el prestador eligió
  (`reintegro_si_no_sale`, guardado en la reserva al crearla).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    CupoTomado,
    ItemReserva,
    PrecioPasajero,
    Reserva,
    SalidaExcursion,
    TurnoExcursion,
    Unidad,
    Usuario,
)
from app.models.enums import EstadoPublicacion, EstadoReserva, ModoReserva, OrigenBloqueo
from app.services import comisiones, politicas, reservas, salidas
from app.services import precios_excursion as px
from app.services.precios_eventos import ZONA

ESTADOS_VIGENTES = (
    EstadoReserva.PENDIENTE_PAGO,
    EstadoReserva.PENDIENTE_APROBACION,
    EstadoReserva.CONFIRMADA,
)


@dataclass(frozen=True)
class CotizacionExcursion:
    unidad: Unidad
    salida: salidas.Salida
    precio: px.PrecioExcursion
    comision: comisiones.ResultadoComision
    total_viajero: Decimal
    sena: Decimal | None


def categorias(db: Session, unidad: Unidad) -> list[PrecioPasajero]:
    return list(
        db.scalars(
            select(PrecioPasajero)
            .where(PrecioPasajero.unidad_id == unidad.id, PrecioPasajero.activo.is_(True))
            .order_by(PrecioPasajero.orden, PrecioPasajero.nombre)
        )
    )


def _salida(
    db: Session,
    unidad: Unidad,
    fecha: date,
    turno_id: uuid.UUID | None,
    salida_id: uuid.UUID | None,
) -> salidas.Salida:
    if (turno_id is None) == (salida_id is None):
        raise reservas.NoSePuedeReservar("Elegí una salida")
    for s in salidas.salidas(db, unidad, fecha, fecha):
        if (salida_id and s.salida_id == salida_id) or (
            turno_id and s.turno_id == turno_id and salida_id is None
        ):
            return s
    raise reservas.NoSePuedeReservar("Esa salida no está disponible")


def cotizar_excursion(
    db: Session,
    unidad: Unidad,
    fecha: date,
    pasajeros: dict[uuid.UUID, int],
    turno_id: uuid.UUID | None = None,
    salida_id: uuid.UUID | None = None,
    hoy: date | None = None,
) -> CotizacionExcursion:
    """Precio, comisión y seña de unos lugares en una salida, sin tocar nada."""
    hoy = hoy or datetime.now(ZONA).date()
    publicacion = unidad.publicacion
    if publicacion.estado is not EstadoPublicacion.APROBADA or not unidad.activa:
        raise reservas.NoSePuedeReservar("Esa excursión no está disponible")
    if publicacion.tipo_servicio.modo_reserva is not ModoReserva.TURNO_CUPO:
        raise reservas.NoSePuedeReservar("Esto no se reserva por turno")
    salida = _salida(db, unidad, fecha, turno_id, salida_id)
    try:
        precio = px.calcular(
            [
                px.Categoria(c.id, c.nombre, c.precio, c.ocupa_lugar)
                for c in categorias(db, unidad)
            ],
            pasajeros,
            unidad.capacidad,
        )
    except px.PrecioInvalido as e:
        raise reservas.NoSePuedeReservar(str(e)) from e
    if precio.lugares > salida.libres:
        raise reservas.NoSePuedeReservar(str(salidas.SinCupo(salida.libres)))
    comision = reservas._comision(db, publicacion, precio.subtotal, fecha, hoy)
    total = reservas._r(precio.subtotal + comision.cargo_viajero)
    return CotizacionExcursion(
        unidad=unidad,
        salida=salida,
        precio=precio,
        comision=comision,
        total_viajero=total,
        sena=reservas._sena(publicacion, total),
    )


def crear_excursion(
    db: Session,
    usuario: Usuario,
    unidad: Unidad,
    fecha: date,
    pasajeros: dict[uuid.UUID, int],
    turno_id: uuid.UUID | None = None,
    salida_id: uuid.UUID | None = None,
    hoy: date | None = None,
) -> Reserva:
    """Crea la reserva y retiene los lugares mientras el viajero paga.

    La sobreventa la frena la base (`salidas.tomar`): si entre la cotización y
    este momento otro tomó los últimos lugares, se deshace todo.
    """
    if not usuario.email_verificado:
        raise reservas.NoSePuedeReservar("Verificá tu correo antes de reservar")
    cot = cotizar_excursion(db, unidad, fecha, pasajeros, turno_id, salida_id, hoy)
    publicacion = unidad.publicacion
    s = get_settings()
    reserva = Reserva(
        codigo=reservas.generar_codigo(db),
        usuario_id=usuario.id,
        estado=EstadoReserva.PENDIENTE_PAGO,
        total=cot.total_viajero,
        monto_sena=cot.sena,
        vence_pago_en=datetime.now(UTC) + timedelta(minutes=s.minutos_retencion_pago),
        politica_cancelacion=politicas.snapshot(publicacion),
    )
    db.add(reserva)
    db.flush()
    item = ItemReserva(
        reserva_id=reserva.id,
        unidad_id=unidad.id,
        prestador_id=publicacion.prestador_id,
        fecha_inicio=cot.salida.fecha,
        fecha_fin=cot.salida.fin.astimezone(ZONA).date(),
        inicio_en=cot.salida.inicio,
        fin_en=cot.salida.fin,
        adultos=cot.precio.personas,
        menores=0,
        mascotas=0,
        desglose={**cot.precio.desglose(), "salida": cot.salida.nombre},
        subtotal=cot.precio.subtotal,
        politica_cancelacion=politicas.snapshot(publicacion),
    )
    db.add(item)
    db.flush()
    reservas._guardar_comision(db, item, cot.comision)

    if cot.salida.salida_id:
        fila = db.get(SalidaExcursion, cot.salida.salida_id)
    else:
        fila = salidas.materializar(db, db.get(TurnoExcursion, cot.salida.turno_id), fecha)
    try:
        salidas.tomar(
            db, fila, cot.precio.lugares, OrigenBloqueo.RETENCION,
            vence_en=reserva.vence_pago_en, item_reserva_id=item.id,
            nota=f"Retención de la reserva {reserva.codigo}",
        )
    except salidas.SinCupo as e:
        db.rollback()
        raise reservas.FechasTomadas(
            f"Alguien tomó lugares mientras completabas. {e}"
        ) from e
    except salidas.SalidaInvalida as e:
        db.rollback()
        raise reservas.NoSePuedeReservar(str(e)) from e

    reservas._avisar_al_viajero(db, reserva, "reserva_creada")
    return reserva


# --- Cuando la salida no va ---


def no_sale(
    db: Session, salida: SalidaExcursion, motivo: str, ahora: datetime | None = None
) -> list[tuple[Reserva, reservas.Reintegro]]:
    """Cancela la salida: sus reservas se cancelan con el reintegro que eligió el
    prestador, los lugares que anotó por fuera se sueltan y la salida queda
    suspendida. Devuelve cada reserva con lo que corresponde devolver."""
    ahora = ahora or datetime.now(UTC)
    salida = salidas.bloquear(db, salida)
    tomados = list(
        db.scalars(
            select(CupoTomado).where(
                CupoTomado.salida_id == salida.id, CupoTomado.activo.is_(True)
            )
        )
    )
    items = [db.get(ItemReserva, t.item_reserva_id) for t in tomados if t.item_reserva_id]
    resultado: list[tuple[Reserva, reservas.Reintegro]] = []
    vistas: set[uuid.UUID] = set()
    for item in items:
        reserva = item.reserva
        if reserva.id in vistas or reserva.estado not in ESTADOS_VIGENTES:
            continue
        vistas.add(reserva.id)
        porcentaje = int(
            (item.politica_cancelacion or {}).get("reintegro_si_no_sale", 100)
        )
        # Sobre lo que entró: a quien todavía no pagó no hay nada que devolverle.
        base = reservas.pagado(reserva)
        reintegro = reservas.Reintegro(
            porcentaje, reservas._r(base * Decimal(porcentaje) / 100), motivo
        )
        texto = motivo
        if base:
            texto += f". Corresponde devolver el {porcentaje} % de lo pagado"
        reservas._liberar(db, reserva, texto)
        resultado.append((reserva, reintegro))
    for t in tomados:
        db.refresh(t)
        if t.activo:  # anotados por el prestador, sin reserva nuestra
            salidas.soltar(db, t)
    salidas.suspender(db, salida, motivo, ahora)
    db.flush()
    return resultado


def revisar_minimos(db: Session, ahora: datetime | None = None) -> dict[str, int]:
    """Para la tarea periódica: a la hora de decidir, cada salida con mínimo o se
    confirma (llegó) o se cancela (no llegó). Lo firme son las reservas pagadas y
    lo que anotó el prestador; quien está pagando todavía no cuenta.

    Una salida confirmada no se vuelve a mirar: si después alguien cancela, va igual.
    """
    ahora = ahora or datetime.now(UTC)
    decide_en = SalidaExcursion.inicio_en - func.make_interval(
        0, 0, 0, 0, SalidaExcursion.aviso_minimo_horas
    )
    pendientes = db.scalars(
        select(SalidaExcursion)
        .where(
            SalidaExcursion.suspendida.is_(False),
            SalidaExcursion.sale_confirmada.is_(False),
            SalidaExcursion.minimo_personas > 1,
            decide_en <= ahora,
        )
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).all()
    confirmadas = canceladas = 0
    for s in pendientes:
        if salidas.personas_firmes(db, s) >= s.minimo_personas:
            s.sale_confirmada = True
            confirmadas += 1
        else:
            no_sale(db, s, f"No se llegó al mínimo de {s.minimo_personas} personas", ahora)
            canceladas += 1
    db.flush()
    return {"salidas_confirmadas": confirmadas, "salidas_canceladas": canceladas}
