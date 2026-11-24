from fastapi import APIRouter

from app.api.v1 import (
    admin,
    agenda,
    auth,
    comisiones,
    correo,
    excursiones,
    ical,
    mis_excursiones,
    mis_publicaciones,
    panel,
    publicaciones,
    reservas,
    salones,
    salud,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(salud.router)
api_router.include_router(auth.router)
api_router.include_router(comisiones.router)
api_router.include_router(publicaciones.router)
api_router.include_router(mis_publicaciones.router)
api_router.include_router(mis_excursiones.router)
api_router.include_router(admin.router)
api_router.include_router(ical.router)
api_router.include_router(agenda.router)
api_router.include_router(correo.router)
api_router.include_router(reservas.router)
api_router.include_router(salones.router)
api_router.include_router(excursiones.router)
api_router.include_router(panel.router)
