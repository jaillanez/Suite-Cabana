"""Traslados con la base de datos (docs/06, etapa 1): de un vehículo y un pedido,
la cotización y si el vehículo está libre.

La cuenta la hace `precios_traslado`; acá se buscan el tramo (en cualquiera de
los dos sentidos si el prestador lo permite), las reglas del vehículo y los
puntos. Que dos viajes no se pisen lo garantiza la restricción de exclusión de
`bloqueo_horario`, como en los salones.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import LugarTraslado, Publicacion, TarifaTraslado, TramoTraslado, Unidad
from app.models.enums import ModoReserva, OrigenBloqueo
from app.services import horarios
from app.services import precios_traslado as pt
from app.services.busqueda import lat_lon
from app.services.privacidad import aproximar

#: Lo más que se corre un punto al redondearlo a dos decimales: medio centésimo de
#: grado en cada eje (~0,56 km), en diagonal.
ERROR_REDONDEO_KM = 0.8


class NoDisponible(Exception):
    """El vehículo ya tiene un viaje (o un bloqueo) en ese horario."""


def _exigir_traslado(unidad: Unidad) -> None:
    if unidad.publicacion.tipo_servicio.modo_reserva is not ModoReserva.TRAMO:
        raise pt.TrasladoInvalido("Esta unidad no es un vehículo de traslados")


def vehiculo(unidad: Unidad) -> pt.Vehiculo:
    return pt.Vehiculo(
        pasajeros=unidad.capacidad,
        valijas=unidad.equipaje,
        preparacion_minutos=unidad.preparacion_minutos or 0,
    )


def reglas(db: Session, unidad: Unidad) -> pt.Reglas:
    t = db.scalar(select(TarifaTraslado).where(TarifaTraslado.unidad_id == unidad.id))
    if t is None:
        return pt.Reglas()
    return pt.Reglas(
        precio_km=t.precio_km,
        bajada=t.bajada,
        minimo=t.minimo,
        radio_km=t.radio_km,
        factor_ruta=t.factor_ruta,
        velocidad_kmh=t.velocidad_kmh,
        recargo_nocturno_desde=t.recargo_nocturno_desde,
        recargo_nocturno_hasta=t.recargo_nocturno_hasta,
        recargo_nocturno_porcentaje=t.recargo_nocturno_porcentaje,
        vuelve_a_base=t.vuelve_a_base,
        anticipacion_minima_horas=t.anticipacion_minima_horas,
    )


def punto(db: Session, lugar: LugarTraslado) -> pt.Punto:
    lat, lon = db.execute(
        select(*lat_lon(LugarTraslado.ubicacion)).where(LugarTraslado.id == lugar.id)
    ).one()
    return pt.Punto(lat=lat, lon=lon)


def base_de(db: Session, unidad: Unidad) -> pt.Punto | None:
    """De dónde sale el vehículo: el lugar marcado como base, o la publicación.

    Redondeado como el punto público (~1 km): el radio se mide desde acá, y con el
    punto exacto, probar direcciones hasta dar con el borde del radio revelaría
    dónde está la base, que puede ser la casa del prestador.
    """
    base = db.scalar(
        select(LugarTraslado).where(
            LugarTraslado.publicacion_id == unidad.publicacion_id,
            LugarTraslado.es_base.is_(True),
            LugarTraslado.activo.is_(True),
        )
    )
    if base is not None:
        p = punto(db, base)
        return pt.Punto(lat=aproximar(p.lat), lon=aproximar(p.lon))
    fila = db.execute(
        select(*lat_lon(Publicacion.ubicacion)).where(
            Publicacion.id == unidad.publicacion_id, Publicacion.ubicacion.is_not(None)
        )
    ).first()
    return pt.Punto(lat=aproximar(fila[0]), lon=aproximar(fila[1])) if fila else None


def tramo_entre(
    db: Session, unidad: Unidad, origen_id: uuid.UUID, destino_id: uuid.UUID
) -> TramoTraslado | None:
    """El tramo de ese vehículo de origen a destino; si no hay, el inverso cuando el
    prestador lo cargó para los dos sentidos."""
    candidatos = db.scalars(
        select(TramoTraslado).where(
            TramoTraslado.unidad_id == unidad.id,
            TramoTraslado.activo.is_(True),
            or_(
                (TramoTraslado.origen_id == origen_id) & (TramoTraslado.destino_id == destino_id),
                (TramoTraslado.origen_id == destino_id)
                & (TramoTraslado.destino_id == origen_id)
                & TramoTraslado.ambos_sentidos.is_(True),
            ),
        )
    ).all()
    # El del sentido pedido gana sobre el inverso.
    return next((t for t in candidatos if t.origen_id == origen_id), None) or next(
        iter(candidatos), None
    )


def cotizar_tramo(
    db: Session, unidad: Unidad, origen_id: uuid.UUID, destino_id: uuid.UUID,
    inicio: datetime, pasajeros: int, valijas: int = 0, ahora: datetime | None = None,
) -> pt.PrecioTraslado:
    _exigir_traslado(unidad)
    tramo = tramo_entre(db, unidad, origen_id, destino_id)
    if tramo is None:
        raise pt.TrasladoInvalido("Este vehículo no hace ese recorrido")
    return pt.por_tramo(
        pt.Tramo(tramo.precio, tramo.duracion_minutos, tramo.por_persona),
        vehiculo(unidad), reglas(db, unidad), inicio, ahora or datetime.now(UTC),
        pasajeros, valijas,
    )


def cotizar_km(
    db: Session, unidad: Unidad, origen: pt.Punto, destino: pt.Punto,
    inicio: datetime, pasajeros: int, valijas: int = 0, ahora: datetime | None = None,
) -> pt.PrecioTraslado:
    _exigir_traslado(unidad)
    return pt.por_km(
        origen, destino, base_de(db, unidad), vehiculo(unidad), reglas(db, unidad),
        inicio, ahora or datetime.now(UTC), pasajeros, valijas,
        margen_km=ERROR_REDONDEO_KM,
    )


def libre(db: Session, unidad: Unidad, precio: pt.PrecioTraslado) -> bool:
    """Si el vehículo está libre todo el tiempo que lo ocupa ese viaje."""
    return horarios.libre(db, unidad.id, precio.inicio, precio.ocupado_hasta)


def ocupar(
    db: Session, unidad: Unidad, precio: pt.PrecioTraslado, origen: OrigenBloqueo, **kw
):
    """Toma el vehículo por el viaje, la vuelta y la preparación. Levanta NoDisponible."""
    try:
        return horarios.bloquear(db, unidad, precio.inicio, precio.ocupado_hasta, origen, **kw)
    except horarios.HorarioOcupado as e:
        raise NoDisponible("El vehículo ya tiene un viaje en ese horario") from e
    except horarios.HorarioInvalido as e:
        raise pt.TrasladoInvalido(str(e)) from e
