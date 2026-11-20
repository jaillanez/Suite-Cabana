"""Lee un mail de confirmación y saca de él una reserva (docs/01 §5 R3).

Existe porque Despegar no publica iCal, y porque una venta cerrada por WhatsApp
no tiene calendario ninguno. Lo que sí hay, siempre, es un mail.

Dos decisiones que mandan sobre todo lo demás:

1. **`11/10` es 11 de octubre.** Nunca 10 de noviembre. Leer una fecha argentina
   en orden norteamericano no da error: da una reserva puesta en el mes
   equivocado, que es mucho peor.
2. **Lo que no se entiende se declara.** Cada cosa que falta se nombra en
   `faltantes`, y con la lista no vacía la reserva queda esperando revisión en
   vez de bloquear fechas adivinadas. Un análisis que rellena huecos por su
   cuenta termina vendiendo dos veces la misma noche.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.services import canales

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
MESES.update({nombre[:3]: numero for nombre, numero in MESES.items()})

#: Cómo nombra cada plataforma la llegada y la salida. Se busca en este orden.
ENTRADA = ("check-in", "checkin", "check in", "entrada", "llegada", "ingreso", "desde")
SALIDA = ("check-out", "checkout", "check out", "salida", "egreso", "hasta")

_ETIQUETAS_HUESPED = ("huesped", "huespedes", "pasajero", "cliente", "titular", "a nombre de")
_ETIQUETAS_CODIGO = ("localizador", "codigo de reserva", "codigo", "reserva nro", "reserva n",
                     "numero de reserva", "booking id", "id de reserva")
_ETIQUETAS_UNIDAD = ("unidad", "alojamiento", "habitacion", "cabana", "departamento", "propiedad")


@dataclass
class Lectura:
    """Lo que se pudo entender de un mail. `faltantes` manda: si tiene algo, no bloquea."""

    plataforma: str = "particular"
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    huesped: str | None = None
    contacto: str | None = None
    personas: int | None = None
    monto: Decimal | None = None
    codigo_externo: str | None = None
    unidad_nombre: str | None = None
    faltantes: list[str] = field(default_factory=list)
    huella: str = ""

    @property
    def completa(self) -> bool:
        return not self.faltantes


def _sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def _a_texto(cuerpo: str) -> str:
    """Saca el HTML. Los mails de las plataformas casi siempre vienen en tabla."""
    texto = re.sub(r"(?is)<(script|style).*?</\1>", " ", cuerpo)
    texto = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6])>", "\n", texto)
    texto = re.sub(r"(?i)</t[dh]>", " | ", texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    entidades = {
        "&nbsp;": " ", "&amp;": "&", "&aacute;": "á", "&eacute;": "é",
        "&iacute;": "í", "&oacute;": "ó", "&uacute;": "ú", "&ntilde;": "ñ",
    }
    for entidad, signo in entidades.items():
        texto = texto.replace(entidad, signo)
    return re.sub(r"[ \t\xa0]+", " ", texto)


def _fecha(texto: str, hoy: date) -> date | None:
    """Una fecha suelta. Día primero, siempre.

    Sin año, se toma la próxima vez que pasa: un mail de confirmación habla del
    futuro, y en diciembre «5 de enero» es del año que viene.
    """
    # ISO primero: es la única forma inequívoca, y dentro de `2026-12-01` el
    # patrón día/mes encuentra `12-01` y lo lee como 12 de enero.
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", texto)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    numerica = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b", texto)
    if numerica:
        dia, mes, anio = numerica.groups()
        dia, mes = int(dia), int(mes)
        if anio:
            anio = int(anio)
            anio += 2000 if anio < 100 else 0
        else:
            anio = hoy.year
        if 1 <= mes <= 12 and 1 <= dia <= 31:
            try:
                encontrada = date(anio, mes, dia)
            except ValueError:
                return None
            if not numerica.group(3) and encontrada < hoy:
                try:
                    encontrada = date(anio + 1, mes, dia)
                except ValueError:
                    return None
            return encontrada

    # «12 de octubre de 2026», «12 oct 2026», «lun 12 de octubre».
    palabras = re.search(
        r"\b(\d{1,2})\s*(?:de\s+)?([a-z]{3,10})\.?(?:\s*(?:de\s+)?(\d{4}))?\b",
        _sin_tildes(texto.lower()),
    )
    if palabras:
        dia, mes_texto, anio = palabras.groups()
        mes = MESES.get(mes_texto) or MESES.get(mes_texto[:3])
        if mes:
            anio = int(anio) if anio else hoy.year
            try:
                encontrada = date(anio, mes, int(dia))
            except ValueError:
                return None
            if not palabras.group(3) and encontrada < hoy:
                encontrada = date(anio + 1, mes, int(dia))
            return encontrada
    return None


def _tras_etiqueta(texto: str, etiquetas: tuple[str, ...], largo: int = 90) -> str | None:
    """El pedazo que sigue a «Check-in:», «Huésped:», etc."""
    plano = _sin_tildes(texto.lower())
    for etiqueta in etiquetas:
        for coincidencia in re.finditer(re.escape(etiqueta) + r"\s*[:\-|]?\s*", plano):
            trozo = texto[coincidencia.end() : coincidencia.end() + largo]
            trozo = trozo.split("\n")[0].strip(" |\t")
            if trozo:
                return trozo
    return None


def _rango_en_una_linea(texto: str, hoy: date) -> tuple[date | None, date | None]:
    """«del 12 al 15 de octubre», «12/10/2026 - 15/10/2026», «12/10 al 15/10»."""
    plano = _sin_tildes(texto.lower())
    dos_numericas = re.search(
        r"(\d{1,2}[/\-.]\d{1,2}(?:[/\-.]\d{2,4})?)\s*(?:al?|a|hasta|[-–—>]|\bhasta el\b)\s*"
        r"(\d{1,2}[/\-.]\d{1,2}(?:[/\-.]\d{2,4})?)",
        plano,
    )
    if dos_numericas:
        return _fecha(dos_numericas.group(1), hoy), _fecha(dos_numericas.group(2), hoy)

    # «del 12 al 15 de octubre [de 2026]»: el mes lo pone la segunda.
    mismo_mes = re.search(
        r"del?\s+(\d{1,2})\s+al\s+(\d{1,2})\s+de\s+([a-z]{3,10})\.?(?:\s+de\s+(\d{4}))?", plano
    )
    if mismo_mes:
        dia_uno, dia_dos, mes_texto, anio = mismo_mes.groups()
        cola = f"{mes_texto}{' ' + anio if anio else ''}"
        return _fecha(f"{dia_uno} de {cola}", hoy), _fecha(f"{dia_dos} de {cola}", hoy)
    return None, None


def _monto(texto: str) -> Decimal | None:
    """Importes argentinos: punto de miles, coma decimal."""
    encontrado = re.search(
        r"(?:\$|ARS|AR\$|pesos)\s*([\d][\d.\s]*(?:,\d{1,2})?)", texto, re.IGNORECASE
    )
    if not encontrado:
        return None
    crudo = encontrado.group(1).replace(" ", "").replace(".", "").replace(",", ".")
    try:
        valor = Decimal(crudo)
    except InvalidOperation:
        return None
    return valor if valor > 0 else None


def _personas(texto: str) -> int | None:
    encontrado = re.search(
        r"\b(\d{1,2})\s*(?:personas?|huespedes?|pasajeros?|adultos?)\b", _sin_tildes(texto.lower())
    )
    if encontrado:
        return int(encontrado.group(1))
    etiqueta = _tras_etiqueta(texto, ("huespedes", "pasajeros", "personas", "ocupantes"), largo=12)
    if etiqueta:
        numero = re.search(r"\d{1,2}", etiqueta)
        if numero:
            return int(numero.group())
    return None


def _contacto(texto: str) -> str | None:
    correo = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", texto)
    if correo and not re.search(
        r"(noreply|no-reply|notificaciones|donotreply)", correo.group(), re.IGNORECASE
    ):
        return correo.group()
    telefono = re.search(r"(?:\+?54\s*)?(?:9\s*)?(?:\d[\s\-]?){9,13}", texto)
    return telefono.group().strip() if telefono else None


def _limpiar_nombre(crudo: str | None) -> str | None:
    """Nombre de persona. Corta en el primer dígito: lo que sigue es un teléfono."""
    if not crudo:
        return None
    nombre = re.split(r"[|<(\d]", crudo)[0].strip(" .,:;-")
    return nombre[:120] if 2 <= len(nombre) <= 120 else None


def _limpiar_unidad(crudo: str | None) -> str | None:
    """Nombre de unidad. Acá los dígitos se quedan: «Cabaña 2» es el nombre entero."""
    if not crudo:
        return None
    nombre = re.split(r"[|<(]", crudo)[0].strip(" .,:;-")
    return nombre[:120] if 2 <= len(nombre) <= 120 else None


def analizar(
    *,
    asunto: str = "",
    cuerpo: str = "",
    remitente: str = "",
    mensaje_id: str | None = None,
    hoy: date | None = None,
) -> Lectura:
    """Lee el mail. Nunca levanta: lo que no entiende lo anota en `faltantes`."""
    hoy = hoy or date.today()
    texto = _a_texto(f"{asunto}\n{cuerpo}")
    lectura = Lectura()

    # De quién viene. El remitente manda sobre el cuerpo: un mail de Despegar
    # puede nombrar a Booking adentro.
    lectura.plataforma = canales.detectar(remitente)
    if lectura.plataforma == "otro":
        del_cuerpo = canales.detectar(texto)
        lectura.plataforma = del_cuerpo if del_cuerpo != "otro" else "particular"

    # Fechas: primero las etiquetadas, que son las confiables.
    entrada, salida = _tras_etiqueta(texto, ENTRADA), _tras_etiqueta(texto, SALIDA)
    if entrada:
        lectura.fecha_inicio = _fecha(entrada, hoy)
    if salida:
        lectura.fecha_fin = _fecha(salida, hoy)
    if not (lectura.fecha_inicio and lectura.fecha_fin):
        desde, hasta = _rango_en_una_linea(texto, hoy)
        lectura.fecha_inicio = lectura.fecha_inicio or desde
        lectura.fecha_fin = lectura.fecha_fin or hasta

    lectura.huesped = _limpiar_nombre(_tras_etiqueta(texto, _ETIQUETAS_HUESPED))
    lectura.codigo_externo = _limpiar_codigo(_tras_etiqueta(texto, _ETIQUETAS_CODIGO))
    lectura.unidad_nombre = _limpiar_unidad(_tras_etiqueta(texto, _ETIQUETAS_UNIDAD, largo=60))
    lectura.personas = _personas(texto)
    lectura.monto = _monto(texto)
    lectura.contacto = _contacto(texto)

    if lectura.fecha_inicio is None:
        lectura.faltantes.append("fecha de entrada")
    if lectura.fecha_fin is None:
        lectura.faltantes.append("fecha de salida")
    if (
        lectura.fecha_inicio
        and lectura.fecha_fin
        and lectura.fecha_fin <= lectura.fecha_inicio
    ):
        lectura.faltantes.append("la salida no puede ser anterior a la entrada")

    lectura.huella = mensaje_id or hashlib.sha256(
        f"{remitente}|{asunto}|{_a_texto(cuerpo).strip()}".encode()
    ).hexdigest()[:64]
    return lectura


def _limpiar_codigo(crudo: str | None) -> str | None:
    if not crudo:
        return None
    codigo = re.search(r"[A-Z0-9][A-Z0-9\-]{3,}", crudo.upper())
    return codigo.group()[:80] if codigo else None
