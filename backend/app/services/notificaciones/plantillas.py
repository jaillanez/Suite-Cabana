"""Textos de las notificaciones (docs/01 §5 R9).

Español rioplatense, con voseo, como el resto del producto. Cada mensaje dice qué
pasó, con qué reserva, y qué tiene que hacer quien lo recibe. Nada de "estimado
usuario".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plantilla:
    asunto: str
    cuerpo: str


def _fechas(datos: dict) -> str:
    return f"del {datos['desde']} al {datos['hasta']}"


PLANTILLAS = {
    # Al viajero
    "reserva_creada": lambda d: Plantilla(
        asunto=f"Te guardamos {d['alojamiento']} — reserva {d['codigo']}",
        cuerpo=(
            f"Hola {d['nombre']},\n\n"
            f"Guardamos {d['alojamiento']} ({d['unidad']}) {_fechas(d)}.\n"
            f"Total: {d['total']}.\n\n"
            f"Te reservamos las fechas por un rato mientras completás el pago. "
            f"Si no lo hacés, se liberan solas.\n\n"
            f"Seguí tu reserva en {d['enlace']}\n"
        ),
    ),
    "reserva_confirmada": lambda d: Plantilla(
        asunto=f"Confirmada: {d['alojamiento']} — reserva {d['codigo']}",
        cuerpo=(
            f"Hola {d['nombre']},\n\n"
            f"Está todo listo. {d['alojamiento']} ({d['unidad']}) {_fechas(d)}.\n"
            f"Código de reserva: {d['codigo']}.\n\n"
            f"El prestador te va a contactar con los detalles de la llegada.\n\n"
            f"{d['enlace']}\n"
        ),
    ),
    "reserva_cancelada": lambda d: Plantilla(
        asunto=f"Cancelada la reserva {d['codigo']}",
        cuerpo=(
            f"Hola {d['nombre']},\n\n"
            f"Se canceló la reserva de {d['alojamiento']} {_fechas(d)}.\n"
            f"Motivo: {d.get('motivo') or 'sin especificar'}.\n\n"
            f"{d.get('reintegro', '')}\n\n"
            f"{d['enlace']}\n"
        ),
    ),
    "recordatorio_estadia": lambda d: Plantilla(
        asunto=f"Tu estadía en {d['alojamiento']} empieza pronto",
        cuerpo=(
            f"Hola {d['nombre']},\n\n"
            f"Te esperan en {d['alojamiento']} ({d['unidad']}) {_fechas(d)}.\n"
            f"{d.get('horarios', '')}\n\n"
            f"{d['enlace']}\n"
        ),
    ),
    "pedido_resena": lambda d: Plantilla(
        asunto=f"¿Cómo te fue en {d['alojamiento']}?",
        cuerpo=(
            f"Hola {d['nombre']},\n\n"
            f"Terminó tu estadía en {d['alojamiento']}. Contanos cómo te fue: le sirve "
            f"al próximo viajero y al prestador.\n\n"
            f"{d['enlace']}\n"
        ),
    ),
    # Al prestador
    "nueva_reserva": lambda d: Plantilla(
        asunto=f"Nueva reserva en {d['alojamiento']} — {d['codigo']}",
        cuerpo=(
            f"Hola,\n\n"
            f"{d['viajero']} reservó {d['unidad']} de {d['alojamiento']} {_fechas(d)}, "
            f"para {d['personas']}.\n"
            f"Te queda: {d['neto']} (ya descontada la comisión).\n\n"
            f"{d.get('accion', '')}\n\n"
            f"{d['enlace']}\n"
        ),
    ),
    "reserva_cancelada_prestador": lambda d: Plantilla(
        asunto=f"Se canceló una reserva en {d['alojamiento']} — {d['codigo']}",
        cuerpo=(
            f"Hola,\n\n"
            f"Se canceló la reserva de {d['unidad']} {_fechas(d)}.\n"
            f"Motivo: {d.get('motivo') or 'sin especificar'}.\n"
            f"Las fechas quedaron libres de nuevo.\n\n"
            f"{d['enlace']}\n"
        ),
    ),
}


def armar(evento: str, datos: dict) -> Plantilla:
    constructor = PLANTILLAS.get(evento)
    if constructor is None:
        raise KeyError(f"No hay plantilla para «{evento}»")
    return constructor(datos)
