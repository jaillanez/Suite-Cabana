"""Registro de pasarelas de pago.

Agregar una billetera es escribir un adaptador que cumpla `Pasarela` y sumarlo
acá. El resto del sistema no se entera.

Las que figuran como `PasarelaPendiente` están previstas y tienen su lugar y sus
credenciales, pero su adaptador todavía no está escrito: hace falta la
documentación técnica de cada una. Se listan a propósito, con el motivo a la
vista, en vez de inventar endpoints que fallarían contra dinero real.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.services.pagos.base import (
    Cobro,
    ErrorDePasarela,
    EstadoPago,
    Notificacion,
    NotificacionInvalida,
    Pasarela,
    PasarelaNoDisponible,
    PasarelaPendiente,
    Preferencia,
)
from app.services.pagos.mercadopago import MercadoPago
from app.services.pagos.simulada import Simulada

__all__ = [
    "Cobro",
    "ErrorDePasarela",
    "EstadoPago",
    "MercadoPago",
    "Notificacion",
    "NotificacionInvalida",
    "Pasarela",
    "PasarelaNoDisponible",
    "PasarelaPendiente",
    "Preferencia",
    "Simulada",
    "disponibles",
    "obtener",
    "predeterminada",
    "todas",
]

# Previstas: el lugar y las credenciales están; el adaptador se escribe cuando
# tengamos su documentación y una cuenta para probar.
PENDIENTES = (
    PasarelaPendiente(
        "modo",
        "MODO",
        ("MODO_CLIENT_ID", "MODO_CLIENT_SECRET", "MODO_WEBHOOK_SECRET"),
        "Es la billetera del consorcio de bancos argentinos.",
    ),
    PasarelaPendiente(
        "uala",
        "Ualá",
        ("UALA_API_KEY", "UALA_WEBHOOK_SECRET"),
    ),
    PasarelaPendiente(
        "cuenta_dni",
        "Cuenta DNI",
        ("CUENTA_DNI_API_KEY", "CUENTA_DNI_WEBHOOK_SECRET"),
        "Banco Provincia; muy usada en Buenos Aires.",
    ),
    PasarelaPendiente(
        "naranja_x",
        "Naranja X",
        ("NARANJA_X_API_KEY", "NARANJA_X_WEBHOOK_SECRET"),
    ),
    PasarelaPendiente(
        "paypal",
        "PayPal",
        ("PAYPAL_CLIENT_ID", "PAYPAL_SECRET"),
        "Para viajeros del exterior, si se habilita cobrar en dólares.",
    ),
)


def todas() -> dict[str, Pasarela]:
    """Todas las pasarelas conocidas, disponibles o no."""
    registro: dict[str, Pasarela] = {
        Simulada.codigo: Simulada(),
        MercadoPago.codigo: MercadoPago(),
    }
    for p in PENDIENTES:
        registro[p.codigo] = p
    return registro


def disponibles() -> dict[str, Pasarela]:
    """Las que se pueden usar ahora mismo."""
    return {codigo: p for codigo, p in todas().items() if p.disponible}


def obtener(codigo: str) -> Pasarela:
    pasarela = todas().get(codigo)
    if pasarela is None:
        raise PasarelaNoDisponible(f"No conocemos la pasarela «{codigo}»")
    return pasarela


def predeterminada() -> Pasarela:
    """La configurada, si está disponible; si no, la primera que sí lo esté."""
    s = get_settings()
    elegida = todas().get(s.pasarela_predeterminada)
    if elegida is not None and elegida.disponible:
        return elegida
    restantes = disponibles()
    if not restantes:
        raise PasarelaNoDisponible(
            "No hay ninguna pasarela de pago configurada. Cargá las credenciales "
            "de al menos una en el archivo .env."
        )
    return next(iter(restantes.values()))
