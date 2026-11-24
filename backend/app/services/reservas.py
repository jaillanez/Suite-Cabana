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
    BloqueoHorario,
    ComisionAplicada,
    CupoTomado,
    FranjaHoraria,
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
from app.services import (
    busqueda,
    comisiones,
    horarios,
    notificaciones,
    politicas,
    precios,
    salidas,
)
from app.services import precios_eventos as pe
from app.services.pagos.base import EstadoPago

ALFABETO_CODIGO = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"


#: Techo técnico de una estadía: el precio se calcula noche por noche y un rango
#: de años no tiene sentido. El tope de negocio, si se decide uno, va por debajo.
MAX_NOCHES = precios.ESTADIA_MAXIMA
# Un salón se reserva con más anticipación que una cabaña: casamientos y fiestas
# grandes se arreglan con más de un año.
VENTANA_EVENTOS_DIAS = 730
# Las cabañas de un paquete siguen al evento, no la ventana de 12 meses: tocan su
# día, y uno que cruza la medianoche termina al siguiente.
VENTANA_EVENTOS_DIAS_PAQUETE = VENTANA_EVENTOS_DIAS + 1


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
    ventana_dias: int = precios.VENTANA_DIAS,
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
    # Acá y no en precios: es el paso común de la reserva sola, el paquete y el
    # listado de cabañas sumables. Sin esto, con anticipación mínima 0 (lo
    # habitual) se podía reservar una noche que ya pasó.
    if fecha_inicio < hoy:
        raise NoSePuedeReservar("Esa fecha ya pasó")
    if (fecha_fin - fecha_inicio).days > MAX_NOCHES:
        raise NoSePuedeReservar(f"Se pueden reservar hasta {MAX_NOCHES} noches")

    try:
        precio = precios.calcular(
            busqueda.unidad_plana(unidad),
            busqueda.tarifas_de(unidad),
            fecha_inicio,
            fecha_fin,
            personas=personas,
            mascotas=mascotas,
            hoy=hoy,
            ventana_dias=ventana_dias,
        )
    except precios.NoDisponible as e:
        raise NoSePuedeReservar(str(e)) from e

    comision = _comision(db, publicacion, precio.subtotal, fecha_inicio, hoy)
    return Cotizacion(
        unidad=unidad,
        precio=precio,
        comision=comision,
        total_viajero=_r(precio.subtotal + comision.cargo_viajero),
        noches=precio.cantidad_noches,
    )


