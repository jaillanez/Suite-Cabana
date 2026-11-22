"""Motor de reservas (docs/01 §5 R5, R6, R8 y §7).

Acá vive la promesa central del producto: **cero dobles reservas**. La garantía
no es este código sino la restricción de exclusión de la base, que impide dos
bloqueos activos superpuestos para la misma unidad. Este módulo se apoya en ella:
intenta, y si la base dice que no, traduce el choque a un mensaje.

Secuencia de una reserva (docs/01 §7):

1. El viajero elige unidad y fechas.
2. Se calcula precio y comisión, y **se retienen las fechas** por un tiempo
   limitado mientras paga.
3. Paga. La pasarela notifica.
4. Si la confirmación es inmediata, queda confirmada; si es por solicitud, el
   prestador tiene un plazo para aprobar.
5. Si no paga en el plazo, la retención vence y las fechas se liberan solas.

Todo importe es Decimal (CLAUDE.md). Cada reserva guarda su `ComisionAplicada`:
cambiar una regla después no altera reservas existentes.
"""

from __future__ import annotations

import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import (
    BloqueoFecha,
    ComisionAplicada,
    ItemReserva,
    Localidad,
    Pago,
    Publicacion,
    ReglaComision,
    Reserva,
    Unidad,
    Usuario,
)
from app.models.enums import (
    CanalNotificacion,
    EstadoPublicacion,
    EstadoReserva,
    ModoReserva,
    OrigenBloqueo,
    TipoPago,
)
from app.services import busqueda, comisiones, notificaciones, precios
from app.services.pagos.base import EstadoPago

ALFABETO_CODIGO = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"


class NoSePuedeReservar(Exception):
    """La reserva no se puede crear, con el motivo en el mensaje."""


class FechasTomadas(NoSePuedeReservar):
    """Alguien se adelantó."""


class TransicionInvalida(Exception):
    """Ese cambio de estado de la reserva no existe."""


