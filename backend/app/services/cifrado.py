"""Cifrado simétrico de secretos guardados en la base.

Hoy lo usan las credenciales de cobro de los anfitriones: con la base filtrada,
esas credenciales dejarían mover la plata de otros. Fernet (AES-128-CBC + HMAC)
autentica además de cifrar, así que un valor alterado no se descifra en silencio.

La clave sale de `CLAVE_CIFRADO`. En local, si falta, se deriva de SECRET_KEY
para que el entorno de desarrollo arranque sin configurar nada.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class SecretoIlegible(Exception):
    """El valor guardado no se puede descifrar con la clave actual."""


def _fernet() -> Fernet:
    s = get_settings()
    material = s.clave_cifrado or f"local:{s.secret_key}"
    # Fernet pide 32 bytes en base64; se derivan de la clave para aceptar
    # cualquier texto suficientemente largo.
    clave = base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest())
    return Fernet(clave)


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(cifrado: str) -> str:
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except InvalidToken as e:
        raise SecretoIlegible("No se pudo descifrar: ¿cambió CLAVE_CIFRADO?") from e
