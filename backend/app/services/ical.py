"""Lectura y escritura de calendarios iCal (docs/01 §5 R3).

El prestador ya publica en Booking y en Airbnb. Si no se sincronizan los
calendarios, la misma noche se vende dos veces: eso es exactamente lo que el
producto promete que no pasa. Acá se traduce entre nuestros bloqueos y el formato
que esas plataformas entienden.

Convención de fechas: en iCal, `DTEND` de un evento de día completo es **exclusivo**
—es el día de salida, que queda libre para el próximo huésped— igual que el
`daterange [)` que usa la base. Las dos puntas coinciden sin conversiones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from icalendar import Calendar, Event

PRODID = "-//Suite Cabana//Calendario de disponibilidad//ES"


@dataclass(frozen=True)
class Ocupacion:
    """Un tramo ocupado, con `hasta` exclusivo."""

    desde: date
    hasta: date
    resumen: str = "Ocupado"
    uid: str | None = None


class CalendarioIlegible(Exception):
    """El archivo no es un iCal que podamos leer."""


def _a_fecha(valor) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return None


def generar(nombre: str, ocupaciones: list[Ocupacion], token: str) -> bytes:
    """El calendario que Booking o Airbnb van a leer.

    No se publica quién reservó ni cuánto pagó: solo qué noches están tomadas.
    Un calendario exportado es una URL sin contraseña.
    """
    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", nombre)

    for i, o in enumerate(ocupaciones):
        evento = Event()
        evento.add("uid", o.uid or f"{token}-{o.desde.isoformat()}-{i}@suite-cabana")
        evento.add("dtstamp", datetime.now())
        evento.add("dtstart", o.desde)
        evento.add("dtend", o.hasta)
        evento.add("summary", o.resumen)
        evento.add("transp", "OPAQUE")
        cal.add_component(evento)

    return cal.to_ical()


def parsear(contenido: bytes | str) -> list[Ocupacion]:
    """Los tramos ocupados de un calendario ajeno.

    Se ignora todo lo que no sea un evento de día completo con inicio y fin: los
    calendarios de las plataformas traen recordatorios, zonas horarias y basura
    que no dice nada sobre disponibilidad.
    """
    if isinstance(contenido, str):
        contenido = contenido.encode("utf-8")
    try:
        cal = Calendar.from_ical(contenido)
    except Exception as e:  # noqa: BLE001 - la librería levanta de todo
        raise CalendarioIlegible(str(e)) from e

    ocupaciones: list[Ocupacion] = []
    for componente in cal.walk("VEVENT"):
        desde = _a_fecha(componente.get("dtstart").dt if componente.get("dtstart") else None)
        hasta = _a_fecha(componente.get("dtend").dt if componente.get("dtend") else None)
        if desde is None:
            continue
        if hasta is None or hasta <= desde:
            # Sin fin, o con fin inválido: se asume una noche.
            hasta = date.fromordinal(desde.toordinal() + 1)
        resumen = str(componente.get("summary") or "Ocupado")
        ocupaciones.append(
            Ocupacion(
                desde=desde,
                hasta=hasta,
                resumen=re.sub(r"\s+", " ", resumen)[:200],
                uid=str(componente.get("uid")) if componente.get("uid") else None,
            )
        )
    return sorted(ocupaciones, key=lambda o: o.desde)


def restar(pedidos: list[Ocupacion], ocupados: list[tuple[date, date]]) -> list[Ocupacion]:
    """Saca de los tramos pedidos las partes que ya están tomadas por otra fuente.

    La base impide que dos bloqueos activos de la misma unidad se superpongan, que
    es la garantía de cero dobles reservas. Al importar un calendario ajeno no se
    puede pisar una reserva propia: se importa solo lo que queda libre.
    """
    libres: list[Ocupacion] = []
    for pedido in pedidos:
        tramos = [(pedido.desde, pedido.hasta)]
        for ini_o, fin_o in ocupados:
            siguientes: list[tuple[date, date]] = []
            for ini, fin in tramos:
                if fin <= ini_o or ini >= fin_o:
                    siguientes.append((ini, fin))
                    continue
                if ini < ini_o:
                    siguientes.append((ini, ini_o))
                if fin > fin_o:
                    siguientes.append((fin_o, fin))
            tramos = siguientes
        for ini, fin in tramos:
            if fin > ini:
                libres.append(
                    Ocupacion(desde=ini, hasta=fin, resumen=pedido.resumen, uid=pedido.uid)
                )
    return libres
