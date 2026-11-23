"""Motor de precios de alojamiento (docs/01 §5 R3). Lógica pura, sin acceso a BD.

Calcula lo que cobra el prestador por una estadía. La comisión de la plataforma
se resuelve aparte, en `app.services.comisiones`, y se suma o descuenta según la
regla que gane. Este módulo nunca decide quién paga la comisión.

Reglas aplicadas, en orden:
1. Cada noche toma el precio de la tarifa vigente de mayor prioridad que la cubra.
   `precios_dia_semana` sobrescribe el precio de esa tarifa para ese día.
2. La tarifa de la primera noche gobierna estadía mínima, máxima y anticipación.
   Sin máximo propio rige el de la plataforma, y la llegada no puede estar a más
   de 12 meses (los dos topes, como Airbnb).
3. Persona extra se cobra por noche, sobre `capacidad_base`.
4. Mascota se cobra una vez por estadía.
5. El descuento por estadía larga se aplica solo sobre el alojamiento, nunca
   sobre limpieza ni extras: mensual desde 28 noches, semanal desde 7.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

CENTAVO = Decimal("0.01")
CIEN = Decimal(100)
NOCHES_SEMANA = 7
NOCHES_MES = 28
# Topes de la plataforma: el anfitrión puede achicarlos, no agrandarlos.
ESTADIA_MAXIMA = 365
VENTANA_DIAS = 365  # hasta cuánto adelante se reserva


def _r(v: Decimal | int | str) -> Decimal:
    """Redondea a centavos. Acepta enteros para no romperse ante un default de BD."""
    if not isinstance(v, Decimal):
        v = Decimal(str(v))
    return v.quantize(CENTAVO, rounding=ROUND_HALF_UP)


class MotivoNoDisponible(StrEnum):
    SIN_TARIFA = "sin_tarifa"
    ESTADIA_CORTA = "estadia_corta"
    ESTADIA_LARGA = "estadia_larga"
    ANTICIPACION_INSUFICIENTE = "anticipacion_insuficiente"
    CAPACIDAD_INSUFICIENTE = "capacidad_insuficiente"
    RANGO_INVALIDO = "rango_invalido"
    FUERA_DE_VENTANA = "fuera_de_ventana"


MENSAJES = {
    MotivoNoDisponible.SIN_TARIFA: "No hay tarifa cargada para alguna de esas noches",
    MotivoNoDisponible.ESTADIA_CORTA: "La estadía es más corta que el mínimo de la unidad",
    MotivoNoDisponible.ESTADIA_LARGA: "La estadía supera el máximo de la unidad",
    MotivoNoDisponible.ANTICIPACION_INSUFICIENTE: "La unidad exige reservar con más anticipación",
    MotivoNoDisponible.CAPACIDAD_INSUFICIENTE: "La unidad no entra esa cantidad de personas",
    MotivoNoDisponible.RANGO_INVALIDO: "La fecha de salida debe ser posterior a la de llegada",
    MotivoNoDisponible.FUERA_DE_VENTANA: "Se puede reservar hasta 12 meses antes",
}


class NoDisponible(Exception):
    """La unidad no se puede reservar con esos parámetros."""

    def __init__(self, motivo: MotivoNoDisponible):
        self.motivo = motivo
        super().__init__(MENSAJES[motivo])


@dataclass(frozen=True)
class Tarifa:
    """Copia plana de app.models.Tarifa; sin fechas significa 'tarifa base'."""

    precio_noche: Decimal
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    precios_dia_semana: dict[str, object] | None = None
    estadia_minima: int = 1
    estadia_maxima: int | None = None
    anticipacion_minima_dias: int = 0
    prioridad: int = 0

    def cubre(self, dia: date) -> bool:
        if self.fecha_desde and dia < self.fecha_desde:
            return False
        if self.fecha_hasta and dia > self.fecha_hasta:
            return False
        return True

    @property
    def es_temporada(self) -> bool:
        return self.fecha_desde is not None or self.fecha_hasta is not None

    def precio(self, dia: date) -> Decimal:
        if self.precios_dia_semana:
            valor = self.precios_dia_semana.get(str(dia.weekday()))
            if valor is not None:
                return Decimal(str(valor))
        return self.precio_noche


@dataclass(frozen=True)
class Unidad:
    """Copia plana de app.models.Unidad."""

    capacidad: int
    capacidad_base: int | None = None
    cargo_limpieza: Decimal = Decimal(0)
    cargo_persona_extra: Decimal = Decimal(0)
    cargo_mascota: Decimal = Decimal(0)
    descuento_semanal: Decimal = Decimal(0)
    descuento_mensual: Decimal = Decimal(0)


@dataclass(frozen=True)
class Noche:
    fecha: date
    precio: Decimal


@dataclass(frozen=True)
class Precio:
    """Lo que cobra el prestador. `subtotal` es la base de la comisión."""

    noches: list[Noche]
    alojamiento: Decimal
    descuento: Decimal
    limpieza: Decimal
    personas_extra: Decimal
    mascotas: Decimal
    subtotal: Decimal
    porcentaje_descuento: Decimal

    @property
    def cantidad_noches(self) -> int:
        return len(self.noches)

    @property
    def promedio_noche(self) -> Decimal:
        return _r(self.alojamiento / self.cantidad_noches)

    def desglose(self) -> dict[str, object]:
        """Guardable tal cual en ItemReserva.desglose (JSONB)."""
        return {
            "noches": [
                {"fecha": n.fecha.isoformat(), "precio": str(n.precio)} for n in self.noches
            ],
            "alojamiento": str(self.alojamiento),
            "descuento": str(self.descuento),
            "porcentaje_descuento": str(self.porcentaje_descuento),
            "limpieza": str(self.limpieza),
            "personas_extra": str(self.personas_extra),
            "mascotas": str(self.mascotas),
            "subtotal": str(self.subtotal),
        }


def tarifa_de_la_noche(tarifas: list[Tarifa], dia: date) -> Tarifa | None:
    """La de mayor prioridad que cubra la noche; a igual prioridad gana la de temporada."""
    candidatas = [t for t in tarifas if t.cubre(dia)]
    if not candidatas:
        return None
    return max(candidatas, key=lambda t: (t.prioridad, t.es_temporada))


def calcular(
    unidad: Unidad,
    tarifas: list[Tarifa],
    fecha_inicio: date,
    fecha_fin: date,
    personas: int = 1,
    mascotas: int = 0,
    hoy: date | None = None,
    ventana_dias: int = VENTANA_DIAS,
) -> Precio:
    """Precio del prestador para la estadía. Lanza NoDisponible si no se puede reservar.

    `ventana_dias` se agranda solo para las cabañas de un paquete con salón, que
    acompañan a un evento reservable con más anticipación.
    """
    if fecha_fin <= fecha_inicio:
        raise NoDisponible(MotivoNoDisponible.RANGO_INVALIDO)
    if personas > unidad.capacidad:
        raise NoDisponible(MotivoNoDisponible.CAPACIDAD_INSUFICIENTE)
    referencia = hoy or date.today()
    if (fecha_inicio - referencia).days > ventana_dias:
        raise NoDisponible(MotivoNoDisponible.FUERA_DE_VENTANA)

    cantidad = (fecha_fin - fecha_inicio).days
    # Antes de recorrer las noches: un rango de años no se calcula para rechazarlo.
    if cantidad > ESTADIA_MAXIMA:
        raise NoDisponible(MotivoNoDisponible.ESTADIA_LARGA)
    dias = [fecha_inicio + timedelta(days=i) for i in range(cantidad)]

    noches: list[Noche] = []
    for dia in dias:
        tarifa = tarifa_de_la_noche(tarifas, dia)
        if tarifa is None:
            raise NoDisponible(MotivoNoDisponible.SIN_TARIFA)
        noches.append(Noche(fecha=dia, precio=_r(tarifa.precio(dia))))

    gobierna = tarifa_de_la_noche(tarifas, fecha_inicio)
    assert gobierna is not None  # garantizado por el bucle anterior
    if cantidad < gobierna.estadia_minima:
        raise NoDisponible(MotivoNoDisponible.ESTADIA_CORTA)
    if gobierna.estadia_maxima is not None and cantidad > gobierna.estadia_maxima:
        raise NoDisponible(MotivoNoDisponible.ESTADIA_LARGA)
    if gobierna.anticipacion_minima_dias:
        if (fecha_inicio - referencia).days < gobierna.anticipacion_minima_dias:
            raise NoDisponible(MotivoNoDisponible.ANTICIPACION_INSUFICIENTE)

    alojamiento = _r(sum((n.precio for n in noches), Decimal(0)))

    if cantidad >= NOCHES_MES:
        porcentaje = unidad.descuento_mensual
    elif cantidad >= NOCHES_SEMANA:
        porcentaje = unidad.descuento_semanal
    else:
        porcentaje = Decimal(0)
    descuento = _r(alojamiento * porcentaje / CIEN)

    base_personas = unidad.capacidad_base
    if base_personas is not None and personas > base_personas:
        personas_extra = _r(
            unidad.cargo_persona_extra * (personas - base_personas) * cantidad
        )
    else:
        personas_extra = Decimal("0.00")

    limpieza = _r(unidad.cargo_limpieza)
    cargo_mascotas = _r(unidad.cargo_mascota * mascotas)
    subtotal = alojamiento - descuento + limpieza + personas_extra + cargo_mascotas

    return Precio(
        noches=noches,
        alojamiento=alojamiento,
        descuento=descuento,
        limpieza=limpieza,
        personas_extra=personas_extra,
        mascotas=cargo_mascotas,
        subtotal=_r(subtotal),
        porcentaje_descuento=porcentaje,
    )
