"""Buzón de reservas: los mails de las plataformas entran por acá (docs/01 §5 R3).

Despegar no publica iCal. Lo que sí manda, siempre, es un mail de confirmación.
El anfitrión pone una regla de reenvío hacia su dirección propia, el proveedor de
correo entrante nos postea el mensaje, y la reserva termina bloqueando la fecha
en todas las otras plataformas.

**Por qué reenvío y no leer su casilla.** La alternativa era guardar la
contraseña de su correo, o la de la extranet de Despegar y entrar a mirar. Las
dos nos convierten en un depósito de credenciales ajenas: si nos entran a la
base, se van con las cuentas de todos los anfitriones. Una regla de reenvío no
nos da acceso a nada más que a los mensajes que ellos eligen mandarnos.

**El endpoint está cerrado si no hay secreto configurado.** Un buzón abierto al
mundo deja que cualquiera te ocupe el calendario.
"""

from __future__ import annotations

import hmac
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import Prestador
from app.models.enums import OrigenReservaExterna
from app.services import reservas_externas as externas
from app.services.correo import analisis

router = APIRouter(tags=["calendario"])

#: Cada proveedor de correo entrante nombra los campos a su manera. Se prueban
#: en orden y gana el primero que traiga algo.
CAMPOS = {
    "destinatario": ("to", "To", "recipient", "OriginalRecipient"),
    "remitente": ("from", "From", "sender", "FromFull"),
    "asunto": ("subject", "Subject"),
    "cuerpo": ("text", "body-plain", "TextBody", "plain", "html", "body-html", "HtmlBody"),
    "mensaje_id": ("message-id", "Message-ID", "MessageID", "message_id"),
}


def _primero(datos: dict, claves: tuple[str, ...]) -> str:
    for clave in claves:
        valor = datos.get(clave)
        if isinstance(valor, dict):  # Postmark manda {"Email": ..., "Name": ...}
            valor = valor.get("Email") or valor.get("email")
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return ""


def direccion_de(prestador: Prestador) -> str:
    """La dirección propia del anfitrión, a la que reenvía los mails.

    El id del prestador es un UUID v4: no se adivina, y así no hace falta una
    columna nueva ni un token que administrar aparte.
    """
    dominio = get_settings().correo_entrante_dominio
    return f"reservas+{prestador.id.hex}@{dominio}" if dominio else ""


def _prestador_de(db: Session, destinatario: str) -> Prestador:
    """De `reservas+<id>@dominio` al anfitrión dueño del buzón."""
    etiqueta = re.search(r"\+([0-9a-fA-F]{32})@", destinatario)
    if not etiqueta:
        raise HTTPException(422, "Esa dirección no corresponde a ningún buzón.")
    try:
        identificador = uuid.UUID(hex=etiqueta.group(1))
    except ValueError as e:
        raise HTTPException(422, "Esa dirección no corresponde a ningún buzón.") from e
    prestador = db.get(Prestador, identificador)
    if prestador is None:
        raise HTTPException(404, "Esa dirección no corresponde a ningún buzón.")
    return prestador


def _autorizado(request: Request) -> None:
    """Secreto compartido con el proveedor. Sin él configurado, nadie entra."""
    esperado = get_settings().correo_entrante_secreto
    if not esperado:
        raise HTTPException(
            503,
            "El buzón de reservas no está configurado todavía. Mientras tanto, los mails "
            "se pegan a mano en el calendario general.",
        )
    recibido = request.headers.get("x-buzon-secreto", "")
    if not hmac.compare_digest(recibido, esperado):
        raise HTTPException(401, "Secreto inválido.")


class RecibidoOut(BaseModel):
    reserva_id: uuid.UUID
    estado: str
    nueva: bool
    detalle: str


@router.post("/correo/entrante", response_model=RecibidoOut, status_code=201)
async def recibir(
    request: Request,
    _: None = Depends(_autorizado),
    db: Session = Depends(get_db),
) -> RecibidoOut:
    """Recibe un mail reenviado y lo convierte en reserva.

    Acepta JSON o formulario: cada proveedor postea a su manera y no vale la pena
    atarse a uno. Si el mensaje no se entiende del todo, la reserva queda
    esperando revisión en el panel: nunca bloquea fechas adivinadas.
    """
    if request.headers.get("content-type", "").startswith("application/json"):
        datos = await request.json()
    else:
        datos = dict(await request.form())
    if not isinstance(datos, dict):
        raise HTTPException(422, "No entendimos el cuerpo del mensaje.")

    destinatario = _primero(datos, CAMPOS["destinatario"])
    cuerpo = _primero(datos, CAMPOS["cuerpo"])
    if not cuerpo:
        raise HTTPException(422, "El mensaje vino vacío.")

    prestador = _prestador_de(db, destinatario)
    lectura = analisis.analizar(
        asunto=_primero(datos, CAMPOS["asunto"]),
        cuerpo=cuerpo,
        remitente=_primero(datos, CAMPOS["remitente"]),
        mensaje_id=_primero(datos, CAMPOS["mensaje_id"]) or None,
    )
    unidades = externas.unidades_de(db, prestador.id)
    unidad = externas.adivinar_unidad(lectura.unidad_nombre, unidades)
    try:
        resultado = externas.registrar(
            db,
            prestador.id,
            unidad,
            lectura,
            origen=OrigenReservaExterna.CORREO,
            mensaje={"destinatario": destinatario, "cuerpo": cuerpo[:20_000]},
        )
    except externas.FechasOcupadas as e:
        # 409 y no 500: el proveedor no tiene que reintentar esto eternamente.
        raise HTTPException(409, str(e)) from e
    db.commit()
    return RecibidoOut(
        reserva_id=resultado.reserva.id,
        estado=resultado.reserva.estado.value,
        nueva=resultado.nueva,
        detalle=resultado.detalle,
    )
