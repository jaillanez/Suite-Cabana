"""De una dirección escrita a un punto en el mapa, para no pedirle al prestador que
busque su casa en un mapa a mano.

Usa Nominatim (OpenStreetMap), gratis y sin clave. Sus condiciones de uso piden:
- como mucho **una consulta por segundo** (acá cada pedido reserva su turno, y si
  falta más de 2 s, no espera: el prestador marca el punto a mano);
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
#: Si el próximo turno libre está más lejos que esto, no se espera.
ESPERA_MAXIMA_S = 2.0
TIEMPO_MAXIMO_S = 4.0
#: Sin centro de la localidad, al menos que caiga en Argentina (continental).
ARGENTINA = (-55.1, -21.7, -73.6, -53.5)  # lat mín, lat máx, lon mín, lon máx
MEMORIA = 512

_candado = threading.Lock()
_proxima = 0.0
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


def _turno() -> float | None:
    """Reserva el próximo turno de consulta (una por segundo, entre todos). None si
    falta demasiado: no se encola a nadie detrás de un servicio lento."""
    global _proxima
    with _candado:
        ahora = time.monotonic()
        turno = max(ahora, _proxima)
        if turno - ahora > ESPERA_MAXIMA_S:
            return None
        _proxima = turno + ESPERA_MINIMA_S
        return turno


def _valido(lat: float, lon: float) -> bool:
    return (
        math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
    )


def _consultar(texto: str) -> tuple[float, float] | None:
    """Una consulta a Nominatim, respetando su ritmo. None si no hay resultado, si el
    servicio no responde o si habría que esperar turno: ubicar es una ayuda, nunca
    traba el guardado.

    El candado solo cuida el turno y la memoria: la consulta por red va afuera, así
    un servicio lento no deja a todos los pedidos esperando detrás.
    """
    s = get_settings()
    if not s.geocodificador_url:
        return None
    with _candado:
        if texto in _memoria:
            _memoria.move_to_end(texto)
            return _memoria[texto]
    turno = _turno()
    if turno is None:
        return None
    espera = turno - time.monotonic()
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
        punto = (float(filas[0]["lat"]), float(filas[0]["lon"])) if filas else None
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as e:
        log.warning("No se pudo ubicar la dirección: %s", e.__class__.__name__)
        return None
    if punto is not None and not _valido(*punto):
        punto = None
    with _candado:
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
    if not _valido(punto.lat, punto.lon):
        return None
    if centro is None:
        la_min, la_max, lo_min, lo_max = ARGENTINA
        return punto if la_min <= punto.lat <= la_max and lo_min <= punto.lon <= lo_max else None
    return punto if _km(punto, centro) <= DISTANCIA_MAXIMA_KM else None
