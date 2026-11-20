"""Dependencias compartidas de la API: quién está pidiendo y qué puede hacer."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import TokenInvalido, leer_token
from app.models import Prestador, Usuario

esquema = HTTPBearer(auto_error=False)


def usuario_actual(
    credencial: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema)] = None,
    db: Session = Depends(get_db),
) -> Usuario:
    if credencial is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Hace falta ingresar")
    try:
        sujeto = leer_token(credencial.credentials)
    except TokenInvalido as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La sesión venció o no es válida") from e

    usuario = db.get(Usuario, UUID(sujeto))
    if usuario is None or not usuario.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La cuenta no está disponible")
    return usuario


def usuario_opcional(
    credencial: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema)] = None,
    db: Session = Depends(get_db),
) -> Usuario | None:
    """Para pantallas públicas que muestran algo extra si hay sesión."""
    if credencial is None:
        return None
    try:
        return usuario_actual(credencial, db)
    except HTTPException:
        return None


def con_email_verificado(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    """docs/01 §5 R1: no se puede reservar sin correo verificado."""
    if not usuario.email_verificado:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Verificá tu correo antes de seguir. Te mandamos un enlace al registrarte.",
        )
    return usuario


def operador(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if not usuario.es_operador:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esto es solo para operadores")
    return usuario


def prestador_actual(
    usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)
) -> Prestador:
    prestador = db.scalar(select(Prestador).where(Prestador.usuario_id == usuario.id))
    if prestador is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Todavía no cargaste tus datos de prestador")
    return prestador


def prestador_habilitado(prestador: Prestador = Depends(prestador_actual)) -> Prestador:
    """docs/01 §5 R1: sin datos fiscales y cuenta de cobro no se puede publicar."""
    if not prestador.puede_publicar:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Para publicar necesitás CUIT, condición frente al IVA y tu cuenta de "
            "Mercado Pago vinculada.",
        )
    return prestador
