"""Contrato común de las pasarelas de pago (docs/00 §8, docs/01 §5 R6).

El producto no se ata a una billetera. `docs/00 §8` deja abierto evaluar otras
pasarelas locales, así que el resto del sistema habla con esta interfaz y nunca
con Mercado Pago directamente: agregar una billetera es escribir un adaptador y
registrarlo, sin tocar reservas, comisiones ni pantallas.

Lo que toda pasarela tiene que poder hacer:

1. Armar un cobro y devolver a dónde mandar al viajero.
2. Decir si una notificación entrante es auténtica.
3. Traducir esa notificación a un estado que el sistema entienda.
4. Reintegrar, total o parcialmente.

Las credenciales son configuración: sin ellas la pasarela existe pero no está
disponible, y se dice por qué.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class EstadoPago(StrEnum):
    """Estados normalizados. Cada pasarela traduce los suyos a estos."""

    PENDIENTE = "pendiente"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    DEVUELTO = "devuelto"
    CANCELADO = "cancelado"
    EN_DISPUTA = "en_disputa"


@dataclass(frozen=True)
class Cobro:
    """Lo que hay que cobrar. Todo en Decimal: nunca float (CLAUDE.md)."""

    codigo_reserva: str
    descripcion: str
    total: Decimal
    comision_plataforma: Decimal
    moneda: str = "ARS"
    email_pagador: str | None = None
    cuenta_prestador: str | None = None
    url_exito: str | None = None
    url_fallo: str | None = None
    url_pendiente: str | None = None
    metadatos: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Preferencia:
    """Dónde mandar al viajero para que pague."""

    id_externo: str
    url_pago: str
    pasarela: str
    datos: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Notificacion:
    """Una notificación entrante, ya traducida."""

    id_externo: str
    codigo_reserva: str | None
    estado: EstadoPago
    monto: Decimal | None
    pasarela: str
    datos: dict[str, Any] = field(default_factory=dict)


class PasarelaNoDisponible(Exception):
    """La pasarela no está configurada o no se puede usar todavía."""


class NotificacionInvalida(Exception):
    """La notificación no viene de la pasarela que dice."""


class ErrorDePasarela(Exception):
    """La pasarela respondió con un error."""


class Pasarela(ABC):
    """Una billetera o procesador de pagos."""

    codigo: str
    nombre: str
    #: Si acredita la comisión a la plataforma y el resto al prestador en una
    #: sola operación. Sin esto la plataforma tendría que custodiar el dinero
    #: ajeno, que es justamente lo que `docs/00 §8` quiere evitar.
    reparte_automaticamente: bool = False

    @property
    @abstractmethod
    def disponible(self) -> bool:
        """Si tiene lo que necesita para operar."""

    @property
    def motivo_no_disponible(self) -> str:
        return f"{self.nombre} todavía no está configurada."

    def exigir_disponible(self) -> None:
        if not self.disponible:
            raise PasarelaNoDisponible(self.motivo_no_disponible)

    @abstractmethod
    def crear_preferencia(self, cobro: Cobro) -> Preferencia:
        """Arma el cobro y devuelve a dónde mandar al viajero."""

    @abstractmethod
    def leer_notificacion(
        self, cuerpo: bytes, cabeceras: dict[str, str]
    ) -> Notificacion:
        """Valida la firma y traduce la notificación. Lanza NotificacionInvalida."""

    @abstractmethod
    def consultar(self, id_externo: str) -> Notificacion:
        """Estado actual de un pago, para no depender solo del webhook."""

    def reintegrar(self, id_externo: str, monto: Decimal | None = None) -> Notificacion:
        """Devuelve el dinero. `monto` nulo = total."""
        raise PasarelaNoDisponible(f"{self.nombre} no tiene reintegros implementados todavía.")


class PasarelaPendiente(Pasarela):
    """Una billetera prevista cuyo adaptador todavía no existe.

    Existe a propósito: deja el lugar, las credenciales y el registro listos, y
    dice con todas las letras qué falta. Es preferible a un adaptador inventado
    que falle recién en producción, contra dinero real.
    """

    def __init__(self, codigo: str, nombre: str, variables: tuple[str, ...], nota: str = ""):
        self.codigo = codigo
        self.nombre = nombre
        self.variables = variables
        self.nota = nota

    @property
    def disponible(self) -> bool:
        return False

    @property
    def motivo_no_disponible(self) -> str:
        credenciales = ", ".join(self.variables)
        base = (
            f"{self.nombre} está prevista pero su adaptador no está escrito. "
            f"Hace falta su documentación técnica y las credenciales ({credenciales})."
        )
        return f"{base} {self.nota}".strip()

    def crear_preferencia(self, cobro: Cobro) -> Preferencia:
        raise PasarelaNoDisponible(self.motivo_no_disponible)

    def leer_notificacion(self, cuerpo: bytes, cabeceras: dict[str, str]) -> Notificacion:
        raise PasarelaNoDisponible(self.motivo_no_disponible)

    def consultar(self, id_externo: str) -> Notificacion:
        raise PasarelaNoDisponible(self.motivo_no_disponible)