def _comision(
    db: Session, publicacion: Publicacion, monto: Decimal, fecha_servicio: date, hoy: date
) -> comisiones.ResultadoComision:
    """La comisión que corresponde, con el motor de reglas (docs/00 §7)."""
    reglas = [comisiones.regla_desde_modelo(m) for m in db.scalars(select(ReglaComision))]
    ctx = comisiones.ContextoComision(
        monto=monto,
        fecha_servicio=fecha_servicio,
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
        return comisiones.resolver(reglas, ctx, get_settings().iva_comision)
    except comisiones.SinReglaAplicable as e:
        # Sin regla por defecto no se reserva: la comisión no se improvisa.
        raise NoSePuedeReservar(
            "No podemos calcular la comisión. Avisale al equipo antes de seguir."
        ) from e


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

    reserva = Reserva(
        codigo=generar_codigo(db),
        usuario_id=usuario.id,
        estado=EstadoReserva.PENDIENTE_PAGO,
        total=cotizacion.total_viajero,
        monto_sena=_sena(publicacion, cotizacion.total_viajero),
        vence_pago_en=datetime.now(UTC) + timedelta(minutes=s.minutos_retencion_pago),
        politica_cancelacion=politicas.snapshot(publicacion),
    )
    db.add(reserva)
    db.flush()

    _retener_estadia(
        db, reserva, Estadia(unidad, fecha_inicio, fecha_fin, personas, menores, mascotas),
        cotizacion,
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


@dataclass(frozen=True)
class Estadia:
    """Noches en una unidad de alojamiento: sola, o sumada a un evento (paquete)."""

    unidad: Unidad
    fecha_inicio: date
    fecha_fin: date
    personas: int = 2
    menores: int = 0
    mascotas: int = 0


def _retener_estadia(
    db: Session, reserva: Reserva, e: Estadia, cotizacion: Cotizacion
) -> ItemReserva:
    """El ítem de una estadía, su comisión y la retención de las noches.

    El choque con otra reserva no se detecta acá sino al hacer flush (lo decide
    la restricción de exclusión): quien llama lo traduce.
    """
    publicacion = e.unidad.publicacion
    item = ItemReserva(
        reserva_id=reserva.id,
        unidad_id=e.unidad.id,
        prestador_id=publicacion.prestador_id,
        fecha_inicio=e.fecha_inicio,
        fecha_fin=e.fecha_fin,
        adultos=e.personas,
        menores=e.menores,
        mascotas=e.mascotas,
        desglose=cotizacion.precio.desglose(),
        subtotal=cotizacion.precio.subtotal,
        politica_cancelacion=politicas.snapshot(publicacion),
    )
    db.add(item)
    db.flush()
    _guardar_comision(db, item, cotizacion.comision)
    db.add(
        BloqueoFecha(
            unidad_id=e.unidad.id,
            rango=Range(e.fecha_inicio, e.fecha_fin, bounds="[)"),
            origen=OrigenBloqueo.RETENCION,
            activo=True,
            vence_en=reserva.vence_pago_en,
            item_reserva_id=item.id,
            nota=f"Retención de la reserva {reserva.codigo}",
        )
    )
    return item


def _sena(publicacion: Publicacion, total: Decimal) -> Decimal | None:
    """La seña de la publicación o, si no tiene, la del prestador. None: total."""
    porcentaje = publicacion.porcentaje_sena
    if porcentaje is None:
        porcentaje = publicacion.prestador.porcentaje_sena
    if not porcentaje or porcentaje >= 100:
        return None
    return _r(total * Decimal(porcentaje) / 100)


def monto_a_cobrar(reserva: Reserva) -> Decimal:
    """Lo que se le cobra online al viajero: la seña si hay, si no el total."""
    return reserva.monto_sena if reserva.monto_sena else reserva.total


@dataclass(frozen=True)
class Reparto:
    """Cómo se reparte el total de la reserva, sumando todos sus ítems."""

    neto_prestador: Decimal  # lo del anfitrión, ya descontada su parte de comisión
    comision_neta: Decimal
    iva: Decimal
    comision_total: Decimal


def reparto(reserva: Reserva) -> Reparto:
    neto = neta = iva = total = Decimal(0)
    for i in reserva.items:
        c = i.comision
        neto += i.subtotal - (c.descuento_prestador if c else 0)
        if c:
            neta += c.comision_neta
            iva += c.iva
            total += c.comision_total
    return Reparto(_r(neto), _r(neta), _r(iva), _r(total))


def pagado(reserva: Reserva) -> Decimal:
    return _r(sum((p.monto for p in reserva.pagos if p.estado == "aprobado"), Decimal(0)))


def _guardar_comision(db: Session, item: ItemReserva, comision) -> None:
    """Snapshot de la comisión: cambiar la regla después no toca esta reserva."""
    db.add(
        ComisionAplicada(
            item_reserva_id=item.id,
            regla_id=comision.regla.id,
            regla_snapshot=comision.regla.a_dict(),
            base=comision.base,
            comision_neta=comision.comision_neta,
            iva=comision.iva,
            comision_total=comision.comision_total,
            cargo_viajero=comision.cargo_viajero,
            descuento_prestador=comision.descuento_prestador,
        )
    )


# --- Eventos: lo que se reserva por horario (docs/04) ---


@dataclass(frozen=True)
class CotizacionEvento:
    unidad: Unidad
    precio: pe.PrecioEvento
    comision: comisiones.ResultadoComision
    total_viajero: Decimal
    sena: Decimal | None


def salon_plano(unidad: Unidad) -> pe.Salon:
    return pe.Salon(
        capacidad=unidad.capacidad,
        capacidad_base=unidad.capacidad_base,
        cargo_persona_extra=unidad.cargo_persona_extra,
        preparacion_minutos=unidad.preparacion_minutos or 0,
    )


def franja_plana(f: FranjaHoraria) -> pe.Franja:
    return pe.Franja(
        id=str(f.id), nombre=f.nombre, hora_inicio=f.hora_inicio, hora_fin=f.hora_fin,
        precio=f.precio, precios_dia_semana=f.precios_dia_semana,
    )


def tarifa_horas(unidad: Unidad) -> pe.TarifaHoras | None:
    t = unidad.tarifa_horaria
    if t is None or not t.activa:
        return None
    return pe.TarifaHoras(
        precio_hora=t.precio_hora,
        hora_apertura=t.hora_apertura,
        hora_cierre=t.hora_cierre,
        horas_minimas=t.horas_minimas,
        precios_dia_semana=t.precios_dia_semana,
        recargo_nocturno_desde=t.recargo_nocturno_desde,
        recargo_nocturno_porcentaje=t.recargo_nocturno_porcentaje,
    )


def cotizar_evento(
    db: Session,
    unidad: Unidad,
    dia: date,
    invitados: int,
    franja_id: uuid.UUID | None = None,
    hora_inicio=None,
    horas: int | None = None,
    adicionales: list[uuid.UUID] | tuple = (),
    hoy: date | None = None,
    ahora: datetime | None = None,
) -> CotizacionEvento:
    """Precio, comisión y seña de un evento, sin tocar nada."""
    hoy = hoy or date.today()
    ahora = ahora or datetime.now(UTC)
    publicacion = unidad.publicacion
    if publicacion.estado is not EstadoPublicacion.APROBADA or not unidad.activa:
        raise NoSePuedeReservar("Ese salón no está disponible")
    if publicacion.tipo_servicio.modo_reserva is not ModoReserva.HORAS:
        raise NoSePuedeReservar("Esto no se reserva por horario")
    if (dia - hoy).days > VENTANA_EVENTOS_DIAS:
        raise NoSePuedeReservar("Los salones se reservan hasta 24 meses antes")

    elegidos = set(adicionales)
    disponibles = {a.id: a for a in unidad.adicionales if a.activo}
    if elegidos - disponibles.keys():
        raise NoSePuedeReservar("Alguno de los adicionales elegidos no existe")
    extras = [
        pe.Adicional(id=str(a.id), nombre=a.nombre, precio=a.precio, por_persona=a.por_persona)
        for a in disponibles.values()
        if a.id in elegidos
    ]

    try:
        if franja_id is not None:
            franja = next(
                (f for f in unidad.franjas if f.id == franja_id and f.activa), None
            )
            if franja is None:
                raise NoSePuedeReservar("Ese turno no existe")
            precio = pe.por_franja(
                salon_plano(unidad), franja_plana(franja), dia, invitados, extras
            )
        elif hora_inicio is not None and horas is not None:
            tarifa = tarifa_horas(unidad)
            if tarifa is None:
                raise NoSePuedeReservar("Este salón no se alquila por horas")
            precio = pe.por_horas(
                salon_plano(unidad), tarifa, dia, hora_inicio, horas, invitados, extras
            )
        else:
            raise NoSePuedeReservar(
                "Elegí un turno, o un horario de inicio y la cantidad de horas"
            )
    except pe.EventoNoDisponible as e:
        raise NoSePuedeReservar(str(e)) from e

    if precio.inicio <= ahora:
        raise NoSePuedeReservar("Ese horario ya pasó")

    comision = _comision(db, publicacion, precio.subtotal, dia, hoy)
    total = _r(precio.subtotal + comision.cargo_viajero)
    return CotizacionEvento(
        unidad=unidad,
        precio=precio,
        comision=comision,
        total_viajero=total,
        sena=_sena(publicacion, total),
    )


#: Cuántos alojamientos se pueden sumar a un evento en una reserva.
MAX_ESTADIAS = 6
#: Noches máximas de cada alojamiento sumado. Sin tope, un solo pedido retendría
#: hasta seis cabañas por meses mientras "paga".
MAX_NOCHES_PAQUETE = 14


@dataclass(frozen=True)
class CotizacionPaquete:
    """Un evento y, si se suman, las estadías del mismo anfitrión (docs/04 S11)."""

    evento: CotizacionEvento
    estadias: list[tuple[Estadia, Cotizacion]]
    total_viajero: Decimal
    sena: Decimal | None


def _nombre(unidad: Unidad) -> str:
    return f"{unidad.publicacion.titulo} · {unidad.nombre}"


def cotizar_paquete(
    db: Session,
    unidad: Unidad,
    dia: date,
    invitados: int,
    franja_id: uuid.UUID | None = None,
    hora_inicio=None,
    horas: int | None = None,
    adicionales: list[uuid.UUID] | tuple = (),
    estadias: list[Estadia] | tuple = (),
    hoy: date | None = None,
    ahora: datetime | None = None,
) -> CotizacionPaquete:
    """El evento más las noches que se suman, sin tocar nada.

    Cada estadía se cotiza igual que sola (mismo precio, su propia comisión); la
    seña es la del salón sobre el total del paquete: se reserva desde el salón.
    """
    hoy = hoy or date.today()
    ev = cotizar_evento(
        db, unidad, dia, invitados, franja_id, hora_inicio, horas, adicionales, hoy, ahora
    )
    if len(estadias) > MAX_ESTADIAS:
        raise NoSePuedeReservar(f"Se pueden sumar hasta {MAX_ESTADIAS} alojamientos")

    prestador_id = unidad.publicacion.prestador_id
    fin_evento = ev.precio.fin.astimezone(pe.ZONA).date()
    vistas: set[uuid.UUID] = set()
    cotizadas: list[tuple[Estadia, Cotizacion]] = []
    for e in estadias:
        # Primero de quién es: de una unidad ajena no se dice ni el nombre.
        # Un solo pago entra en una sola cuenta: el paquete es de un anfitrión.
        if e.unidad.publicacion.prestador_id != prestador_id:
            raise NoSePuedeReservar(
                "Al salón solo se le pueden sumar alojamientos del mismo anfitrión"
            )
        if e.unidad.id in vistas:
            raise NoSePuedeReservar(f"{_nombre(e.unidad)} está elegida dos veces")
        vistas.add(e.unidad.id)
        if (e.fecha_fin - e.fecha_inicio).days > MAX_NOCHES_PAQUETE:
            raise NoSePuedeReservar(
                f"{_nombre(e.unidad)}: se pueden sumar hasta {MAX_NOCHES_PAQUETE} noches"
            )
        # Las noches tienen que tocar el evento: llegar antes o irse después vale,
        # una estadía de otro mes no es un paquete.
        if e.fecha_inicio > fin_evento or e.fecha_fin < dia:
            raise NoSePuedeReservar(
                f"{_nombre(e.unidad)}: la estadía tiene que coincidir con el evento"
            )
        try:
            c = cotizar(
                db, e.unidad, e.fecha_inicio, e.fecha_fin,
                e.personas + e.menores, e.mascotas, hoy,
                ventana_dias=VENTANA_EVENTOS_DIAS_PAQUETE,
            )
        except NoSePuedeReservar as err:
            raise NoSePuedeReservar(f"{_nombre(e.unidad)}: {err}") from err
        cotizadas.append((e, c))

    total = _r(ev.total_viajero + sum((c.total_viajero for _, c in cotizadas), Decimal(0)))
    return CotizacionPaquete(
        evento=ev,
        estadias=cotizadas,
        total_viajero=total,
        sena=_sena(unidad.publicacion, total),
    )


def crear_evento(
    db: Session,
    usuario: Usuario,
    unidad: Unidad,
    dia: date,
    invitados: int,
    franja_id: uuid.UUID | None = None,
    hora_inicio=None,
    horas: int | None = None,
    adicionales: list[uuid.UUID] | tuple = (),
    estadias: list[Estadia] | tuple = (),
    hoy: date | None = None,
) -> Reserva:
    """Crea la reserva del evento —y de las noches que se sumen— y retiene todo
    mientras el viajero paga.

    Igual que con las noches, el choque lo decide la base (`horarios.bloquear`):
    se retiene el evento más el tiempo de preparación posterior. Con un paquete,
    o se retiene todo o nada: todo va en la misma transacción y cualquier choque
    la deshace entera.
    """
    if not usuario.email_verificado:
        raise NoSePuedeReservar("Verificá tu correo antes de reservar")
    paquete = cotizar_paquete(
        db, unidad, dia, invitados, franja_id, hora_inicio, horas, adicionales, estadias, hoy
    )
    cot = paquete.evento
    inicio, fin_bloqueo = pe.rango_ocupado(cot.precio, salon_plano(unidad))
    if not horarios.libre(db, unidad.id, inicio, fin_bloqueo):
        raise FechasTomadas("Ese horario ya no está disponible")
    for e, _ in paquete.estadias:
        if not _libre(db, e.unidad.id, e.fecha_inicio, e.fecha_fin):
            raise FechasTomadas(f"{_nombre(e.unidad)}: esas fechas ya no están disponibles")

    s = get_settings()
    publicacion = unidad.publicacion
    reserva = Reserva(
        codigo=generar_codigo(db),
        usuario_id=usuario.id,
        estado=EstadoReserva.PENDIENTE_PAGO,
        total=paquete.total_viajero,
        monto_sena=paquete.sena,
        vence_pago_en=datetime.now(UTC) + timedelta(minutes=s.minutos_retencion_pago),
        politica_cancelacion=politicas.snapshot(publicacion),
    )
    db.add(reserva)
    db.flush()

    item = ItemReserva(
        reserva_id=reserva.id,
        unidad_id=unidad.id,
        prestador_id=publicacion.prestador_id,
        fecha_inicio=dia,
        fecha_fin=cot.precio.fin.astimezone(pe.ZONA).date(),
        inicio_en=cot.precio.inicio,
        fin_en=cot.precio.fin,
        adultos=invitados,
        menores=0,
        mascotas=0,
        desglose=cot.precio.desglose(),
        subtotal=cot.precio.subtotal,
        politica_cancelacion=politicas.snapshot(publicacion),
    )
    db.add(item)
    db.flush()
    _guardar_comision(db, item, cot.comision)

    try:
        horarios.bloquear(
            db, unidad, inicio, fin_bloqueo, OrigenBloqueo.RETENCION,
            vence_en=reserva.vence_pago_en,
            nota=f"Retención de la reserva {reserva.codigo}",
            item_reserva_id=item.id,
        )
    except horarios.HorarioOcupado as e:
        db.rollback()
        raise FechasTomadas(
            "Alguien reservó ese horario mientras completabas. Probá con otro."
        ) from e

    for e, c in paquete.estadias:
        _retener_estadia(db, reserva, e, c)
    try:
        db.flush()
    except IntegrityError as err:
        # Se deshace todo, el salón incluido: el paquete no se reserva a medias.
        db.rollback()
        raise FechasTomadas(
            "Alguien reservó uno de los alojamientos mientras completabas. "
            "Probá con otras fechas o sin ese alojamiento."
        ) from err

    _avisar_al_viajero(db, reserva, "reserva_creada")
    return reserva


#: Pago aprobado por un monto menor al de la reserva: no la confirma.
ESTADO_MONTO_DISTINTO = "monto_distinto"
#: Pago aprobado que llegó tarde, con el lugar ya liberado: hay que devolverlo.
ESTADO_SIN_LUGAR = "aprobado_sin_lugar"


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
    partes = reparto(reserva)

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
            monto_prestador=partes.neto_prestador,
            monto_comision=partes.comision_neta,
            iva_comision=partes.iva,
        )
        db.add(pago)

    pago.id_externo = id_externo
    pago.estado = estado.value
    if monto is not None:
        pago.monto = monto
    if datos:
        pago.datos = datos

    # El cobro se pide por la seña o el total (`monto_a_cobrar`). Un pago aprobado
    # por menos —uno armado a mano con el mismo código de reserva, o un error de
    # la pasarela— no confirma: queda a la vista para revisarlo.
    if estado is EstadoPago.APROBADO and monto is not None and monto < monto_a_cobrar(reserva):
        pago.estado = ESTADO_MONTO_DISTINTO
        db.flush()
        return reserva

    if estado is EstadoPago.APROBADO:
        # Un pago que llega cuando la reserva ya se canceló —venció el plazo y la
        # tarea soltó las fechas— no la revive: otro pudo haber tomado ese lugar.
        # Falla cerrado: el pago queda marcado para devolverlo.
        if reserva.estado is EstadoReserva.CANCELADA or not _confirmar(db, reserva):
            pago.estado = ESTADO_SIN_LUGAR
            if reserva.estado is not EstadoReserva.CANCELADA:
                _liberar(
                    db, reserva,
                    "El pago llegó cuando el lugar ya estaba tomado: corresponde devolverlo",
                )
    elif estado in (EstadoPago.RECHAZADO, EstadoPago.CANCELADO):
        _liberar(db, reserva, "El pago no se completó")
    elif estado is EstadoPago.DEVUELTO:
        _liberar(db, reserva, "El pago fue devuelto")

    db.flush()
    return reserva


def _afirmar_bloqueos(db: Session, reserva: Reserva) -> bool:
    """Pasa las retenciones de todos los ítems a reserva firme. False si algún
    lugar ya no está: en un paquete se confirma todo o nada.

    Una retención vencida pudo haberse desactivado y otro tomado ese lugar: al
    reactivarla, la restricción de exclusión lo rechaza. Se prueba en un
    savepoint para no arrastrar la transacción del aviso de pago.
    """
    # Releídos de la base: una copia en memoria puede decir "activo" de un bloqueo
    # que otra operación ya desactivó, y entonces reactivarlo no mandaría nada a
    # la base y la restricción de exclusión nunca tendría la chance de rechazarlo.
    releer = {"populate_existing": True}
    ids = [i.id for i in reserva.items]
    bloqueos = [
        *db.scalars(
            select(BloqueoFecha)
            .where(BloqueoFecha.item_reserva_id.in_(ids))
            .execution_options(**releer)
        ),
        *db.scalars(
            select(BloqueoHorario)
            .where(BloqueoHorario.item_reserva_id.in_(ids))
            .execution_options(**releer)
        ),
    ]
    # Las excursiones no bloquean un rango: toman lugares de una salida.
    cupos = list(
        db.scalars(
            select(CupoTomado)
            .where(CupoTomado.item_reserva_id.in_(ids))
            .order_by(CupoTomado.creado_en)
            .execution_options(**releer)
        )
    )
    # Cada ítem tiene que tener su bloqueo: si a uno le falta, ese lugar se soltó.
    if {b.item_reserva_id for b in bloqueos} | {c.item_reserva_id for c in cupos} != set(ids):
        return False
    por_item: dict[uuid.UUID, list[CupoTomado]] = {}
    for c in cupos:
        por_item.setdefault(c.item_reserva_id, []).append(c)
    try:
        with db.begin_nested():
            for bloqueo in bloqueos:
                bloqueo.origen = OrigenBloqueo.RESERVA
                bloqueo.vence_en = None
                bloqueo.activo = True
                bloqueo.nota = f"Reserva {reserva.codigo}"
            for item_id, tomados in por_item.items():
                activos = [t for t in tomados if t.activo]
                for t in activos:
                    t.origen = OrigenBloqueo.RESERVA
                    t.vence_en = None
                    t.nota = f"Reserva {reserva.codigo}"
                if not activos:
                    # La retención venció y se soltó: se vuelve a pedir el lugar, y
                    # si ya no hay (o la salida no va), no se confirma.
                    ultimo = tomados[-1]
                    salidas.tomar(
                        db, ultimo.salida, ultimo.personas, OrigenBloqueo.RESERVA,
                        item_reserva_id=item_id, nota=f"Reserva {reserva.codigo}",
                    )
            db.flush()
    except (IntegrityError, salidas.SinCupo, salidas.SalidaInvalida):
        return False
    return True


def _confirmar(db: Session, reserva: Reserva) -> bool:
    """Pago aprobado: la retención pasa a ser una reserva firme.

    Devuelve False, sin tocar el estado, si el lugar ya no está disponible.
    """
    if reserva.estado in (EstadoReserva.CONFIRMADA, EstadoReserva.COMPLETADA):
        return True  # idempotente

    if not _afirmar_bloqueos(db, reserva):
        return False
    # El anfitrión aprueba o rechaza el paquete entero: si alguna parte es "a
    # solicitud", lo es toda la reserva.
    inmediata = all(i.unidad.publicacion.confirmacion_inmediata for i in reserva.items)
    s = get_settings()

    reserva.estado = (
        EstadoReserva.CONFIRMADA if inmediata else EstadoReserva.PENDIENTE_APROBACION
    )
    reserva.vence_pago_en = None
    if not inmediata:
        reserva.vence_aprobacion_en = datetime.now(UTC) + timedelta(
            hours=s.horas_aprobacion_prestador
        )

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
    return True


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
        for bloqueo in [
            *db.scalars(select(BloqueoFecha).where(BloqueoFecha.item_reserva_id == item.id)),
            *db.scalars(select(BloqueoHorario).where(BloqueoHorario.item_reserva_id == item.id)),
        ]:
            db.delete(bloqueo)
        # Los lugares de una excursión vuelven a la salida; el registro queda.
        for tomado in db.scalars(
            select(CupoTomado).where(
                CupoTomado.item_reserva_id == item.id, CupoTomado.activo.is_(True)
            )
        ).all():
            salidas.soltar(db, tomado)


@dataclass(frozen=True)
class Reintegro:
    porcentaje: int
    monto: Decimal
    motivo: str


def calcular_reintegro(reserva: Reserva, hoy: date | None = None) -> Reintegro:
    """Cuánto se devuelve según la política que la reserva guardó (docs/01 §5 R8).

    Se usa el snapshot, no la política actual: el viajero aceptó la de ese momento.

    En un paquete cada ítem cancela con su política y desde su propia fecha: la
    plata pagada se reparte entre los ítems según lo que vale cada uno, y el
    reintegro es la suma (docs/04 S11).
    """
    hoy = hoy or date.today()
    # Sobre lo que entró, no sobre el total: con seña no se devuelve plata que el
    # viajero nunca pagó. Si todavía no pagó, sobre lo que tendría que pagar.
    base = pagado(reserva) or monto_a_cobrar(reserva)
    items = sorted(reserva.items, key=lambda i: (i.fecha_inicio, i.inicio_en is None))
    if len(items) <= 1:
        porcentaje, motivo = _tramo(
            (items[0].politica_cancelacion if items else None) or reserva.politica_cancelacion,
            min((i.fecha_inicio for i in items), default=hoy),
            hoy,
        )
        return Reintegro(porcentaje, _r(base * Decimal(porcentaje) / 100), motivo)

    valores = [
        i.subtotal + (i.comision.cargo_viajero if i.comision else Decimal(0)) for i in items
    ]
    suma = sum(valores, Decimal(0)) or Decimal(1)
    monto, repartido = Decimal(0), Decimal(0)
    detalle = []
    for n, (item, valor) in enumerate(zip(items, valores, strict=True)):
        # La última parte se lleva el resto: los centavos del redondeo no se pierden.
        parte = base - repartido if n == len(items) - 1 else _r(base * valor / suma)
        repartido += parte
        # Solo la del ítem: una cabaña sin política no hereda la de eventos del salón.
        porcentaje, _ = _tramo(item.politica_cancelacion, item.fecha_inicio, hoy)
        monto += _r(parte * Decimal(porcentaje) / 100)
        detalle.append(f"{item.unidad.nombre} {porcentaje} %")
    monto = _r(monto)
    return Reintegro(
        porcentaje=int((monto * 100 / base).to_integral_value()) if base else 0,
        monto=monto,
        motivo="Cada parte con su política: " + ", ".join(detalle),
    )


def _tramo(politica: dict | None, inicio: date, hoy: date) -> tuple[int, str]:
    """El porcentaje de reintegro de una política a tantos días del inicio."""
    tramos = (politica or {}).get("tramos") or []
    if not tramos:
        return 0, "Esta reserva no tiene política de cancelación"
    faltan = (inicio - hoy).days
    # Gana el tramo más exigente que el viajero todavía alcanza.
    elegibles = [t for t in tramos if faltan >= int(t.get("dias_antes", 0))]
    if not elegibles:
        return 0, "Ya pasó el plazo para cancelar con reintegro"
    mejor = max(elegibles, key=lambda t: int(t.get("porcentaje_reintegro", 0)))
    return int(mejor.get("porcentaje_reintegro", 0)), f"Cancelás con {faltan} días de anticipación"


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


def principal(reserva: Reserva) -> ItemReserva:
    """El ítem que da nombre a la reserva: el evento si hay (en un traslado de ida
    y vuelta, el primer viaje), si no el primero."""
    con_hora = [i for i in reserva.items if i.inicio_en]
    return min(con_hora, key=lambda i: i.inicio_en) if con_hora else reserva.items[0]


def ordenados(reserva: Reserva) -> list[ItemReserva]:
    """Los ítems para mostrar: el principal primero, después por fecha."""
    item = principal(reserva)
    resto = sorted(
        (i for i in reserva.items if i is not item),
        key=lambda i: (i.fecha_inicio, i.unidad.publicacion.titulo, i.unidad.nombre),
    )
    return [item, *resto]


def _recorrido(item: ItemReserva) -> str:
    d = item.desglose or {}
    return f"{d.get('origen', '')} → {d.get('destino', '')}"


def _datos_para_aviso(reserva: Reserva) -> dict:
    """Lo que las plantillas necesitan saber de la reserva."""
    item = principal(reserva)
    publicacion = item.unidad.publicacion
    web = get_settings().url_publica_web.rstrip("/")
    neto = reparto(reserva).neto_prestador
    personas = item.adultos + item.menores
    if item.inicio_en and item.fin_en:
        # Un evento: "del 15/03/2027 21:00 al 16/03/2027 05:00 h", no dos fechas.
        desde = item.inicio_en.astimezone(pe.ZONA).strftime("%d/%m/%Y %H:%M")
        hasta = item.fin_en.astimezone(pe.ZONA).strftime("%d/%m/%Y %H:%M h")
        palabra = {ModoReserva.HORAS: "invitado", ModoReserva.TRAMO: "pasajero"}.get(
            publicacion.tipo_servicio.modo_reserva, "persona"
        )
        quienes = f"{personas} {palabra}" + ("s" if personas != 1 else "")
    else:
        desde = item.fecha_inicio.strftime("%d/%m/%Y")
        hasta = item.fecha_fin.strftime("%d/%m/%Y")
        quienes = f"{personas} persona" + ("s" if personas != 1 else "")
    unidad = item.unidad.nombre
    sumadas = ordenados(reserva)[1:]
    if publicacion.tipo_servicio.modo_reserva is ModoReserva.TRAMO:
        # Un traslado: el recorrido, y la vuelta si la hay (docs/06).
        unidad += f": {_recorrido(item)}"
        for i in sumadas:
            sale = i.inicio_en.astimezone(pe.ZONA)
            unidad += f"; vuelta {_recorrido(i)} el {sale:%d/%m/%Y %H:%M} h"
    elif sumadas:
        # Paquete: las plantillas hablan de una unidad; se nombran las demás ahí.
        unidad += "; además " + ", ".join(
            f"{i.unidad.nombre} de {i.unidad.publicacion.titulo} del "
            f"{i.fecha_inicio:%d/%m/%Y} al {i.fecha_fin:%d/%m/%Y}"
            for i in sumadas
        )
    return {
        "codigo": reserva.codigo,
        "alojamiento": publicacion.titulo,
        "unidad": unidad,
        "desde": desde,
        "hasta": hasta,
        "total": f"$ {reserva.total:,.2f}".replace(",", "."),
        "neto": f"$ {neto:,.2f}".replace(",", "."),
        "personas": quienes,
        "enlace": f"{web}/reservas/{reserva.codigo}",
    }


def _avisar_al_viajero(
    db: Session, reserva: Reserva, evento: str, extra: dict | None = None
) -> None:
    usuario = db.get(Usuario, reserva.usuario_id)
    if usuario is None:
        return
    datos = {**_datos_para_aviso(reserva), "nombre": usuario.nombre, **(extra or {})}
    # Solo por correo: WhatsApp es el botón de la reserva (app.services.contacto).
    notificaciones.encolar(
        db, evento, CanalNotificacion.EMAIL, usuario.email, datos,
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
