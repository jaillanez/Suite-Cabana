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
