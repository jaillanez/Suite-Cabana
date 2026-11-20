"""Verificación del token de identidad de Google (docs/01 §5 R1).

Google devuelve al navegador un JWT firmado con RS256. Verificarlo de verdad
—firma contra las claves públicas de Google, destinatario, emisor y vencimiento—
es lo único que impide que cualquiera mande un token armado a mano y entre como
quien quiera. Decodificarlo sin verificar sería dejar la puerta abierta.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

CERTIFICADOS = "https://www.googleapis.com/oauth2/v3/certs"
EMISORES = ("accounts.google.com", "https://accounts.google.com")

# El cliente cachea las claves de Google en memoria y las renueva solo.
_claves = PyJWKClient(CERTIFICADOS, cache_keys=True)


class TokenGoogleInvalido(Exception):
    """El token no vino de Google, no es para esta aplicación, o venció."""


@dataclass(frozen=True)
class IdentidadGoogle:
    sub: str
    email: str
    email_verificado: bool
    nombre: str
    apellido: str


def verificar(credencial: str, client_id: str) -> IdentidadGoogle:
    try:
        clave = _claves.get_signing_key_from_jwt(credencial)
        datos = jwt.decode(
            credencial,
            clave.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=list(EMISORES),
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except Exception as e:  # noqa: BLE001 - jwt y urllib levantan de todo
        raise TokenGoogleInvalido(str(e)) from e

    email = (datos.get("email") or "").lower().strip()
    if not email:
        raise TokenGoogleInvalido("el token no trae correo")

    return IdentidadGoogle(
        sub=str(datos["sub"]),
        email=email,
        email_verificado=bool(datos.get("email_verified")),
        nombre=(datos.get("given_name") or datos.get("name") or email.split("@")[0]).strip(),
        apellido=(datos.get("family_name") or "").strip(),
    )