def _r(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def generar_codigo(db: Session) -> str:
    """Código corto para que el viajero lo lea por teléfono. Sin O ni I."""
    for _ in range(20):
        codigo = "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(8))
        if not db.scalar(select(Reserva.id).where(Reserva.codigo == codigo)):
            return codigo
    raise RuntimeError("No pudimos generar un código de reserva")


@dataclass(frozen=True)
class Cotizacion:
    unidad: Unidad
    precio: precios.Precio
    comision: comisiones.ResultadoComision
    total_viajero: Decimal
    noches: int


def cotizar(
    db: Session,
    unidad: Unidad,
    fecha_inicio: date,
    fecha_fin: date,
    personas: int = 2,
    mascotas: int = 0,
    hoy: date | None = None,
) -> Cotizacion:
    """Precio y comisión de una estadía, sin tocar nada.

    Es lo mismo que calcula la búsqueda: el precio que el viajero vio tiene que
    ser el que se le cobra (docs/01 §5 R5).
    """
    hoy = hoy or date.today()
    publicacion = unidad.publicacion
    if publicacion.estado is not EstadoPublicacion.APROBADA:
        raise NoSePuedeReservar("Ese alojamiento no está disponible")
    if not unidad.activa:
        raise NoSePuedeReservar("Esa unidad no está disponible")
    if publicacion.tipo_servicio.modo_reserva is not ModoReserva.NOCHES:
        # Un salón se reserva por horario (docs/04): cotizarlo por noches daría
        # un precio que no es el suyo.
        raise NoSePuedeReservar("Esto no se reserva por noches")

    try:
        precio = precios.calcular(
            busqueda.unidad_plana(unidad),
            busqueda.tarifas_de(unidad),
            fecha_inicio,
            fecha_fin,
            personas=personas,
            mascotas=mascotas,
            hoy=hoy,
        )
    except precios.NoDisponible as e:
        raise NoSePuedeReservar(str(e)) from e

    reglas = [comisiones.regla_desde_modelo(m) for m in db.scalars(select(ReglaComision))]
    ctx = comisiones.ContextoComision(
        monto=precio.subtotal,
        fecha_servicio=fecha_inicio,
        fecha_creacion=hoy,
        tipo_servicio_id=publicacion.tipo_servicio_id,
        subtipo_servicio_id=publicacion.subtipo_servicio_id,
        provincia_id=publicacion.localidad.provincia_id,
        localidad_id=publicacion.localidad_id,
        zona_id=publicacion.zona_id,
        prestador_id=publicacion.prestador_id,
        publicacion_id=publicacion.id,
        antiguedad_prestador_meses=max(
            0,
            (hoy.year - publicacion.prestador.fecha_alta.year) * 12
            + (hoy.month - publicacion.prestador.fecha_alta.month),
        ),
        categoria_prestador=publicacion.prestador.categoria,
    )
    try:
        comision = comisiones.resolver(reglas, ctx, get_settings().iva_comision)
    except comisiones.SinReglaAplicable as e:
        # Sin regla por defecto no se reserva: la comisión no se improvisa.
        raise NoSePuedeReservar(
            "No podemos calcular la comisión. Avisale al equipo antes de seguir."
        ) from e

    return Cotizacion(
        unidad=unidad,
        precio=precio,
        comision=comision,
        total_viajero=_r(precio.subtotal + comision.cargo_viajero),
        noches=precio.cantidad_noches,
    )


def _libre(db: Session, unidad_id: uuid.UUID, desde: date, hasta: date) -> bool:
    rango = func.daterange(desde, hasta, "[)")
    choque = db.scalar(
        select(BloqueoFecha.id).where(
            BloqueoFecha.unidad_id == unidad_id,
            BloqueoFecha.activo.is_(True),
            BloqueoFecha.rango.op("&&")(rango),
            or_(BloqueoFecha.vence_en.is_(None), BloqueoFecha.vence_en > func.now()),
        )
    )
    return choque is None


def crear(
    db: Session,
    usuario: Usuario,
    unidad: Unidad,
    fecha_inicio: date,
    fecha_fin: date,
    personas: int = 2,
    menores: int = 0,
    mascotas: int = 0,
    hoy: date | None = None,
) -> Reserva:
    """Crea la reserva y retiene las fechas mientras el viajero paga.

    La retención es un bloqueo con vencimiento: si no paga, se libera sola. El
    choque con otra reserva lo detecta la base, no un `if`: entre el chequeo y la
    inserción puede meterse otra transacción, y la restricción de exclusión es lo
    único que cierra esa ventana.
    """
    if not usuario.email_verificado:
        raise NoSePuedeReservar("Verificá tu correo antes de reservar")

    hoy = hoy or date.today()
    cotizacion = cotizar(db, unidad, fecha_inicio, fecha_fin, personas + menores, mascotas, hoy)
    if not _libre(db, unidad.id, fecha_inicio, fecha_fin):
        raise FechasTomadas("Esas fechas ya no están disponibles")

    s = get_settings()
    publicacion = unidad.publicacion
    politica = publicacion.politica_cancelacion

    reserva = Reserva(
        codigo=generar_codigo(db),
        usuario_id=usuario.id,
        estado=EstadoReserva.PENDIENTE_PAGO,
        total=cotizacion.total_viajero,
        monto_sena=(
            _r(cotizacion.total_viajero * Decimal(publicacion.prestador.porcentaje_sena) / 100)
            if publicacion.prestador.porcentaje_sena
            else None
        ),
        vence_pago_en=datetime.now(UTC) + timedelta(minutes=s.minutos_retencion_pago),
        politica_cancelacion=(
            {
                "codigo": politica.codigo,
                "nombre": politica.nombre,
                "tramos": politica.tramos,
            }
            if politica
            else None
        ),
    )
    db.add(reserva)
    db.flush()

    item = ItemReserva(
        reserva_id=reserva.id,
        unidad_id=unidad.id,
        prestador_id=publicacion.prestador_id,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        adultos=personas,
        menores=menores,
        mascotas=mascotas,
        desglose=cotizacion.precio.desglose(),
        subtotal=cotizacion.precio.subtotal,
    )
    db.add(item)
    db.flush()

    # Snapshot de la comisión: cambiar la regla después no toca esta reserva.
    db.add(
        ComisionAplicada(
            item_reserva_id=item.id,
            regla_id=cotizacion.comision.regla.id,
            regla_snapshot=cotizacion.comision.regla.a_dict(),
            base=cotizacion.comision.base,
            comision_neta=cotizacion.comision.comision_neta,
            iva=cotizacion.comision.iva,
            comision_total=cotizacion.comision.comision_total,
            cargo_viajero=cotizacion.comision.cargo_viajero,
            descuento_prestador=cotizacion.comision.descuento_prestador,
        )
    )

    db.add(
        BloqueoFecha(
            unidad_id=unidad.id,
            rango=Range(fecha_inicio, fecha_fin, bounds="[)"),
            origen=OrigenBloqueo.RETENCION,
            activo=True,
            vence_en=reserva.vence_pago_en,
            item_reserva_id=item.id,
            nota=f"Retención de la reserva {reserva.codigo}",
        )
    )

    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise FechasTomadas(
            "Alguien reservó esas fechas mientras completabas. Probá con otras."
        ) from e

    _avisar_al_viajero(db, reserva, "reserva_creada")
    return reserva


#: Pago aprobado por un monto menor al de la reserva: no la confirma.
ESTADO_MONTO_DISTINTO = "monto_distinto"


def registrar_pago(
    db: Session,
    reserva: Reserva,
    id_externo: str,
    pasarela: str,
    estado: EstadoPago,
    monto: Decimal | None = None,
    datos: dict | None = None,
) -> Reserva:
    """Aplica el resultado de un pago. Es idempotente: repetir no duplica nada."""
    item = reserva.items[0]
    comision = item.comision

    # Ya visto: se actualiza, no se duplica.
    pago = db.scalar(
        select(Pago).where(Pago.pasarela == pasarela, Pago.id_externo == id_externo)
    )
    if pago is None:
        # Al pedir el cobro se creó un pago pendiente sin id externo: este es ese
        # pago, no uno nuevo. Duplicarlo dejaría dos cobros por una reserva y la
        # liquidación del prestador saldría mal.
        pago = db.scalar(
            select(Pago).where(
                Pago.reserva_id == reserva.id,
                Pago.pasarela == pasarela,
                Pago.id_externo.is_(None),
            )
        )
    if pago is None:
        pago = Pago(
            reserva_id=reserva.id,
            tipo=TipoPago.TOTAL,
            pasarela=pasarela,
            monto=monto if monto is not None else reserva.total,
            monto_prestador=item.subtotal - (comision.descuento_prestador if comision else 0),
            monto_comision=comision.comision_neta if comision else Decimal(0),
            iva_comision=comision.iva if comision else Decimal(0),
        )
        db.add(pago)

    pago.id_externo = id_externo
    pago.estado = estado.value
    if monto is not None:
        pago.monto = monto
    if datos:
        pago.datos = datos

    # El cobro se pide por el total (api/v1/reservas.py → pagar). Un pago
    # aprobado por menos —uno armado a mano con el mismo código de reserva, o un
    # error de la pasarela— no confirma: queda a la vista para revisarlo.
    if estado is EstadoPago.APROBADO and monto is not None and monto < reserva.total:
        pago.estado = ESTADO_MONTO_DISTINTO
        db.flush()
        return reserva

    if estado is EstadoPago.APROBADO:
        _confirmar(db, reserva)
    elif estado in (EstadoPago.RECHAZADO, EstadoPago.CANCELADO):
        _liberar(db, reserva, "El pago no se completó")
    elif estado is EstadoPago.DEVUELTO:
        _liberar(db, reserva, "El pago fue devuelto")

    db.flush()
    return reserva


def _confirmar(db: Session, reserva: Reserva) -> None:
    """Pago aprobado: la retención pasa a ser una reserva firme."""
    if reserva.estado in (EstadoReserva.CONFIRMADA, EstadoReserva.COMPLETADA):
        return  # idempotente

    item = reserva.items[0]
    inmediata = item.unidad.publicacion.confirmacion_inmediata
    s = get_settings()

    reserva.estado = (
        EstadoReserva.CONFIRMADA if inmediata else EstadoReserva.PENDIENTE_APROBACION
    )
    reserva.vence_pago_en = None
    if not inmediata:
        reserva.vence_aprobacion_en = datetime.now(UTC) + timedelta(
            hours=s.horas_aprobacion_prestador
        )

    for bloqueo in db.scalars(
        select(BloqueoFecha).where(BloqueoFecha.item_reserva_id == item.id)
    ):
        bloqueo.origen = OrigenBloqueo.RESERVA
        bloqueo.vence_en = None
        bloqueo.activo = True
        bloqueo.nota = f"Reserva {reserva.codigo}"

    _avisar_al_viajero(
        db,
        reserva,
        "reserva_confirmada" if inmediata else "reserva_creada",
    )
    _avisar_al_prestador(
        db,
        reserva,
        "nueva_reserva",
        {
            "accion": (
                "Ya está confirmada."
                if inmediata
                else "Tenés que aceptarla o rechazarla antes de que venza el plazo."
            )
        },
    )


def _liberar(db: Session, reserva: Reserva, motivo: str) -> None:
    """Suelta las fechas de una reserva que no prosperó."""
    if reserva.estado is EstadoReserva.CANCELADA:
        return
    reserva.estado = EstadoReserva.CANCELADA
    reserva.cancelada_en = datetime.now(UTC)
    reserva.motivo_cancelacion = motivo
    _avisar_al_viajero(db, reserva, "reserva_cancelada", {"motivo": motivo})
    _avisar_al_prestador(db, reserva, "reserva_cancelada_prestador", {"motivo": motivo})
    for item in reserva.items:
        for bloqueo in db.scalars(
            select(BloqueoFecha).where(BloqueoFecha.item_reserva_id == item.id)
        ):
            db.delete(bloqueo)


@dataclass(frozen=True)
class Reintegro:
    porcentaje: int
    monto: Decimal
    motivo: str


def calcular_reintegro(reserva: Reserva, hoy: date | None = None) -> Reintegro:
    """Cuánto se devuelve según la política que la reserva guardó (docs/01 §5 R8).

    Se usa el snapshot, no la política actual: el viajero aceptó la de ese momento.
    """
    hoy = hoy or date.today()
    politica = reserva.politica_cancelacion or {}
    tramos = politica.get("tramos") or []
    if not tramos:
        return Reintegro(0, Decimal("0.00"), "Esta reserva no tiene política de cancelación")

    inicio = min(i.fecha_inicio for i in reserva.items)
    faltan = (inicio - hoy).days
    # Gana el tramo más exigente que el viajero todavía alcanza.
    elegibles = [t for t in tramos if faltan >= int(t.get("dias_antes", 0))]
    if not elegibles:
        return Reintegro(0, Decimal("0.00"), "Ya pasó el plazo para cancelar con reintegro")

    mejor = max(elegibles, key=lambda t: int(t.get("porcentaje_reintegro", 0)))
    porcentaje = int(mejor.get("porcentaje_reintegro", 0))
    return Reintegro(
        porcentaje=porcentaje,
        monto=_r(reserva.total * Decimal(porcentaje) / 100),
        motivo=f"Cancelás con {faltan} días de anticipación",
    )


def cancelar(db: Session, reserva: Reserva, motivo: str, hoy: date | None = None) -> Reintegro:
    """Cancela y devuelve cuánto corresponde reintegrar."""
    if reserva.estado in (EstadoReserva.CANCELADA, EstadoReserva.COMPLETADA):
        raise TransicionInvalida("Esta reserva ya no se puede cancelar")

    reintegro = calcular_reintegro(reserva, hoy)
    _liberar(db, reserva, motivo)
    db.flush()
    return reintegro


def aprobar(db: Session, reserva: Reserva) -> Reserva:
    """El prestador acepta una solicitud."""
    if reserva.estado is not EstadoReserva.PENDIENTE_APROBACION:
        raise TransicionInvalida("Esta reserva no está esperando tu respuesta")
    reserva.estado = EstadoReserva.CONFIRMADA
    reserva.vence_aprobacion_en = None
    db.flush()
    return reserva


def rechazar(db: Session, reserva: Reserva, motivo: str) -> Reserva:
    """El prestador rechaza: se libera y corresponde reintegro total."""
    if reserva.estado is not EstadoReserva.PENDIENTE_APROBACION:
        raise TransicionInvalida("Esta reserva no está esperando tu respuesta")
    _liberar(db, reserva, motivo or "El prestador no pudo tomar la reserva")
    db.flush()
    return reserva


def liberar_vencidas(db: Session, ahora: datetime | None = None) -> int:
    """Suelta las reservas que no se pagaron en el plazo (docs/01 §5 R5).

    Pensada para correr desde la cola de trabajos. Mientras no exista, la base ya
    ignora las retenciones vencidas al buscar, así que una fecha nunca queda
    tomada de más aunque esta tarea no corra.
    """
    ahora = ahora or datetime.now(UTC)
    vencidas = list(
        db.scalars(
            select(Reserva)
            .where(
                Reserva.estado == EstadoReserva.PENDIENTE_PAGO,
                Reserva.vence_pago_en.is_not(None),
                Reserva.vence_pago_en < ahora,
            )
            .options(selectinload(Reserva.items))
        )
    )
    for reserva in vencidas:
        _liberar(db, reserva, "No se completó el pago en el plazo")
    db.flush()
    return len(vencidas)


# --- Avisos (docs/01 §5 R9) ---


def _datos_para_aviso(reserva: Reserva) -> dict:
    """Lo que las plantillas necesitan saber de la reserva."""
    item = reserva.items[0]
    publicacion = item.unidad.publicacion
    web = get_settings().url_publica_web.rstrip("/")
    comision = item.comision
    neto = item.subtotal - (comision.descuento_prestador if comision else Decimal(0))
    personas = item.adultos + item.menores
    return {
        "codigo": reserva.codigo,
        "alojamiento": publicacion.titulo,
        "unidad": item.unidad.nombre,
        "desde": item.fecha_inicio.strftime("%d/%m/%Y"),
        "hasta": item.fecha_fin.strftime("%d/%m/%Y"),
        "total": f"$ {reserva.total:,.2f}".replace(",", "."),
        "neto": f"$ {neto:,.2f}".replace(",", "."),
        "personas": f"{personas} persona" + ("s" if personas != 1 else ""),
        "enlace": f"{web}/reservas/{reserva.codigo}",
    }


def _avisar_al_viajero(
    db: Session, reserva: Reserva, evento: str, extra: dict | None = None
) -> None:
    usuario = db.get(Usuario, reserva.usuario_id)
    if usuario is None:
        return
    datos = {**_datos_para_aviso(reserva), "nombre": usuario.nombre, **(extra or {})}
    notificaciones.encolar(
        db, evento, CanalNotificacion.EMAIL, usuario.email, datos,
        usuario_id=usuario.id, reserva_id=reserva.id,
    )
    if usuario.telefono:
        # Queda registrada aunque todavía no haya proveedor de WhatsApp.
        notificaciones.encolar(
            db, evento, CanalNotificacion.WHATSAPP, usuario.telefono, datos,
            usuario_id=usuario.id, reserva_id=reserva.id,
        )


def _avisar_al_prestador(
    db: Session, reserva: Reserva, evento: str, extra: dict | None = None
) -> None:
    item = reserva.items[0]
    prestador = item.unidad.publicacion.prestador
    dueno = db.get(Usuario, prestador.usuario_id)
    if dueno is None:
        return
    viajero = db.get(Usuario, reserva.usuario_id)
    datos = {
        **_datos_para_aviso(reserva),
        "nombre": dueno.nombre,
        "viajero": f"{viajero.nombre} {viajero.apellido}" if viajero else "Un viajero",
        **(extra or {}),
    }
    notificaciones.encolar(
        db, evento, CanalNotificacion.EMAIL, dueno.email, datos,
        usuario_id=dueno.id, reserva_id=reserva.id,
    )
    if dueno.telefono:
        notificaciones.encolar(
            db, evento, CanalNotificacion.WHATSAPP, dueno.telefono, datos,
            usuario_id=dueno.id, reserva_id=reserva.id,
        )


def traer(db: Session, codigo: str) -> Reserva | None:
    return db.scalar(
        select(Reserva)
        .where(Reserva.codigo == codigo.upper().strip())
        .options(
            selectinload(Reserva.pagos),
            selectinload(Reserva.items).selectinload(ItemReserva.comision),
            selectinload(Reserva.items)
            .selectinload(ItemReserva.unidad)
            .selectinload(Unidad.publicacion)
            .selectinload(Publicacion.localidad)
            .selectinload(Localidad.provincia),
            selectinload(Reserva.items)
            .selectinload(ItemReserva.unidad)
            .selectinload(Unidad.publicacion)
            .selectinload(Publicacion.fotos),
        )
    )
