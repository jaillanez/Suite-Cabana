"""De una dirección escrita a un punto en el mapa, para no pedirle al prestador que
busque su casa en un mapa a mano.

Usa Nominatim (OpenStreetMap), gratis y sin clave. Sus condiciones de uso piden:
- como mucho **una consulta por segundo** (acá se espacian con un candado);
- identificar la aplicación en el User-Agent (el nombre y el sitio, sin datos
  de nadie);
- guardar lo ya consultado (acá, en memoria).

El resultado se acepta solo si cae cerca de la localidad de la publicación: "San
Martín 120" existe en cientos de pueblos, y un punto en otra provincia es peor que
ninguno. El prestador siempre puede corregir el pin a mano.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

#: Cuán lejos del centro de la localidad puede caer la dirección.
DISTANCIA_MAXIMA_KM = 40.0
ESPERA_MINIMA_S = 1.1
TIEMPO_MAXIMO_S = 6.0
MEMORIA = 512

_candado = threading.Lock()
_ultima = 0.0
_memoria: OrderedDict[str, tuple[float, float] | None] = OrderedDict()


@dataclass(frozen=True)
class Punto:
    lat: float
    lon: float


def _km(a: Punto, b: Punto) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(
        (lo2 - lo1) / 2
    ) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _consultar(texto: str) -> tuple[float, float] | None:
    """Una consulta a Nominatim, respetando su ritmo. None si no hay resultado o
    si el servicio no responde: ubicar es una ayuda, nunca traba el guardado."""
    global _ultima
    s = get_settings()
    if not s.geocodificador_url:
        return None
    with _candado:
        if texto in _memoria:
            _memoria.move_to_end(texto)
            return _memoria[texto]
        espera = ESPERA_MINIMA_S - (time.monotonic() - _ultima)
        if espera > 0:
            time.sleep(espera)
        try:
            r = httpx.get(
                s.geocodificador_url,
                params={"q": texto, "format": "jsonv2", "limit": 1, "countrycodes": "ar"},
                headers={
                    "User-Agent": f"SuiteCabana/1.0 (+{s.url_publica_web})",
                    "Accept-Language": "es",
                },
                timeout=TIEMPO_MAXIMO_S,
            )
            r.raise_for_status()
            filas = r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("No se pudo ubicar la dirección: %s", e.__class__.__name__)
            return None
        finally:
            _ultima = time.monotonic()
        try:
            punto = (float(filas[0]["lat"]), float(filas[0]["lon"])) if filas else None
        except (KeyError, TypeError, ValueError, IndexError):
            punto = None
        _memoria[texto] = punto
        if len(_memoria) > MEMORIA:
            _memoria.popitem(last=False)
        return punto


def ubicar(
    direccion: str, localidad: str, provincia: str, centro: Punto | None
) -> Punto | None:
    """El punto de una dirección en esa localidad, o None si no se encuentra o cae
    lejos (más de 40 km del centro de la localidad)."""
    direccion = (direccion or "").strip()
    if len(direccion) < 3:
        return None
    hallado = _consultar(f"{direccion}, {localidad}, {provincia}, Argentina")
    if hallado is None:
        return None
    punto = Punto(*hallado)
    if centro is not None and _km(punto, centro) > DISTANCIA_MAXIMA_KM:
        return None
    return punto
