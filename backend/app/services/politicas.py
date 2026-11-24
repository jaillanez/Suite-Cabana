"""La política de cancelación que rige una publicación.

El operador mantiene plantillas (flexible, moderada, estricta, eventos). Cada
prestador puede elegir una o cargar sus propios tramos (docs/05 §2): no es una
regla de la plataforma. Lo que se muestra en la ficha y lo que se copia en la
reserva salen de acá, así nunca dicen cosas distintas.
"""

from __future__ import annotations

from app.models import Publicacion
from app.models.enums import ModoReserva

#: Más tramos que esto no se leen; con 5 alcanza para cualquier escalera.
MAX_TRAMOS = 5
MAX_DIAS_ANTES = 365
PROPIA = "propia"


class TramosInvalidos(ValueError):
    pass


def validar_tramos(tramos: list[dict]) -> list[dict]:
    """Normaliza los tramos del prestador: enteros, en rango, sin días repetidos,
    del más anticipado al menos. Levanta TramosInvalidos."""
    if not tramos:
        raise TramosInvalidos("Cargá al menos un tramo")
    if len(tramos) > MAX_TRAMOS:
        raise TramosInvalidos(f"Hasta {MAX_TRAMOS} tramos")
    limpios = []
    for t in tramos:
        try:
            dias = int(t["dias_antes"])
            porcentaje = int(t["porcentaje_reintegro"])
        except (KeyError, TypeError, ValueError) as e:
            raise TramosInvalidos("Cada tramo lleva días de anticipación y porcentaje") from e
        if not 0 <= dias <= MAX_DIAS_ANTES:
            raise TramosInvalidos(f"Los días de anticipación van de 0 a {MAX_DIAS_ANTES}")
        if not 0 <= porcentaje <= 100:
            raise TramosInvalidos("El porcentaje de reintegro va de 0 a 100")
        limpios.append({"dias_antes": dias, "porcentaje_reintegro": porcentaje})
    if len({t["dias_antes"] for t in limpios}) != len(limpios):
        raise TramosInvalidos("Hay dos tramos con los mismos días")
    return sorted(limpios, key=lambda t: -t["dias_antes"])


def vigente(publicacion: Publicacion) -> dict | None:
    """{codigo, nombre, descripcion, tramos} de la publicación, o None si no tiene.

    Para servicios que pueden no salir (excursiones) suma `reintegro_si_no_sale`:
    lo que se devuelve si el prestador suspende o no se llega al mínimo.
    """
    plantilla = publicacion.politica_cancelacion
    if publicacion.tramos_cancelacion:
        politica = {
            "codigo": PROPIA,
            "nombre": "Propia del prestador",
            "descripcion": None,
            "tramos": publicacion.tramos_cancelacion,
        }
    elif plantilla is not None:
        politica = {
            "codigo": plantilla.codigo,
            "nombre": plantilla.nombre,
            "descripcion": plantilla.descripcion,
            "tramos": plantilla.tramos,
        }
    else:
        politica = None
    if publicacion.tipo_servicio.modo_reserva is ModoReserva.TURNO_CUPO:
        politica = politica or {
            "codigo": PROPIA, "nombre": "Sin reintegro", "descripcion": None, "tramos": [],
        }
        politica["reintegro_si_no_sale"] = publicacion.reintegro_si_no_sale
    return politica


def snapshot(publicacion: Publicacion) -> dict | None:
    """Lo que la reserva guarda: sin la descripción, que es texto de la plantilla."""
    politica = vigente(publicacion)
    if politica is None:
        return None
    return {k: v for k, v in politica.items() if k != "descripcion"}
