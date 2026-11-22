"""Motor de precios de salones de eventos (docs/04 §4 y §5). Lógica pura, sin BD.

Es el equivalente de `precios.py` para lo que se alquila por horario. Calcula lo
que cobra el prestador; la comisión se resuelve aparte, en `comisiones`.

Un evento tiene un **día del evento** (el que figura en la reserva) y un rango
exacto [inicio, fin) que puede terminar pasada la medianoche. El precio por día
de la semana se toma siempre del día del evento: una fiesta del sábado que
termina el domingo a las 5 es una fiesta del sábado.

Reglas, en orden:
1. Franja fija: su precio (o el de ese día de la semana).
2. Por horas: precio por hora (o el de ese día de la semana) × horas, con un
   mínimo de horas, dentro del horario de atención. Cada hora que empieza desde
   `recargo_nocturno_desde` suma el recargo nocturno.
3. Persona extra: una vez por evento, por cada invitado sobre `capacidad_base`.
4. Adicionales: por evento, o por invitado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

CENTAVO = Decimal("0.01")
CIEN = Decimal(100)
ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
UNA_HORA = timedelta(hours=1)
HORAS_MAXIMAS = 24


def _r(v: Decimal | int | str) -> Decimal:
    return Decimal(v).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def precio_del_dia(base: Decimal, por_dia: dict | None, dia: date) -> Decimal:
    if por_dia:
        valor = por_dia.get(str(dia.weekday()))
        if valor is not None:
            return Decimal(str(valor))
    return base


def en_hora(dia: date, hora: time) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora.hour, hora.minute, tzinfo=ZONA)


def _ventana(dia: date, desde: time, hasta: time) -> tuple[datetime, datetime]:
    """[desde, hasta) del día; si `hasta` no es posterior, termina al día siguiente."""
    inicio = en_hora(dia, desde)
    fin = en_hora(dia, hasta)
    if fin <= inicio:
        fin += timedelta(days=1)
    return inicio, fin


class EventoNoDisponible(ValueError):
    """El pedido no se puede cotizar, con el motivo en el mensaje."""


@dataclass(frozen=True)
class Salon:
    """Copia plana de lo que importa de la unidad."""

    capacidad: int
    capacidad_base: int | None = None
    cargo_persona_extra: Decimal = Decimal(0)
    preparacion_minutos: int = 0


@dataclass(frozen=True)
class Franja:
    id: str
    nombre: str
    hora_inicio: time
    hora_fin: time
    precio: Decimal
    precios_dia_semana: dict | None = None

    def rango(self, dia: date) -> tuple[datetime, datetime]:
        return _ventana(dia, self.hora_inicio, self.hora_fin)


@dataclass(frozen=True)
class TarifaHoras:
    precio_hora: Decimal
    hora_apertura: time
    hora_cierre: time
    horas_minimas: int = 1
    precios_dia_semana: dict | None = None
    recargo_nocturno_desde: time | None = None
    recargo_nocturno_porcentaje: Decimal = Decimal(0)

    def atencion(self, dia: date) -> tuple[datetime, datetime]:
        return _ventana(dia, self.hora_apertura, self.hora_cierre)


@dataclass(frozen=True)
class Adicional:
    id: str
    nombre: str
    precio: Decimal
    por_persona: bool = False


@dataclass(frozen=True)
class Linea:
    concepto: str
    monto: Decimal


@dataclass(frozen=True)
class PrecioEvento:
    dia: date
    inicio: datetime
    fin: datetime
    invitados: int
    alquiler: Decimal
    lineas: list[Linea] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        return _r(self.alquiler + sum((ln.monto for ln in self.lineas), Decimal(0)))

    @property
    def horas(self) -> Decimal:
        return Decimal((self.fin - self.inicio).total_seconds()) / 3600

    def desglose(self) -> dict:
        return {
            "modo": "horario",
            "dia": self.dia.isoformat(),
            "inicio": self.inicio.isoformat(),
            "fin": self.fin.isoformat(),
            "horas": str(self.horas.normalize()),
            "invitados": self.invitados,
            "alquiler": str(self.alquiler),
            "lineas": [{"concepto": ln.concepto, "monto": str(ln.monto)} for ln in self.lineas],
            "subtotal": str(self.subtotal),
        }


def _extras(
    salon: Salon, invitados: int, adicionales: list[Adicional]
) -> list[Linea]:
    if invitados < 1:
        raise EventoNoDisponible("Indicá cuántos invitados van a ser")
    if invitados > salon.capacidad:
        raise EventoNoDisponible(f"El lugar admite hasta {salon.capacidad} personas")
    lineas: list[Linea] = []
    base = salon.capacidad_base
    if base and invitados > base and salon.cargo_persona_extra > 0:
        extra = invitados - base
        lineas.append(
            Linea(f"{extra} invitados sobre {base}", _r(salon.cargo_persona_extra * extra))
        )
    for a in adicionales:
        if a.por_persona:
            lineas.append(Linea(f"{a.nombre} ({invitados} personas)", _r(a.precio * invitados)))
        else:
            lineas.append(Linea(a.nombre, _r(a.precio)))
    return lineas


def por_franja(
    salon: Salon, franja: Franja, dia: date, invitados: int, adicionales: list[Adicional]
) -> PrecioEvento:
    inicio, fin = franja.rango(dia)
    alquiler = _r(precio_del_dia(franja.precio, franja.precios_dia_semana, dia))
    return PrecioEvento(
        dia=dia,
        inicio=inicio,
        fin=fin,
        invitados=invitados,
        alquiler=alquiler,
        lineas=_extras(salon, invitados, adicionales),
    )


def inicio_en_el_dia(tarifa: TarifaHoras, dia: date, hora: time) -> datetime:
    """La hora pedida dentro del horario de atención del día del evento.

    Si el salón atiende de 10 a 2 h, "1:00" del sábado es la 1 del domingo.
    """
    apertura, cierre = tarifa.atencion(dia)
    candidato = en_hora(dia, hora)
    if candidato < apertura:
        candidato += timedelta(days=1)
    if not (apertura <= candidato < cierre):
        raise EventoNoDisponible("Ese horario está fuera del horario de atención")
    return candidato


def por_horas(
    salon: Salon,
    tarifa: TarifaHoras,
    dia: date,
    hora_inicio: time,
    horas: int,
    invitados: int,
    adicionales: list[Adicional],
) -> PrecioEvento:
    if horas < tarifa.horas_minimas:
        raise EventoNoDisponible(f"El mínimo es de {tarifa.horas_minimas} horas")
    if horas > HORAS_MAXIMAS:
        raise EventoNoDisponible("Para más de 24 horas, consultá al anfitrión")
    if hora_inicio.minute not in (0, 30) or hora_inicio.second:
        raise EventoNoDisponible("El inicio tiene que ser en punto o y media")

    inicio = inicio_en_el_dia(tarifa, dia, hora_inicio)
    fin = inicio + horas * UNA_HORA
    _, cierre = tarifa.atencion(dia)
    if fin > cierre:
        raise EventoNoDisponible(
            f"El salón cierra a las {tarifa.hora_cierre.strftime('%H:%M')}"
        )

    precio_hora = precio_del_dia(tarifa.precio_hora, tarifa.precios_dia_semana, dia)
    alquiler = _r(precio_hora * horas)

    lineas: list[Linea] = []
    if tarifa.recargo_nocturno_desde and tarifa.recargo_nocturno_porcentaje > 0:
        # El recargo arranca a esa hora del día del evento (o de la madrugada
        # siguiente, si la hora es anterior a la apertura).
        desde = en_hora(dia, tarifa.recargo_nocturno_desde)
        if desde < tarifa.atencion(dia)[0]:
            desde += timedelta(days=1)
        nocturnas = sum(1 for h in range(horas) if inicio + h * UNA_HORA >= desde)
        if nocturnas:
            recargo = _r(precio_hora * nocturnas * tarifa.recargo_nocturno_porcentaje / CIEN)
            lineas.append(
                Linea(
                    f"Recargo nocturno ({nocturnas} h, "
                    f"{tarifa.recargo_nocturno_porcentaje.normalize()} %)",
                    recargo,
                )
            )

    return PrecioEvento(
        dia=dia,
        inicio=inicio,
        fin=fin,
        invitados=invitados,
        alquiler=alquiler,
        lineas=lineas + _extras(salon, invitados, adicionales),
    )


def rango_ocupado(precio: PrecioEvento, salon: Salon) -> tuple[datetime, datetime]:
    """Lo que hay que bloquear: el evento más el tiempo de preparación posterior.

    Con la preparación pegada al final de cada evento alcanza para los dos lados:
    uno nuevo que termina justo antes de otro choca con la preparación del nuevo.
    """
    return precio.inicio, precio.fin + timedelta(minutes=salon.preparacion_minutos)
