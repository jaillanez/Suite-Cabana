"""Descargas de direcciones que carga un usuario (hoy: calendarios iCal).

Una URL pegada por un anfitrión la descarga el servidor, así que sin control
sirve para que el servidor le pegue a su propia red: la base, otros servicios
del mismo equipo, la metadata del proveedor. Acá solo se sale a internet:

- http o https, puertos 80/443, sin usuario ni clave en la dirección;
- el nombre se resuelve y **todas** sus IP tienen que ser públicas;
- la conexión va a la IP ya revisada (el nombre viaja en Host y en SNI, así
  que el certificado se valida igual): un DNS que cambia de respuesta entre la
  revisión y la conexión no la desvía;
- las redirecciones se siguen a mano y cada salto se revisa de nuevo;
- la respuesta tiene un tamaño máximo.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

PUERTOS = {"http": 80, "https": 443}
MAX_REDIRECCIONES = 5
MAX_BYTES = 5 * 1024 * 1024


class DireccionNoPermitida(ValueError):
    """La dirección apunta a algo que no es internet pública."""


def validar_forma(url: str) -> None:
    """Lo que se puede revisar sin salir a la red. Sirve al guardar la dirección."""
    partes = urlsplit(url.strip())
    if partes.scheme not in PUERTOS:
        raise DireccionNoPermitida("La dirección tiene que empezar con http:// o https://")
    if partes.username or partes.password:
        raise DireccionNoPermitida("La dirección no puede llevar usuario ni contraseña")
    if not partes.hostname:
        raise DireccionNoPermitida("A la dirección le falta el sitio")
    try:
        puerto = partes.port
    except ValueError as e:
        raise DireccionNoPermitida("El puerto de la dirección no es válido") from e
    if puerto not in (None, PUERTOS[partes.scheme]):
        raise DireccionNoPermitida("La dirección usa un puerto que no es el web estándar")
    host = partes.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise DireccionNoPermitida("Esa dirección no es pública")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if not ip.is_global:
        raise DireccionNoPermitida("Esa dirección no es pública")


def _ip_publica(host: str, puerto: int) -> str:
    try:
        resultados = socket.getaddrinfo(host, puerto, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise httpx.ConnectError(f"No se encontró {host}") from e
    ips = {r[4][0] for r in resultados}
    if not ips:
        raise httpx.ConnectError(f"No se encontró {host}")
    for ip in ips:
        if not ipaddress.ip_address(ip.split("%")[0]).is_global:
            raise DireccionNoPermitida("Esa dirección no es pública")
    return sorted(ips)[0]


def descargar_publica(url: str, *, agente: str, tiempo: float) -> bytes:
    """Descarga `url` solo si (ella y cada redirección) está en internet pública.

    Levanta `DireccionNoPermitida`, o los errores de httpx de siempre.
    """
    actual = url.strip()
    with httpx.Client(timeout=tiempo, follow_redirects=False, trust_env=False) as cliente:
        for _ in range(MAX_REDIRECCIONES + 1):
            validar_forma(actual)
            partes = urlsplit(actual)
            host = partes.hostname or ""
            puerto = partes.port or PUERTOS[partes.scheme]
            ip = _ip_publica(host, puerto)
            ip_url = f"[{ip}]" if ":" in ip else ip
            destino = urlunsplit(
                (partes.scheme, f"{ip_url}:{puerto}", partes.path or "/", partes.query, "")
            )
            cabeceras = {"User-Agent": agente, "Host": partes.netloc.rsplit("@", 1)[-1]}
            extensiones = {"sni_hostname": host} if partes.scheme == "https" else {}
            pedido = cliente.build_request(
                "GET", destino, headers=cabeceras, extensions=extensiones
            )
            respuesta = cliente.send(pedido, stream=True)
            try:
                if respuesta.is_redirect:
                    siguiente = respuesta.headers.get("location", "")
                    actual = urljoin(actual, siguiente)
                    continue
                # El error se informa con la URL original, no con la IP.
                respuesta.request = httpx.Request("GET", actual)
                respuesta.raise_for_status()
                cuerpo = bytearray()
                for trozo in respuesta.iter_bytes():
                    cuerpo += trozo
                    if len(cuerpo) > MAX_BYTES:
                        raise DireccionNoPermitida("El calendario es demasiado grande")
                return bytes(cuerpo)
            finally:
                respuesta.close()
    raise httpx.TooManyRedirects("Demasiadas redirecciones", request=httpx.Request("GET", url))
