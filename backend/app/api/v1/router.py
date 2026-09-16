from fastapi import APIRouter

from app.api.v1 import comisiones, salud

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(salud.router)
api_router.include_router(comisiones.router)
