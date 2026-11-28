"""Calendario público de una unidad, para que lo lean Booking y Airbnb.

La URL lleva un token propio de la unidad y no pide sesión: así la tienen que
consumir esas plataformas. Por eso el archivo no dice quién reservó ni cuánto
pagó, solo qué noches están tomadas.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models import Unidad
from app.services import calendario, canales

router = APIRouter(tags=["calendario"])


@router.get(
    "/ical/{token}.ics",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}},
)
def exportar(token: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> Response:
    unidad = db.scalar(
        select(Unidad)
        .where(Unidad.ical_export_token == token)
        .options(selectinload(Unidad.publicacion))
    )
    if unidad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese calendario no existe")

    # Quién lo lee: así el anfitrión ve que pegó bien la dirección en Airbnb o
    # Booking. Una persona con el navegador (él mismo probando) no cuenta.
    lector = canales.lector(request.headers.get("user-agent"))
    if lector is not None:
        calendario.anotar_lectura(db, unidad.id, lector)
        db.commit()

    return Response(
        content=calendario.exportar(db, unidad),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{token}.ics"',
            "Cache-Control": "public, max-age=600",
        },
    )
