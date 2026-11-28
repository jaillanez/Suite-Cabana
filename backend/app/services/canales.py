"""Catálogo de plataformas con las que se sincroniza el calendario (docs/01 §5 R3).

Hay dos mundos, y conviene no mezclarlos:

1. **Las que publican un iCal por alojamiento** (Airbnb, Booking, Vrbo). Son dos
   direcciones: la de ellos se pega acá, la nuestra se pega allá. Funciona hoy.
2. **Las que no se lo ofrecen al anfitrión** (Despegar). Integrarse exige su API
   de partners o un channel manager en el medio. Figuran acá, con el motivo, en
   vez de fingir que alcanza con una URL.

Lo que iCal puede y no puede: transmite **solo qué noches están ocupadas**. No
lleva precios, ni datos del huésped, ni el detalle de la reserva. Y no es en
tiempo real: cada plataforma relee los calendarios ajenos cada una a cuatro
horas, así que dos ventas simultáneas en portales distintos siguen siendo
posibles. Por eso la garantía dura está en nuestra base, no en la sincronización.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Plataforma:
    codigo: str
    nombre: str
    #: Si el anfitrión puede sacar una dirección de calendario por su cuenta.
    tiene_ical: bool
    #: Dónde encontrarla, en los términos que usa esa plataforma.
    donde_esta: str = ""
    #: Cómo se ve, para que se note si pegó otra cosa.
    ejemplo_url: str = ""
    dominios: tuple[str, ...] = ()
    nota: str = ""
    pasos: list[str] = field(default_factory=list)


PLATAFORMAS: tuple[Plataforma, ...] = (
    Plataforma(
        codigo="airbnb",
        nombre="Airbnb",
        tiene_ical=True,
        donde_esta="Calendario del anuncio → Disponibilidad → Sincronizar calendarios",
        ejemplo_url="https://www.airbnb.com/calendar/ical/12345678.ics?s=…",
        dominios=("airbnb.com", "airbnb.com.ar"),
        pasos=[
            "Entrá al anuncio y abrí su calendario.",
            "En Disponibilidad, buscá «Sincronizar calendarios».",
            "Copiá el enlace de «Exportar calendario» y pegalo acá.",
            "Después, en la misma pantalla, elegí «Importar calendario» y pegá la "
            "dirección nuestra.",
        ],
    ),
    Plataforma(
        codigo="booking",
        nombre="Booking.com",
        tiene_ical=True,
        donde_esta="Extranet → Tarifas y disponibilidad → Sincronizar calendarios",
        ejemplo_url="https://admin.booking.com/hotel/hoteladmin/ical.html?t=…",
        dominios=("booking.com",),
        nota=(
            "Está disponible para departamentos y casas. Si la propiedad está cargada como "
            "hotel y se maneja con un channel manager, la sincronización va por ahí."
        ),
        pasos=[
            "Entrá a la extranet y abrí Tarifas y disponibilidad.",
            "Elegí «Sincronizar calendarios». Con varias unidades, aparece al lado del "
            "nombre de cada una.",
            "Tocá «Exportar calendario», copiá el enlace y pegalo acá.",
            "Después usá «Importar calendario» y pegá la dirección nuestra.",
        ],
    ),
    Plataforma(
        codigo="vrbo",
        nombre="Vrbo / Expedia",
        tiene_ical=True,
        donde_esta="Panel del anuncio → Calendario → Importar y exportar",
        ejemplo_url="http://www.vrbo.com/icalendar/….ics",
        dominios=("vrbo.com", "homeaway.com", "expedia.com"),
    ),
    Plataforma(
        codigo="google",
        nombre="Google Calendar",
        tiene_ical=True,
        donde_esta=(
            "Configuración del calendario → Integrar calendario → Dirección secreta "
            "en formato iCal"
        ),
        ejemplo_url="https://calendar.google.com/calendar/ical/…/basic.ics",
        dominios=("calendar.google.com",),
        nota="Sirve para bloquear fechas que llevás en tu propio calendario.",
        pasos=[
            "Abrí Google Calendar en la computadora y entrá a Configuración (la rueda).",
            "Elegí tu calendario y, en «Integrar calendario», copiá la «Dirección secreta "
            "en formato iCal». Pegala acá.",
            "Para ver allá lo que se reserva acá: en «Otros calendarios» tocá «+» → "
            "«Desde URL» y pegá la dirección nuestra.",
        ],
    ),
    Plataforma(
        codigo="otro",
        nombre="Otra plataforma con iCal",
        tiene_ical=True,
        donde_esta="Buscá «sincronizar calendario», «exportar iCal» o «.ics» en su panel",
        ejemplo_url="https://…/calendario.ics",
        nota="Cualquier portal que publique un .ics funciona, aunque no esté en esta lista.",
    ),
    # Sin iCal para el anfitrión.
    Plataforma(
        codigo="despegar",
        nombre="Despegar",
        tiene_ical=False,
        dominios=("despegar.com", "despegar.com.ar", "decolar.com"),
        nota=(
            "Su extranet tiene calendario de disponibilidad, pero no publica un iCal que el "
            "anfitrión pueda copiar. Integrarse requiere su API de partners o un channel "
            "manager en el medio. Hasta entonces, lo vendido en Despegar hay que bloquearlo "
            "a mano acá."
        ),
    ),
)

POR_CODIGO = {p.codigo: p for p in PLATAFORMAS}


def con_ical() -> tuple[Plataforma, ...]:
    return tuple(p for p in PLATAFORMAS if p.tiene_ical)


def detectar(url: str) -> str:
    """Adivina la plataforma por el dominio, para no preguntar lo que ya se sabe."""
    minuscula = (url or "").lower()
    for p in PLATAFORMAS:
        if any(d in minuscula for d in p.dominios):
            return p.codigo
    return "otro"


# --- Revisar lo que pegó el anfitrión, antes de guardarlo ---


class EnlaceEquivocado(ValueError):
    """Lo pegado no es la dirección del calendario: se explica qué es y dónde está la buena."""


#: Lo que tiene la dirección del calendario de cada plataforma. Sin esto, lo más
#: común es pegar el enlace del anuncio, que es una página, no un calendario.
FIRMA_ICAL = {
    "airbnb": "/calendar/ical/",
    "booking": "ical",
    "vrbo": "ical",
    "google": "/ical/",
}


def revisar_enlace(url: str, plataforma: str | None) -> str:
    """La plataforma del enlace, o `EnlaceEquivocado` con qué hacer.

    - De una plataforma sin iCal (Despegar): no hay dirección que sirva.
    - De otra plataforma que la elegida ("elegiste Airbnb y es de Booking").
    - De la plataforma correcta pero no del calendario (el anuncio, la extranet).
    """
    detectada = detectar(url)
    p = POR_CODIGO.get(detectada)
    if p is not None and not p.tiene_ical:
        raise EnlaceEquivocado(f"{p.nombre} no da una dirección de calendario. {p.nota}")
    elegida = POR_CODIGO.get(plataforma or "")
    if elegida and elegida.codigo != "otro" and detectada not in ("otro", elegida.codigo):
        raise EnlaceEquivocado(
            f"Ese enlace es de {POR_CODIGO[detectada].nombre} y elegiste {elegida.nombre}. "
            "Revisá que lo hayas copiado de la plataforma correcta."
        )
    firma = FIRMA_ICAL.get(detectada)
    if firma and firma not in url.lower():
        plat = POR_CODIGO[detectada]
        raise EnlaceEquivocado(
            f"Ese parece el enlace de tu anuncio o de tu panel en {plat.nombre}, no el del "
            f"calendario. Lo encontrás en: {plat.donde_esta}. Se ve así: {plat.ejemplo_url}"
        )
    return detectada


# --- Quién lee nuestro calendario ---

#: Pistas en el User-Agent de cada plataforma cuando viene a leer el .ics. Son
#: aproximadas: si no se reconoce, queda como "otra".
LECTORES = (
    ("airbnb", ("airbnb",)),
    ("booking", ("booking.com", "booking")),
    ("vrbo", ("vrbo", "homeaway", "expedia")),
    ("google", ("google-calendar", "googlecalendar", "google")),
)
NAVEGADORES = ("mozilla", "chrome", "safari", "firefox", "edg/")


def lector(user_agent: str | None) -> str | None:
    """Qué plataforma pidió nuestro calendario. None si fue una persona con un
    navegador (el anfitrión probando el enlace): eso no cuenta como sincronizado."""
    ua = (user_agent or "").lower()
    for codigo, pistas in LECTORES:
        if any(x in ua for x in pistas):
            return codigo
    if any(x in ua for x in NAVEGADORES):
        return None
    return "otro"
