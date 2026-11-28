"""Leer el texto de un anuncio de Airbnb o Booking que el prestador pegó, para no
cargar todo de nuevo.

No se sale a ningún lado: Airbnb y Booking no ofrecen exportar un anuncio y sus
condiciones prohíben copiarlo de forma automática. El prestador copia el texto
de su propio anuncio y lo pega; acá se lo ordena con reglas simples y se
devuelve una **propuesta**. No se guarda nada: el prestador la revisa, la
corrige y la aplica con el editor de siempre.

Lo que se busca:
- la descripción (el texto corrido, sobre todo bajo "Acerca de este espacio");
- las reglas de la casa;
- los horarios de llegada y salida;
- las comodidades del catálogo que nombra, salvo las que dice que no tiene;
- capacidad: huéspedes, dormitorios, camas y baños.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import time

TEXTO_MAXIMO = 30_000
DESCRIPCION_MAXIMA = 2_000
REGLAS_MAXIMAS = 10

#: Comodidades de alojamiento y las palabras con que las nombran Airbnb y Booking.
#: Se comparan sin tildes ni mayúsculas y por palabra entera.
PALABRAS: dict[str, tuple[str, ...]] = {
    "wifi": ("wifi", "wi-fi", "internet"),
    "pileta": ("pileta", "piscina"),
    "mascotas": ("se admiten mascotas", "mascotas permitidas", "acepta mascotas",
                 "pet friendly", "admite mascotas"),
    "cochera": ("cochera", "estacionamiento", "garage", "garaje", "aparcamiento", "parking"),
    "parrilla": ("parrilla", "asador", "barbacoa"),
    "aire": ("aire acondicionado",),
    "calefaccion": ("calefaccion", "calefactor", "estufa", "losa radiante", "hogar a lena"),
    "desayuno": ("desayuno",),
    "lavarropas": ("lavarropas", "lavadora", "lavarropa"),
    "tv": ("tv", "televisor", "television", "smart tv"),
    "ropa_blanca": ("ropa de cama", "sabanas", "toallas", "ropa blanca"),
    "accesible": ("silla de ruedas", "accesible", "adaptado para personas con movilidad"),
    "quincho": ("quincho",),
}

#: Una línea con esto habla de lo que NO hay: "No disponible: Wifi". "Sin" no
#: entra: "estacionamiento sin cargo" sí lo tiene.
NEGACION = re.compile(
    r"\b(no disponible|no incluid[oa]s?|no se admite[n]?|no se permite[n]?|no hay|"
    r"no tiene|no cuenta con)\b"
)

#: Encabezados de sección de Airbnb y Booking.
DESCRIPCION_TITULOS = ("acerca de este espacio", "acerca de este alojamiento", "el espacio",
                       "descripcion", "sobre este alojamiento", "sobre el alojamiento")
REGLAS_TITULOS = ("reglas de la casa", "normas de la casa", "normas del alojamiento",
                  "cosas que tenes que saber", "cosas que debes saber", "condiciones")
OTROS_TITULOS = ("lo que este lugar ofrece", "servicios", "servicios mas populares",
                 "donde vas a dormir", "donde dormiras", "ubicacion", "resenas", "anfitrion",
                 "disponibilidad", "politica de cancelacion", "seguridad y propiedad",
                 "a donde iras", "mostrar mas", "acceso de los huespedes",
                 "otros aspectos a destacar", "informacion importante", "preguntas frecuentes")


@dataclass
class Propuesta:
    descripcion: str | None = None
    reglas_casa: str | None = None
    hora_ingreso: time | None = None
    hora_salida: time | None = None
    comodidades: list[str] = field(default_factory=list)
    huespedes: int | None = None
    dormitorios: int | None = None
    camas: int | None = None
    banos: str | None = None  # "1,5"

    @property
    def vacia(self) -> bool:
        return not any(
            (self.descripcion, self.reglas_casa, self.hora_ingreso, self.hora_salida,
             self.comodidades, self.huespedes, self.dormitorios, self.camas, self.banos)
        )


class TextoInvalido(ValueError):
    pass


def _plano(s: str) -> str:
    """Sin tildes y en minúscula, para comparar."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _es_titulo(linea: str, titulos: tuple[str, ...]) -> bool:
    plano = _plano(linea).strip(" :·-")
    return any(plano == t or plano.startswith(t + " ") and len(plano) < len(t) + 25
               for t in titulos)


def _todos_los_titulos() -> tuple[str, ...]:
    return DESCRIPCION_TITULOS + REGLAS_TITULOS + OTROS_TITULOS


