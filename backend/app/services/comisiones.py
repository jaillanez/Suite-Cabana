"""Motor de comisiones (docs/00 §7). Lógica pura, sin acceso a BD.

Resolución:
1. Reglas activas, vigentes y que coinciden con el contexto.
2. Gana la más específica (más dimensiones definidas).
3. Empate: mayor prioridad. 4. Empate: la más reciente.
5. La regla por defecto (sin dimensiones) garantiza un resultado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from app.models.enums import QuienPaga

CENTAVO = Decimal("0.01")
CIEN = Decimal(100)


def _r(v: Decimal) -> Decimal:
    return v.quantize(CENTAVO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ContextoComision:
    monto: Decimal  # subtotal del prestador (base de cálculo)
    fecha_servicio: date  # inicio de estadía o servicio
    fecha_creacion: date
    tipo_servicio_id: UUID | None = None
    subtipo_servicio_id: UUID | None = None
    provincia_id: UUID | None = None
    localidad_id: UUID | None = None
    zona_id: UUID | None = None
    prestador_id: UUID | None = None
    publicacion_id: UUID | None = None
    antiguedad_prestador_meses: int | None = None
    categoria_prestador: str | None = None


@dataclass(frozen=True)
class Regla:
    id: UUID
    nombre: str
    creada_en: datetime
    activa: bool = True
    prioridad: int = 0
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    # dimensiones exactas
    tipo_servicio_id: UUID | None = None
    subtipo_servicio_id: UUID | None = None
    provincia_id: UUID | None = None
    localidad_id: UUID | None = None
    zona_id: UUID | None = None
    prestador_id: UUID | None = None
    publicacion_id: UUID | None = None
    categoria_prestador: str | None = None
    # dimensiones de rango (inclusivas)
    servicio_desde: date | None = None
    servicio_hasta: date | None = None
    creacion_desde: date | None = None
    creacion_hasta: date | None = None
    monto_desde: Decimal | None = None
    monto_hasta: Decimal | None = None
    antiguedad_meses_desde: int | None = None
    antiguedad_meses_hasta: int | None = None
    # valor
    porcentaje: Decimal = Decimal(0)
    monto_fijo: Decimal = Decimal(0)
    minimo: Decimal | None = None
    maximo: Decimal | None = None
    quien_paga: QuienPaga = QuienPaga.PRESTADOR
    porcentaje_viajero: Decimal = Decimal(0)
    iva_incluido: bool = False

    EXACTAS = (
        "tipo_servicio_id",
        "subtipo_servicio_id",
        "provincia_id",
        "localidad_id",
        "zona_id",
        "prestador_id",
        "publicacion_id",
        "categoria_prestador",
    )
    RANGOS = (
        ("servicio_desde", "servicio_hasta", "fecha_servicio"),
        ("creacion_desde", "creacion_hasta", "fecha_creacion"),
        ("monto_desde", "monto_hasta", "monto"),
        ("antiguedad_meses_desde", "antiguedad_meses_hasta", "antiguedad_prestador_meses"),
    )

    #: Lo que una dimensión ya define por sí sola: una cabalgata es una excursión,
    #: una localidad está en una provincia y una publicación lo dice todo. Sin esto,
    #: "Cabalgatas" y "Excursiones" valdrían lo mismo y ganaría la última creada.
    IMPLICA = {
        "subtipo_servicio_id": ("tipo_servicio_id",),
        "localidad_id": ("provincia_id",),
        "zona_id": ("localidad_id", "provincia_id"),
        "publicacion_id": (
            "prestador_id", "tipo_servicio_id", "subtipo_servicio_id",
            "provincia_id", "localidad_id", "zona_id",
        ),
    }

    @property
    def especificidad(self) -> int:
        definidas = {d for d in self.EXACTAS if getattr(self, d) is not None}
        for d in list(definidas):
            definidas.update(self.IMPLICA.get(d, ()))
        n = len(definidas)
        n += sum(
            getattr(self, a) is not None or getattr(self, b) is not None for a, b, _ in self.RANGOS
        )
        return n

    @property
    def es_default(self) -> bool:
        return self.especificidad == 0

    def motivo_descarte(self, ctx: ContextoComision) -> str | None:
        """None si la regla aplica; si no, el motivo."""
        if not self.activa:
            return "inactiva"
        if self.vigente_desde and ctx.fecha_creacion < self.vigente_desde:
            return "todavía no vigente"
        if self.vigente_hasta and ctx.fecha_creacion > self.vigente_hasta:
            return "vigencia vencida"
        for d in self.EXACTAS:
            valor = getattr(self, d)
            if valor is not None and valor != getattr(ctx, d):
                return f"no coincide {d}"
        for desde, hasta, campo in self.RANGOS:
            lo, hi = getattr(self, desde), getattr(self, hasta)
            if lo is None and hi is None:
                continue
            v = getattr(ctx, campo)
            if v is None or (lo is not None and v < lo) or (hi is not None and v > hi):
                return f"fuera de rango {campo}"
        return None

    def a_dict(self) -> dict[str, Any]:
        out = {}
        for k in self.__dataclass_fields__:
            v = getattr(self, k)
            out[k] = str(v) if isinstance(v, (UUID, Decimal, date, datetime)) else v
        return out


@dataclass(frozen=True)
class ResultadoComision:
    regla: Regla
    base: Decimal
    comision_neta: Decimal
    iva: Decimal
    comision_total: Decimal
    cargo_viajero: Decimal  # se suma a lo que paga el viajero
    descuento_prestador: Decimal  # se descuenta del cobro del prestador
    explicacion: list[str] = field(default_factory=list)

    @property
    def total_viajero(self) -> Decimal:
        return self.base + self.cargo_viajero

    @property
    def neto_prestador(self) -> Decimal:
        return self.base - self.descuento_prestador


class SinReglaAplicable(Exception):
    """No hay regla por defecto activa. Nunca debería ocurrir en producción."""


def elegir_regla(reglas: list[Regla], ctx: ContextoComision) -> tuple[Regla, list[str]]:
    explicacion: list[str] = []
    candidatas: list[Regla] = []
    for r in reglas:
        motivo = r.motivo_descarte(ctx)
        if motivo:
            explicacion.append(f"✗ {r.nombre}: {motivo}")
        else:
            candidatas.append(r)
            explicacion.append(
                f"✓ {r.nombre}: coincide (especificidad {r.especificidad}, prioridad {r.prioridad})"
            )
    if not candidatas:
        raise SinReglaAplicable("No existe una regla por defecto activa")
    ganadora = max(candidatas, key=lambda r: (r.especificidad, r.prioridad, r.creada_en))
    explicacion.append(f"→ Aplica: {ganadora.nombre}")
    return ganadora, explicacion


def calcular(regla: Regla, base: Decimal, alicuota_iva: Decimal) -> tuple[Decimal, ...]:
    bruto = base * regla.porcentaje / CIEN + regla.monto_fijo
    if regla.minimo is not None:
        bruto = max(bruto, regla.minimo)
    if regla.maximo is not None:
        bruto = min(bruto, regla.maximo)

    if regla.iva_incluido:
        total = _r(bruto)
        neta = _r(total / (1 + alicuota_iva))
        iva = total - neta
    else:
        neta = _r(bruto)
        iva = _r(neta * alicuota_iva)
        total = neta + iva

    match regla.quien_paga:
        case QuienPaga.PRESTADOR:
            pct_viajero = Decimal(0)
        case QuienPaga.VIAJERO:
            pct_viajero = CIEN
        case QuienPaga.DIVIDIDO:
            pct_viajero = regla.porcentaje_viajero
    cargo_viajero = _r(total * pct_viajero / CIEN)
    descuento_prestador = total - cargo_viajero
    return neta, iva, total, cargo_viajero, descuento_prestador


def resolver(
    reglas: list[Regla], ctx: ContextoComision, alicuota_iva: Decimal
) -> ResultadoComision:
    regla, explicacion = elegir_regla(reglas, ctx)
    neta, iva, total, cargo_v, desc_p = calcular(regla, ctx.monto, alicuota_iva)
    return ResultadoComision(
        regla=regla,
        base=ctx.monto,
        comision_neta=neta,
        iva=iva,
        comision_total=total,
        cargo_viajero=cargo_v,
        descuento_prestador=desc_p,
        explicacion=explicacion,
    )


def regla_desde_modelo(m) -> Regla:
    """Convierte un app.models.ReglaComision en Regla."""
    campos = {k for k in Regla.__dataclass_fields__ if k not in ("creada_en",)}
    return Regla(creada_en=m.creado_en, **{k: getattr(m, k) for k in campos})
