"""Reservar un traslado (docs/06, etapa 2).

Sigue el mismo circuito que un evento (`reservas`): cotización, retención con
vencimiento mientras se paga, confirmación con el pago y snapshot de comisión y
política. Lo propio de un traslado:

- Cada extremo es un **lugar** del prestador ("Aeropuerto") o un **punto** con
  su dirección. De lugar a lugar, con un tramo cargado, se cobra el tramo; si no,
  por kilómetro (si el vehículo cobra así).
- **Ida y vuelta** son dos ítems de la misma reserva: cada viaje tiene su precio,
  su comisión y su retención, y se confirman o se caen juntos.
- Si la vuelta sale antes de que el vehículo alcance a volver a la base, el
  chofer espera: la ocupación de la ida termina donde empieza la vuelta, y entre
  las dos el vehículo queda tomado sin hueco.
- Los datos del viaje (vuelo, dirección exacta, notas) van aparte del precio, en
  `item_reserva.datos_servicio`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ItemReserva, LugarTraslado, Reserva, Unidad, Usuario
from app.models.enums import EstadoPublicacion, EstadoReserva, ModoReserva, OrigenBloqueo
from app.services import comisiones, politicas, reservas, traslados
from app.services import precios_traslado as pt
from app.services.precios_eventos import ZONA

VUELO_MAX = 20
DIRECCION_MAX = 200
NOTAS_MAX = 500

ESTADOS_VIGENTES = (
    EstadoReserva.PENDIENTE_PAGO,
    EstadoReserva.PENDIENTE_APROBACION,
    EstadoReserva.CONFIRMADA,
)


@dataclass(frozen=True)
class Extremo:
    """Un lugar del prestador, o un punto del mapa con su dirección."""

    lugar_id: uuid.UUID | None = None
    punto: pt.Punto | None = None
    #: Con un lugar es la precisión ("Hotel Lago, Mitre 120"); con un punto, obligatoria.
    direccion: str | None = None


@dataclass(frozen=True)
class Pedido:
    origen: Extremo
    destino: Extremo
    inicio: datetime
    pasajeros: int
    valijas: int = 0
    vuelta_inicio: datetime | None = None
    vuelo_ida: str | None = None
    vuelo_vuelta: str | None = None
    notas: str | None = None


@dataclass(frozen=True)
class Viaje:
    sentido: str  # "ida" | "vuelta"
    origen: str
    destino: str
    cobro: str  # "tramo" | "km"
    precio: pt.PrecioTraslado
    #: Hasta cuándo se toma el vehículo por este viaje: puede ser antes que
    #: `precio.ocupado_hasta` si la vuelta sale mientras volvía a la base.
    ocupado_hasta: datetime
    comision: comisiones.ResultadoComision

    @property
    def total(self) -> Decimal:
        return reservas._r(self.precio.subtotal + self.comision.cargo_viajero)


@dataclass(frozen=True)
class CotizacionTraslado:
    unidad: Unidad
    viajes: list[Viaje]
    subtotal: Decimal
    cargo_servicio: Decimal
    total_viajero: Decimal
    sena: Decimal | None


def _texto(valor: str | None, maximo: int, que: str) -> str | None:
    valor = (valor or "").strip()
    if len(valor) > maximo:
        raise reservas.NoSePuedeReservar(f"{que}: hasta {maximo} caracteres")
    return valor or None


def _lugar(db: Session, unidad: Unidad, lugar_id: uuid.UUID) -> LugarTraslado:
    lugar = db.get(LugarTraslado, lugar_id)
    if lugar is None or lugar.publicacion_id != unidad.publicacion_id or not lugar.activo:
        raise reservas.NoSePuedeReservar("Ese lugar no es de este traslado")
    return lugar


def _nombre(db: Session, unidad: Unidad, e: Extremo) -> str:
    if e.lugar_id:
        return _lugar(db, unidad, e.lugar_id).nombre
    return "Dirección elegida"


def _punto(db: Session, unidad: Unidad, e: Extremo) -> pt.Punto:
    if e.lugar_id:
        return traslados.punto(db, _lugar(db, unidad, e.lugar_id))
    return e.punto


def _validar_extremo(e: Extremo) -> None:
    if (e.lugar_id is None) == (e.punto is None):
        raise reservas.NoSePuedeReservar("Elegí un lugar o marcá un punto en el mapa")
    if e.punto is not None and not (e.direccion or "").strip():
        raise reservas.NoSePuedeReservar("Indicá la dirección del punto que marcaste")
    _texto(e.direccion, DIRECCION_MAX, "La dirección")


def _precio(
    db: Session, unidad: Unidad, origen: Extremo, destino: Extremo, inicio: datetime,
    pasajeros: int, valijas: int, ahora: datetime,
) -> tuple[str, pt.PrecioTraslado]:
    """El tramo fijo si hay uno de lugar a lugar; si no, por kilómetro."""
    try:
        if origen.lugar_id and destino.lugar_id:
            _lugar(db, unidad, origen.lugar_id)
            _lugar(db, unidad, destino.lugar_id)
            if traslados.tramo_entre(db, unidad, origen.lugar_id, destino.lugar_id):
                return "tramo", traslados.cotizar_tramo(
                    db, unidad, origen.lugar_id, destino.lugar_id, inicio, pasajeros,
                    valijas, ahora,
                )
        if traslados.reglas(db, unidad).precio_km is None:
            raise reservas.NoSePuedeReservar("Este vehículo no hace ese recorrido")
        return "km", traslados.cotizar_km(
            db, unidad, _punto(db, unidad, origen), _punto(db, unidad, destino), inicio,
            pasajeros, valijas, ahora,
        )
    except pt.TrasladoInvalido as e:
        raise reservas.NoSePuedeReservar(str(e)) from e


def cotizar_traslado(
    db: Session, unidad: Unidad, pedido: Pedido, ahora: datetime | None = None
) -> CotizacionTraslado:
    """Precio de la ida (y la vuelta), comisión y seña, sin tocar nada."""
    ahora = ahora or datetime.now(UTC)
    publicacion = unidad.publicacion
    if publicacion.estado is not EstadoPublicacion.APROBADA or not unidad.activa:
        raise reservas.NoSePuedeReservar("Ese traslado no está disponible")
    if publicacion.tipo_servicio.modo_reserva is not ModoReserva.TRAMO:
        raise reservas.NoSePuedeReservar("Esto no es un traslado")
    for e in (pedido.origen, pedido.destino):
        _validar_extremo(e)
    _texto(pedido.vuelo_ida, VUELO_MAX, "El vuelo")
    _texto(pedido.vuelo_vuelta, VUELO_MAX, "El vuelo")
    _texto(pedido.notas, NOTAS_MAX, "Las notas")

    hoy = ahora.astimezone(ZONA).date()
    tramos = [("ida", pedido.origen, pedido.destino, pedido.inicio)]
    if pedido.vuelta_inicio is not None:
        tramos.append(("vuelta", pedido.destino, pedido.origen, pedido.vuelta_inicio))

    calculados = []
    for sentido, origen, destino, inicio in tramos:
        cobro, precio = _precio(
            db, unidad, origen, destino, inicio, pedido.pasajeros, pedido.valijas, ahora
        )
        calculados.append((sentido, origen, destino, cobro, precio))

    if len(calculados) == 2:
        ida, vuelta = calculados[0][4], calculados[1][4]
        if vuelta.inicio < ida.llegada:
            raise reservas.NoSePuedeReservar(
                "La vuelta tiene que salir después de que llega la ida"
            )

    viajes: list[Viaje] = []
    for n, (sentido, origen, destino, cobro, precio) in enumerate(calculados):
        ocupado_hasta = precio.ocupado_hasta
        if n == 0 and len(calculados) == 2:
            # El chofer espera la vuelta en vez de volver: no hay hueco que ofrecer.
            ocupado_hasta = min(ocupado_hasta, calculados[1][4].inicio)
        viajes.append(
            Viaje(
                sentido=sentido,
                origen=_nombre(db, unidad, origen),
                destino=_nombre(db, unidad, destino),
                cobro=cobro,
                precio=precio,
                ocupado_hasta=ocupado_hasta,
                comision=reservas._comision(
                    db, publicacion, precio.subtotal, precio.inicio.astimezone(ZONA).date(), hoy
                ),
            )
        )

    subtotal = reservas._r(sum((v.precio.subtotal for v in viajes), Decimal(0)))
    cargo = reservas._r(sum((v.comision.cargo_viajero for v in viajes), Decimal(0)))
    total = reservas._r(sum((v.total for v in viajes), Decimal(0)))
    return CotizacionTraslado(
        unidad=unidad,
        viajes=viajes,
        subtotal=subtotal,
        cargo_servicio=cargo,
        total_viajero=total,
        sena=reservas._sena(publicacion, total),
    )


def _datos(pedido: Pedido, sentido: str) -> dict:
    ida = sentido == "ida"
    origen, destino = (
        (pedido.origen, pedido.destino) if ida else (pedido.destino, pedido.origen)
    )
    datos = {
        "vuelo": _texto(pedido.vuelo_ida if ida else pedido.vuelo_vuelta, VUELO_MAX, "El vuelo"),
        "direccion_origen": _texto(origen.direccion, DIRECCION_MAX, "La dirección"),
        "direccion_destino": _texto(destino.direccion, DIRECCION_MAX, "La dirección"),
        "notas": _texto(pedido.notas, NOTAS_MAX, "Las notas"),
    }
    for clave, e in (("origen", origen), ("destino", destino)):
        if e.punto is not None:
            datos[f"punto_{clave}"] = {"lat": e.punto.lat, "lon": e.punto.lon}
    return datos


def crear_traslado(
    db: Session, usuario: Usuario, unidad: Unidad, pedido: Pedido,
    ahora: datetime | None = None,
) -> Reserva:
    """Crea la reserva y retiene el vehículo mientras el viajero paga.

    Que dos viajes no se pisen lo decide la base (`traslados.ocupar`): si entre la
    cotización y este momento otro tomó el vehículo, se deshace todo, la vuelta
    incluida.
    """
    if not usuario.email_verificado:
        raise reservas.NoSePuedeReservar("Verificá tu correo antes de reservar")
    cot = cotizar_traslado(db, unidad, pedido, ahora)
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

    for v in cot.viajes:
        item = ItemReserva(
            reserva_id=reserva.id,
            unidad_id=unidad.id,
            prestador_id=publicacion.prestador_id,
            fecha_inicio=v.precio.inicio.astimezone(ZONA).date(),
            fecha_fin=v.precio.llegada.astimezone(ZONA).date(),
            inicio_en=v.precio.inicio,
            fin_en=v.precio.llegada,
            adultos=pedido.pasajeros,
            menores=0,
            mascotas=0,
            desglose={
                **v.precio.desglose(),
                "sentido": v.sentido,
                "origen": v.origen,
                "destino": v.destino,
                "cobro": v.cobro,
                "valijas": pedido.valijas,
            },
            subtotal=v.precio.subtotal,
            politica_cancelacion=politicas.snapshot(publicacion),
            datos_servicio=_datos(pedido, v.sentido),
        )
        db.add(item)
        db.flush()
        reservas._guardar_comision(db, item, v.comision)
        try:
            traslados.ocupar(
                db, unidad,
                pt.PrecioTraslado(
                    inicio=v.precio.inicio, llegada=v.precio.llegada,
                    ocupado_hasta=v.ocupado_hasta, km=v.precio.km,
                ),
                OrigenBloqueo.RETENCION,
                vence_en=reserva.vence_pago_en,
                item_reserva_id=item.id,
                nota=f"Retención de la reserva {reserva.codigo}",
            )
        except traslados.NoDisponible as e:
            db.rollback()
            que = "la vuelta" if v.sentido == "vuelta" else "ese horario"
            raise reservas.FechasTomadas(
                f"El vehículo ya está tomado para {que}. Probá con otro horario."
            ) from e
        except pt.TrasladoInvalido as e:
            db.rollback()
            raise reservas.NoSePuedeReservar(str(e)) from e

    reservas._avisar_al_viajero(db, reserva, "reserva_creada")
    return reserva


def cambiar_datos(
    db: Session, reserva: Reserva, vuelo_ida: str | None, vuelo_vuelta: str | None,
    notas: str | None, ahora: datetime | None = None,
) -> Reserva:
    """El viajero corrige el vuelo o las notas (cambió el vuelo, viaja con un
    cochecito). Las direcciones no: con un punto del mapa, el precio salió de ahí.

    Solo en una reserva vigente y en los viajes que todavía no salieron.
    """
    ahora = ahora or datetime.now(UTC)
    if reserva.estado not in ESTADOS_VIGENTES:
        raise reservas.TransicionInvalida("Esta reserva ya no se puede cambiar")
    items = [i for i in reserva.items if i.datos_servicio is not None]
    if not items:
        raise reservas.TransicionInvalida("Esta reserva no tiene datos de viaje")
    cambiados = 0
    for item in items:
        if item.inicio_en is None or item.inicio_en <= ahora:
            continue
        datos = dict(item.datos_servicio)
        vuelo = vuelo_ida if item.desglose.get("sentido") != "vuelta" else vuelo_vuelta
        if vuelo is not None:
            datos["vuelo"] = _texto(vuelo, VUELO_MAX, "El vuelo")
        if notas is not None:
            datos["notas"] = _texto(notas, NOTAS_MAX, "Las notas")
        item.datos_servicio = datos  # una asignación nueva: JSONB no detecta cambios internos
        cambiados += 1
    if not cambiados:
        raise reservas.TransicionInvalida("Los viajes de esta reserva ya salieron")
    db.flush()
    return reserva

