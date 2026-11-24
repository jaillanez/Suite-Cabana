"""Precio de una excursión por tipo de pasajero (docs/05, etapa 2). Cuenta pura.

Cada prestador define sus tipos de pasajero con su precio: "Adulto", "Menor de 3
a 12", "Jubilado". La plataforma no decide edades ni quién paga qué; solo suma.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


class PrecioInvalido(ValueError):
    """El pedido no se puede cotizar: un tipo que no existe, nadie que viaje."""


@dataclass(frozen=True)
class Categoria:
    id: uuid.UUID
    nombre: str
    precio: Decimal
    ocupa_lugar: bool = True


@dataclass(frozen=True)
class Linea:
    categoria_id: uuid.UUID
    concepto: str
    cantidad: int
    precio_unitario: Decimal
    monto: Decimal


@dataclass(frozen=True)
class PrecioExcursion:
    lineas: list[Linea]
    subtotal: Decimal
    personas: int  # todos los que van
    lugares: int  # los que ocupan cupo

    def desglose(self) -> dict:
        return {
            "pasajeros": [
                {
                    "categoria_id": str(ln.categoria_id),
                    "concepto": ln.concepto,
                    "cantidad": ln.cantidad,
                    "precio_unitario": str(ln.precio_unitario),
                    "monto": str(ln.monto),
                }
                for ln in self.lineas
            ],
            "personas": self.personas,
            "lugares": self.lugares,
            "subtotal": str(self.subtotal),
        }


def _r(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular(
    categorias: list[Categoria], pedido: dict[uuid.UUID, int], maximo_por_reserva: int
) -> PrecioExcursion:
    """Suma cada tipo de pasajero por su precio. `pedido` es {categoría: cantidad}."""
    por_id = {c.id: c for c in categorias}
    if not por_id:
        raise PrecioInvalido("Esta excursión todavía no tiene precios")
    lineas: list[Linea] = []
    for cid, cantidad in pedido.items():
        if cantidad < 0:
            raise PrecioInvalido("La cantidad de pasajeros no puede ser negativa")
        if cantidad == 0:
            continue
        categoria = por_id.get(cid)
        if categoria is None:
            raise PrecioInvalido("Ese tipo de pasajero no existe en esta excursión")
        lineas.append(
            Linea(
                categoria_id=cid,
                concepto=categoria.nombre,
                cantidad=cantidad,
                precio_unitario=categoria.precio,
                monto=_r(categoria.precio * cantidad),
            )
        )
    personas = sum(ln.cantidad for ln in lineas)
    lugares = sum(ln.cantidad for ln in lineas if por_id[ln.categoria_id].ocupa_lugar)
    if lugares < 1:
        raise PrecioInvalido("Tiene que ir al menos una persona que ocupe lugar")
    if personas > maximo_por_reserva:
        raise PrecioInvalido(f"Se reservan hasta {maximo_por_reserva} personas por vez")
    # En el orden en que el prestador los cargó, no en el del pedido.
    orden = {c.id: n for n, c in enumerate(categorias)}
    lineas.sort(key=lambda ln: orden[ln.categoria_id])
    return PrecioExcursion(
        lineas=lineas,
        subtotal=_r(sum((ln.monto for ln in lineas), Decimal(0))),
        personas=personas,
        lugares=lugares,
    )
