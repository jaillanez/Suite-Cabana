"""Contrato común de los canales de notificación (docs/01 §5 R9).

Igual que con las pasarelas de pago, el sistema no se ata a un proveedor: habla
con esta interfaz. El correo y WhatsApp son dos canales del mismo mecanismo.

Toda notificación se guarda en el buzón antes de intentar enviarse. Guardar
primero y enviar después permite reintentar sin duplicar y saber qué se le dijo a
quién: un envío que se pierde en el aire no se puede auditar ni reclamar.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.enums import CanalNotificacion


@dataclass(frozen=True)
class Mensaje:
    destino: str
    asunto: str
    cuerpo: str


class CanalNoDisponible(Exception):
    """El canal no está configurado."""


class ErrorDeEnvio(Exception):
    """El proveedor rechazó el envío."""


class Canal(ABC):
    canal: CanalNotificacion
    nombre: str

    @property
    @abstractmethod
    def disponible(self) -> bool:
        """Si tiene lo que necesita para enviar."""

    @property
    def motivo_no_disponible(self) -> str:
        return f"{self.nombre} no está configurado."

    @abstractmethod
    def enviar(self, mensaje: Mensaje) -> None:
        """Envía o lanza ErrorDeEnvio."""


class CanalPendiente(Canal):
    """Un canal previsto cuyo proveedor todavía no se decidió.

    `docs/01 §9` deja abierto el proveedor de WhatsApp. Hasta que se elija, las
    notificaciones de ese canal se guardan en el buzón marcadas como descartadas:
    quedan registradas y se pueden reenviar el día que haya proveedor, en vez de
    perderse.
    """

    def __init__(self, canal: CanalNotificacion, nombre: str, nota: str = ""):
        self.canal = canal
        self.nombre = nombre
        self.nota = nota

    @property
    def disponible(self) -> bool:
        return False

    @property
    def motivo_no_disponible(self) -> str:
        return f"{self.nombre} no tiene proveedor definido todavía. {self.nota}".strip()

    def enviar(self, mensaje: Mensaje) -> None:
        raise CanalNoDisponible(self.motivo_no_disponible)
