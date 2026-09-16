from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import ReglaComision
from app.services import comisiones as motor

router = APIRouter(prefix="/comisiones", tags=["comisiones"])


class CasoSimulacion(BaseModel):
    monto: Decimal
    fecha_servicio: date
    fecha_creacion: date | None = None
    tipo_servicio_id: UUID | None = None
    subtipo_servicio_id: UUID | None = None
    provincia_id: UUID | None = None
    localidad_id: UUID | None = None
    zona_id: UUID | None = None
    prestador_id: UUID | None = None
    publicacion_id: UUID | None = None
    antiguedad_prestador_meses: int | None = None
    categoria_prestador: str | None = None


class ResultadoSimulacion(BaseModel):
    regla_id: UUID
    regla_nombre: str
    base: Decimal
    comision_neta: Decimal
    iva: Decimal
    comision_total: Decimal
    cargo_viajero: Decimal
    descuento_prestador: Decimal
    total_viajero: Decimal
    neto_prestador: Decimal
    explicacion: list[str]


# TODO: restringir a operadores cuando exista la autenticación.
@router.post("/simular", response_model=ResultadoSimulacion)
def simular(caso: CasoSimulacion, db: Session = Depends(get_db)) -> ResultadoSimulacion:
    datos = caso.model_dump()
    datos["fecha_creacion"] = datos["fecha_creacion"] or date.today()
    ctx = motor.ContextoComision(**datos)
    reglas = [motor.regla_desde_modelo(m) for m in db.scalars(select(ReglaComision))]
    try:
        r = motor.resolver(reglas, ctx, get_settings().iva_comision)
    except motor.SinReglaAplicable as e:
        raise HTTPException(409, str(e)) from e
    return ResultadoSimulacion(
        regla_id=r.regla.id,
        regla_nombre=r.regla.nombre,
        base=r.base,
        comision_neta=r.comision_neta,
        iva=r.iva,
        comision_total=r.comision_total,
        cargo_viajero=r.cargo_viajero,
        descuento_prestador=r.descuento_prestador,
        total_viajero=r.total_viajero,
        neto_prestador=r.neto_prestador,
        explicacion=r.explicacion,
    )