def _seccion(lineas: list[str], titulos: tuple[str, ...]) -> list[str]:
    """Las líneas bajo el primer encabezado de `titulos`, hasta el siguiente encabezado."""
    for i, linea in enumerate(lineas):
        if _es_titulo(linea, titulos):
            fin = len(lineas)
            for j in range(i + 1, len(lineas)):
                # Un encabezado del mismo grupo no corta: en Airbnb "Cosas que tenés
                # que saber" va justo antes de "Reglas de la casa".
                if _es_titulo(lineas[j], _todos_los_titulos()) and not _es_titulo(
                    lineas[j], titulos
                ):
                    fin = j
                    break
            # Sin los encabezados del medio: no son contenido.
            return [x for x in lineas[i + 1 : fin] if x.strip() and not _es_titulo(x, titulos)]
    return []


def _descripcion(lineas: list[str]) -> str | None:
    bajo_titulo = _seccion(lineas, DESCRIPCION_TITULOS)
    # Texto corrido: oraciones de verdad, no ítems sueltos de una lista.
    corrido = [x.strip() for x in (bajo_titulo or lineas) if len(x.strip()) >= 60]
    if not corrido:
        return None
    texto = ""
    for parrafo in corrido:
        if _plano(parrafo).startswith(("mostrar mas", "traducido", "ver traduccion")):
            continue
        if len(texto) + len(parrafo) + 2 > DESCRIPCION_MAXIMA:
            break
        texto = f"{texto}\n\n{parrafo}" if texto else parrafo
    return texto or None


def _reglas(lineas: list[str]) -> str | None:
    seccion = _seccion(lineas, REGLAS_TITULOS)
    sueltas = [
        x for x in lineas
        if re.search(r"\b(no se permite|prohibido|no fumar|fiestas|silencio|horas de descanso)",
                     _plano(x))
    ]
    reglas: list[str] = []
    for x in [*seccion, *sueltas]:
        x = x.strip(" •·-*")
        plano = _plano(x)
        # Los horarios van en sus campos; "Mostrar más" es un botón copiado.
        if not x or len(x) > 200 or plano.startswith(("mostrar", "llegada", "salida",
                                                       "check-in", "check-out", "entrada")):
            continue
        if x not in reglas:
            reglas.append(x)
        if len(reglas) >= REGLAS_MAXIMAS:
            break
    return "\n".join(f"• {r}" for r in reglas) or None


HORA = r"(\d{1,2})(?:[:.](\d{2}))?\s*(h|hs|horas|a\.?\s?m\.?|p\.?\s?m\.?)?"


def _hora(plano: str, palabras: str) -> time | None:
    """La primera hora después de una de esas palabras ("Llegada: a partir de las 15:00")."""
    m = re.search(rf"\b(?:{palabras})\b[^0-9\n]{{0,40}}{HORA}", plano)
    if not m:
        return None
    horas, minutos, sufijo = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "")
    if not m.group(2) and not sufijo:
        return None  # un número suelto ("2 baños") no es una hora
    sufijo = sufijo.replace(".", "").replace(" ", "")
    if sufijo == "pm" and horas < 12:
        horas += 12
    if sufijo == "am" and horas == 12:
        horas = 0
    if not (0 <= horas <= 23 and 0 <= minutos <= 59):
        return None
    return time(horas, minutos)


def _comodidades(lineas: list[str]) -> list[str]:
    halladas: list[str] = []
    for linea in lineas:
        plano = _plano(linea)
        if NEGACION.search(plano):
            continue
        for codigo, palabras in PALABRAS.items():
            if codigo in halladas:
                continue
            if any(re.search(rf"(?<![a-z]){re.escape(p)}(?![a-z])", plano) for p in palabras):
                halladas.append(codigo)
    return halladas


def _numero(plano: str, palabras: str) -> int | None:
    m = re.search(rf"\b(\d{{1,3}})\s+(?:{palabras})\b", plano)
    return int(m.group(1)) if m else None


def leer(texto: str) -> Propuesta:
    """La propuesta que sale del texto pegado. Lo que no se encuentra queda vacío."""
    texto = (texto or "").replace("\r\n", "\n")
    if len(texto.strip()) < 20:
        raise TextoInvalido("Pegá el texto del anuncio: así es muy corto para leer algo")
    if len(texto) > TEXTO_MAXIMO:
        raise TextoInvalido("El texto es muy largo: hasta 30.000 caracteres")
    lineas = [x.strip() for x in texto.split("\n")]
    plano = _plano(texto)
    banos = re.search(r"\b(\d{1,2}(?:[.,]5)?)\s+banos?\b", plano)
    return Propuesta(
        descripcion=_descripcion(lineas),
        reglas_casa=_reglas(lineas),
        hora_ingreso=_hora(plano, "llegada|check-in|check in|entrada|ingreso"),
        hora_salida=_hora(plano, "salida|check-out|check out"),
        comodidades=_comodidades(lineas),
        huespedes=_numero(plano, "huespedes|huesped|personas|adultos"),
        dormitorios=_numero(plano, "dormitorios|dormitorio|habitaciones|habitacion"),
        camas=_numero(plano, "camas|cama"),
        banos=banos.group(1).replace(".", ",") if banos else None,
    )
