"""Canales de correo: por consola en desarrollo, por SMTP en serio."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.models.enums import CanalNotificacion
from app.services.notificaciones.base import Canal, ErrorDeEnvio, Mensaje

registro = logging.getLogger("notificaciones")


class CorreoPorConsola(Canal):
    """Escribe el correo en el log en vez de enviarlo.

    Permite recorrer y revisar el circuito completo sin servidor de correo. Solo
    en entorno local: en cualquier otro, un correo que no sale es un correo que el
    viajero no recibe.
    """

    canal = CanalNotificacion.EMAIL
    nombre = "Correo por consola (solo desarrollo)"

    @property
    def disponible(self) -> bool:
        return get_settings().environment == "local" and not get_settings().smtp_host

    @property
    def motivo_no_disponible(self) -> str:
        return "Solo se usa en local y cuando no hay SMTP configurado."

    def enviar(self, mensaje: Mensaje) -> None:
        registro.info(
            "CORREO (no enviado, solo local)\n  Para: %s\n  Asunto: %s\n%s",
            mensaje.destino,
            mensaje.asunto,
            mensaje.cuerpo,
        )


class CorreoSMTP(Canal):
    canal = CanalNotificacion.EMAIL
    nombre = "Correo"

    @property
    def disponible(self) -> bool:
        s = get_settings()
        return bool(s.smtp_host and s.smtp_desde)

    @property
    def motivo_no_disponible(self) -> str:
        return "Faltan SMTP_HOST y SMTP_DESDE para enviar correos."

    def enviar(self, mensaje: Mensaje) -> None:
        s = get_settings()
        correo = EmailMessage()
        correo["From"] = s.smtp_desde
        correo["To"] = mensaje.destino
        correo["Subject"] = mensaje.asunto
        correo.set_content(mensaje.cuerpo)

        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_puerto, timeout=20) as servidor:
                if s.smtp_tls:
                    servidor.starttls()
                if s.smtp_usuario:
                    servidor.login(s.smtp_usuario, s.smtp_password)
                servidor.send_message(correo)
        except Exception as e:  # noqa: BLE001 - smtplib levanta varias familias
            raise ErrorDeEnvio(f"No pudimos enviar el correo: {type(e).__name__}") from e
