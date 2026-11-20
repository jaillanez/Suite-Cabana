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
import hmac

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class SecretoIlegible(Exception):
    """El valor guardado no se puede descifrar con la clave actual."""


def _material() -> str:
    s = get_settings()
    return s.clave_cifrado or f"local:{s.secret_key}"


def _fernet() -> Fernet:
    # Fernet pide 32 bytes en base64; se derivan de la clave para aceptar
    # cualquier texto suficientemente largo.
    clave = base64.urlsafe_b64encode(hashlib.sha256(_material().encode()).digest())
    return Fernet(clave)


def firmar(texto: str) -> str:
    """Firma corta de un valor que viaja en una URL nuestra (p. ej. el aviso de
    pago). Usa una clave derivada aparte: firmar no es cifrar."""
    clave = hashlib.sha256(f"firma:{_material()}".encode()).digest()
    return hmac.new(clave, texto.encode(), hashlib.sha256).hexdigest()[:32]


def firma_valida(texto: str, firma: str) -> bool:
    return hmac.compare_digest(firmar(texto), firma or "")


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(cifrado: str) -> str:
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except InvalidToken as e:
        raise SecretoIlegible("No se pudo descifrar: ¿cambió CLAVE_CIFRADO?") from e
