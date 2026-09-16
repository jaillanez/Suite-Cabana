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


def crear_token(sujeto: str) -> str:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(minutes=s.access_token_minutes)
    return jwt.encode({"sub": sujeto, "exp": exp}, s.secret_key, algorithm=ALGORITMO)


def leer_token(token: str) -> str:
    return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITMO])["sub"]
