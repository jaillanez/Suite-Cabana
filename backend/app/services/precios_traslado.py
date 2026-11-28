"""Precio de un traslado y cuánto queda ocupado el vehículo (docs/06). Cuenta pura.

Dos formas de cobrar, que elige cada prestador por vehículo:

- **Tramo fijo**: un precio por el vehículo o por persona, con su duración.
- **Por kilómetro**: bajada + precio por km, con un mínimo. La distancia es la
  línea recta por el factor de ruta del prestador: sin proveedor de rutas, es lo
  más honesto que se puede calcular, y el prestador ajusta el factor a su zona.

A cualquiera de las dos se le suma el recargo nocturno, si la salida cae en su
horario. El vehículo queda ocupado el viaje, la vuelta a la base (si el
prestador lo indica) y la preparación.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.services.precios_eventos import ZONA

RADIO_TIERRA_KM = 6371.0
VENTANA_DIAS = 365
DURACION_MINIMA = timedelta(minutes=15)
#: Lo más que un viaje puede tener tomado el vehículo (viaje, vuelta y
#: preparación). `horarios` usa el mismo tope: lo que se cotiza, se puede reservar.
OCUPACION_MAXIMA = timedelta(hours=120)


class TrasladoInvalido(ValueError):
    """No se puede cotizar: no entran, queda fuera de zona, es muy pronto."""


@dataclass(frozen=True)
class Punto:
    lat: float
    lon: float


@dataclass(frozen=True)
class Vehiculo:
    pasajeros: int
    valijas: int | None = None  # None: sin límite
    preparacion_minutos: int = 0


@dataclass(frozen=True)
class Reglas:
    """Las reglas del vehículo que elige el prestador (`tarifa_traslado`)."""

    precio_km: Decimal | None = None
    bajada: Decimal = Decimal(0)
    minimo: Decimal = Decimal(0)
    radio_km: int | None = None
    factor_ruta: Decimal = Decimal("1.3")
    velocidad_kmh: int = 60
    recargo_nocturno_desde: time | None = None
    recargo_nocturno_hasta: time | None = None
    recargo_nocturno_porcentaje: Decimal = Decimal(0)
    vuelve_a_base: bool = True
    anticipacion_minima_horas: int = 12


@dataclass(frozen=True)
class Tramo:
    precio: Decimal
    duracion_minutos: int
    por_persona: bool = False


@dataclass(frozen=True)
class Linea:
    concepto: str
    monto: Decimal


@dataclass(frozen=True)
class PrecioTraslado:
    inicio: datetime
    llegada: datetime
    #: Hasta cuándo queda tomado el vehículo: llegada + vuelta + preparación.
    ocupado_hasta: datetime
    km: Decimal | None
    lineas: list[Linea] = field(default_factory=list)
    subtotal: Decimal = Decimal(0)

    def desglose(self) -> dict:
        return {
            "lineas": [{"concepto": ln.concepto, "monto": str(ln.monto)} for ln in self.lineas],
            "km": str(self.km) if self.km is not None else None,
            "llegada": self.llegada.isoformat(),
            "subtotal": str(self.subtotal),
        }


def _r(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def distancia_km(a: Punto, b: Punto) -> float:
    """Distancia en línea recta (haversine), en km."""
    la1, lo1, la2, lo2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(
        (lo2 - lo1) / 2
    ) ** 2
    return 2 * RADIO_TIERRA_KM * math.asin(math.sqrt(h))


def es_nocturno(inicio: datetime, reglas: Reglas) -> bool:
    """Si la salida cae en el horario de recargo (que puede cruzar la medianoche)."""
    desde, hasta = reglas.recargo_nocturno_desde, reglas.recargo_nocturno_hasta
    if not desde or not hasta or reglas.recargo_nocturno_porcentaje <= 0:
        return False
    hora = inicio.astimezone(ZONA).time()
    if desde < hasta:
        return desde <= hora < hasta
    return hora >= desde or hora < hasta  # de 22 a 6


def _validar(
    vehiculo: Vehiculo, reglas: Reglas, pasajeros: int, valijas: int,
    inicio: datetime, ahora: datetime,
) -> None:
    if inicio.tzinfo is None:
        raise TrasladoInvalido("La hora tiene que venir con zona horaria")
    if pasajeros < 1:
        raise TrasladoInvalido("Tiene que viajar al menos una persona")
    if pasajeros > vehiculo.pasajeros:
        raise TrasladoInvalido(f"En este vehículo entran hasta {vehiculo.pasajeros} pasajeros")
    if valijas < 0:
        raise TrasladoInvalido("La cantidad de valijas no puede ser negativa")
    if vehiculo.valijas is not None and valijas > vehiculo.valijas:
        raise TrasladoInvalido(f"En este vehículo entran hasta {vehiculo.valijas} valijas")
    if inicio < ahora + timedelta(hours=reglas.anticipacion_minima_horas):
        raise TrasladoInvalido(
            f"Se reserva con al menos {reglas.anticipacion_minima_horas} h de anticipación"
        )
    if inicio > ahora + timedelta(days=VENTANA_DIAS):
        raise TrasladoInvalido("Se puede reservar hasta 12 meses antes")


def _armar(
    base: Decimal, concepto: str, duracion: timedelta, inicio: datetime,
    vehiculo: Vehiculo, reglas: Reglas, km: Decimal | None,
) -> PrecioTraslado:
    lineas = [Linea(concepto, _r(base))]
    if es_nocturno(inicio, reglas):
        lineas.append(
            Linea(
                f"Recargo nocturno ({reglas.recargo_nocturno_porcentaje.normalize():f} %)",
                _r(base * reglas.recargo_nocturno_porcentaje / 100),
            )
        )
    llegada = inicio + duracion
    vuelta = duracion if reglas.vuelve_a_base else timedelta(0)
    ocupado_hasta = llegada + vuelta + timedelta(minutes=vehiculo.preparacion_minutos)
    if ocupado_hasta - inicio > OCUPACION_MAXIMA:
        raise TrasladoInvalido("Ese viaje es demasiado largo para este vehículo")
    return PrecioTraslado(
        inicio=inicio,
        llegada=llegada,
        ocupado_hasta=ocupado_hasta,
        km=km,
        lineas=lineas,
        subtotal=_r(sum((ln.monto for ln in lineas), Decimal(0))),
    )


def por_tramo(
    tramo: Tramo, vehiculo: Vehiculo, reglas: Reglas, inicio: datetime, ahora: datetime,
    pasajeros: int, valijas: int = 0,
) -> PrecioTraslado:
    _validar(vehiculo, reglas, pasajeros, valijas, inicio, ahora)
    if tramo.por_persona:
        base = tramo.precio * pasajeros
        # El monto va en su columna: acá solo cuántos pagan (sin "8000.00" sin formato).
        concepto = f"Traslado por persona, {pasajeros} pasajero{'s' if pasajeros != 1 else ''}"
    else:
        base, concepto = tramo.precio, "Traslado"
    return _armar(
        base, concepto, timedelta(minutes=tramo.duracion_minutos), inicio, vehiculo, reglas,
        None,
    )


def por_km(
    origen: Punto, destino: Punto, base_vehiculo: Punto | None, vehiculo: Vehiculo,
    reglas: Reglas, inicio: datetime, ahora: datetime, pasajeros: int, valijas: int = 0,
    margen_km: float = 0.0,
) -> PrecioTraslado:
    """`margen_km`: cuánto puede estar corrida la base que se recibe (redondeada,
    ver `traslados.base_de`). Se descuenta del radio para que el que se aplica
    nunca sea más grande que el que eligió el prestador."""
    if reglas.precio_km is None:
        raise TrasladoInvalido("Este vehículo no cobra por kilómetro")
    _validar(vehiculo, reglas, pasajeros, valijas, inicio, ahora)
    if reglas.radio_km is not None and base_vehiculo is not None:
        for p in (origen, destino):
            if distancia_km(base_vehiculo, p) > reglas.radio_km - margen_km:
                raise TrasladoInvalido(
                    f"Este vehículo va hasta {reglas.radio_km} km de su base"
                )
    recta = Decimal(str(distancia_km(origen, destino)))
    km = (recta * reglas.factor_ruta).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if km < Decimal("0.5"):
        raise TrasladoInvalido("El origen y el destino son el mismo lugar")
    base = max(reglas.minimo, reglas.bajada + km * reglas.precio_km)
    # Duración estimada a la velocidad media, redondeada a 5 minutos hacia arriba.
    minutos = math.ceil(float(km) / reglas.velocidad_kmh * 60 / 5) * 5
    duracion = max(timedelta(minutes=minutos), DURACION_MINIMA)
    # "14,6 km": el concepto lo lee el viajero, con coma decimal.
    concepto = f"Traslado, {str(km).replace('.', ',')} km"
    return _armar(base, concepto, duracion, inicio, vehiculo, reglas, km)
