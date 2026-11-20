from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_hasher = PasswordHash.recommended()
ALGORITMO = "HS256"


def hashear_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(password: str, hash_: str) -> bool:
    return _hasher.verify(password, hash_)


class TokenInvalido(Exception):
    """El token no es válido, venció, o no es del tipo esperado."""


def crear_token(sujeto: str, tipo: str = "acceso", minutos: int | None = None) -> str:
    """Token firmado. El `tipo` evita que un token de verificación sirva para entrar."""
    s = get_settings()
    duracion = minutos if minutos is not None else s.access_token_minutes
    ahora = datetime.now(UTC)
    return jwt.encode(
        {"sub": sujeto, "tipo": tipo, "iat": ahora, "exp": ahora + timedelta(minutes=duracion)},
        s.secret_key,
        algorithm=ALGORITMO,
    )


def leer_token(token: str, tipo: str = "acceso") -> str:
    try:
        datos = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITMO])
    except jwt.PyJWTError as e:
        raise TokenInvalido(str(e)) from e
    if datos.get("tipo") != tipo:
        raise TokenInvalido(f"se esperaba un token de {tipo}")
    return datos["sub"]
