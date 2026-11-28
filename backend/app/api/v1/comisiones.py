"""Comisiones para el operador (docs/00 §7.4): las reglas por tipo y subtipo de
servicio, provincia, localidad y temporada; su historial; y el simulador.

Cambiar una regla nunca toca las reservas hechas: cada una guardó su
`ComisionAplicada` con la regla y los montos de ese momento (CLAUDE.md §4).
Todo es solo para operadores: las condiciones comerciales no son públicas.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import operador
from app.core.config import get_settings
from app.core.database import get_db
from app.models import (
    ComisionAplicada,
    Localidad,
    Provincia,
    ReglaComision,
    ReglaComisionHistorial,
    SubtipoServicio,
    TipoServicio,
    Usuario,
)
from app.models.enums import QuienPaga
from app.services import comisiones as motor

router = APIRouter(prefix="/comisiones", tags=["comisiones"])

Porcentaje = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Monto = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]

#: Lo que el panel deja editar. Las demás dimensiones del motor (zona, prestador,
#: publicación, monto, antigüedad, categoría, fecha de creación) siguen
#: existiendo y se respetan, pero todavía no se cargan desde acá.
DIMENSIONES = ("tipo_servicio_id", "subtipo_servicio_id", "provincia_id", "localidad_id",
               "servicio_desde", "servicio_hasta")
VALORES = ("nombre", "descripcion", "prioridad", "vigente_desde", "vigente_hasta",
           "porcentaje", "monto_fijo", "minimo", "maximo", "quien_paga",
           "porcentaje_viajero", "iva_incluido")


# --- Formas ---


class ReglaIn(BaseModel):
    nombre: Annotated[str, Field(min_length=3, max_length=120)]
    descripcion: Annotated[str | None, Field(default=None, max_length=500)] = None
    prioridad: Annotated[int, Field(ge=0, le=1000)] = 0
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    tipo_servicio_id: UUID | None = None
    subtipo_servicio_id: UUID | None = None
    provincia_id: UUID | None = None
    localidad_id: UUID | None = None
    servicio_desde: date | None = Field(default=None, description="Temporada: desde")
    servicio_hasta: date | None = None
    porcentaje: Porcentaje = Decimal(0)
    monto_fijo: Monto = Decimal(0)
    minimo: Monto | None = None
    maximo: Monto | None = None
    quien_paga: QuienPaga = QuienPaga.PRESTADOR
    porcentaje_viajero: Porcentaje = Decimal(0)
    iva_incluido: bool = False

    @model_validator(mode="after")
    def _coherente(self) -> ReglaIn:
        for desde, hasta, que in (
            (self.vigente_desde, self.vigente_hasta, "La vigencia"),
            (self.servicio_desde, self.servicio_hasta, "La temporada"),
        ):
            if desde and hasta and hasta < desde:
                raise ValueError(f"{que} termina antes de empezar")
        if self.minimo is not None and self.maximo is not None and self.maximo < self.minimo:
            raise ValueError("El máximo no puede ser menor que el mínimo")
        if self.quien_paga is QuienPaga.DIVIDIDO and not 0 < self.porcentaje_viajero < 100:
            raise ValueError("Dividida: decí qué parte paga el viajero, entre 1 y 99 %")
        return self


class ReglaOut(BaseModel):
    id: UUID
    nombre: str
    descripcion: str | None
    activa: bool
    es_default: bool
    prioridad: int
    vigente_desde: date | None
    vigente_hasta: date | None
    tipo_servicio_id: UUID | None
    tipo_servicio: str | None
    subtipo_servicio_id: UUID | None
    subtipo_servicio: str | None
    provincia_id: UUID | None
    provincia: str | None
    localidad_id: UUID | None
    localidad: str | None
    servicio_desde: date | None
    servicio_hasta: date | None
    porcentaje: Decimal
    monto_fijo: Decimal
    minimo: Decimal | None
    maximo: Decimal | None
    quien_paga: QuienPaga
    porcentaje_viajero: Decimal
    iva_incluido: bool
    otras_condiciones: bool = Field(
        description="Tiene dimensiones que este panel no edita (prestador, zona, monto…)"
    )
    reservas: int = Field(description="Ítems de reserva que la usaron")


class HistorialOut(BaseModel):
    accion: str
    usuario: str | None
    fecha: str
    antes: dict | None
    despues: dict | None


class CatalogoComisiones(BaseModel):
    tipos: list[dict]
    provincias: list[dict]


class CasoSimulacion(BaseModel):
    monto: Monto
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


# --- Ayudantes ---


def _foto(r: ReglaComision) -> dict:
    """La regla como quedó, para el historial."""
    campos = (*DIMENSIONES, *VALORES, "activa")
    return {
        k: (str(v) if v is not None and not isinstance(v, (bool, int)) else v)
        for k in campos
        for v in [getattr(r, k)]
    }


def _historial(db: Session, r: ReglaComision, usuario: Usuario, accion: str, antes) -> None:
    db.add(
        ReglaComisionHistorial(
            regla_id=r.id, usuario_id=usuario.id, accion=accion, antes=antes,
            despues=_foto(r),
        )
    )


def _validar_dimensiones(db: Session, d: ReglaIn) -> None:
    """Que lo elegido exista y sea coherente: una regla con "Excursión" y
    "Quincho" nunca coincidiría con nada y nadie se daría cuenta."""
    if d.tipo_servicio_id and db.get(TipoServicio, d.tipo_servicio_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ese tipo de servicio no existe")
    if d.subtipo_servicio_id:
        sub = db.get(SubtipoServicio, d.subtipo_servicio_id)
        if sub is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ese subtipo no existe")
        if d.tipo_servicio_id and sub.tipo_id != d.tipo_servicio_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Ese subtipo no es de ese tipo de servicio"
            )
    if d.provincia_id and db.get(Provincia, d.provincia_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Esa provincia no existe")
    if d.localidad_id:
        loc = db.get(Localidad, d.localidad_id)
        if loc is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Esa localidad no existe")
        if d.provincia_id and loc.provincia_id != d.provincia_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Esa localidad no es de esa provincia"
            )


def _sin_dimensiones(d: ReglaIn) -> bool:
    return all(getattr(d, k) is None for k in DIMENSIONES)


def _otras(r: ReglaComision) -> bool:
    return any(
        getattr(r, k) is not None
        for k in ("zona_id", "prestador_id", "publicacion_id", "creacion_desde", "creacion_hasta",
                  "monto_desde", "monto_hasta", "antiguedad_meses_desde",
                  "antiguedad_meses_hasta", "categoria_prestador")
    )


def _salida(db: Session, reglas: list[ReglaComision]) -> list[ReglaOut]:
    usos = dict(
        db.execute(
            select(ComisionAplicada.regla_id, func.count())
            .where(ComisionAplicada.regla_id.in_([r.id for r in reglas]))
            .group_by(ComisionAplicada.regla_id)
        ).all()
    )
    nombres: dict = {}
    for modelo, campo in ((TipoServicio, "nombre"), (SubtipoServicio, "nombre"),
                          (Provincia, "nombre"), (Localidad, "nombre")):
        nombres.update(dict(db.execute(select(modelo.id, getattr(modelo, campo))).all()))

    def nombre(i):
        return nombres.get(i) if i else None

    return [
        ReglaOut(
            id=r.id, nombre=r.nombre, descripcion=r.descripcion, activa=r.activa,
            es_default=r.es_default, prioridad=r.prioridad, vigente_desde=r.vigente_desde,
            vigente_hasta=r.vigente_hasta,
            tipo_servicio_id=r.tipo_servicio_id, tipo_servicio=nombre(r.tipo_servicio_id),
            subtipo_servicio_id=r.subtipo_servicio_id,
            subtipo_servicio=nombre(r.subtipo_servicio_id),
            provincia_id=r.provincia_id, provincia=nombre(r.provincia_id),
            localidad_id=r.localidad_id, localidad=nombre(r.localidad_id),
            servicio_desde=r.servicio_desde, servicio_hasta=r.servicio_hasta,
            porcentaje=r.porcentaje, monto_fijo=r.monto_fijo, minimo=r.minimo, maximo=r.maximo,
            quien_paga=r.quien_paga, porcentaje_viajero=r.porcentaje_viajero,
            iva_incluido=r.iva_incluido, otras_condiciones=_otras(r),
            reservas=usos.get(r.id, 0),
        )
        for r in reglas
    ]


def _regla(db: Session, regla_id: UUID) -> ReglaComision:
    r = db.get(ReglaComision, regla_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa regla")
    return r


# --- Reglas ---


@router.get("/reglas", response_model=list[ReglaOut])
def listar(
    _: Usuario = Depends(operador), db: Session = Depends(get_db)
) -> list[ReglaOut]:
    """Todas las reglas: la general primero, después las activas por nombre."""
    reglas = db.scalars(
        select(ReglaComision).order_by(
            ReglaComision.es_default.desc(), ReglaComision.activa.desc(), ReglaComision.nombre
        )
    ).all()
    return _salida(db, list(reglas))


@router.post("/reglas", response_model=ReglaOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: ReglaIn, usuario: Usuario = Depends(operador), db: Session = Depends(get_db)
) -> ReglaOut:
    if _sin_dimensiones(datos):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Una regla nueva necesita al menos un tipo, una zona o una temporada: sin "
            "ninguna es la regla general, que ya existe. Editala a ella.",
        )
    _validar_dimensiones(db, datos)
    r = ReglaComision(**datos.model_dump(), creado_por_id=usuario.id)
    db.add(r)
    db.flush()
    _historial(db, r, usuario, "alta", None)
    db.commit()
    return _salida(db, [r])[0]


@router.put("/reglas/{regla_id}", response_model=ReglaOut)
def editar(
    regla_id: UUID,
    datos: ReglaIn,
    usuario: Usuario = Depends(operador),
    db: Session = Depends(get_db),
) -> ReglaOut:
    """Reemplaza la regla. Las reservas ya hechas no cambian: guardaron la suya."""
    r = _regla(db, regla_id)
    if r.es_default and not _sin_dimensiones(datos):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "La regla general no lleva tipo, zona ni temporada: es la que aplica cuando "
            "ninguna otra coincide. Para un caso particular, creá una regla nueva.",
        )
    if not r.es_default and _sin_dimensiones(datos) and not _otras(r):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Sin tipo, zona ni temporada sería otra regla general. Dejale al menos una.",
        )
    _validar_dimensiones(db, datos)
    antes = _foto(r)
    for campo, valor in datos.model_dump().items():
        setattr(r, campo, valor)
    _historial(db, r, usuario, "edicion", antes)
    db.commit()
    return _salida(db, [r])[0]


def _activar(db: Session, regla_id: UUID, usuario: Usuario, activa: bool) -> ReglaOut:
    r = _regla(db, regla_id)
    if r.es_default and not activa:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La regla general no se desactiva: sin ella hay reservas sin comisión posible.",
        )
    if r.activa != activa:
        antes = _foto(r)
        r.activa = activa
        _historial(db, r, usuario, "alta" if activa else "baja", antes)
        db.commit()
    return _salida(db, [r])[0]


@router.post("/reglas/{regla_id}/desactivar", response_model=ReglaOut)
def desactivar(
    regla_id: UUID, usuario: Usuario = Depends(operador), db: Session = Depends(get_db)
) -> ReglaOut:
    return _activar(db, regla_id, usuario, False)


@router.post("/reglas/{regla_id}/activar", response_model=ReglaOut)
def activar(
    regla_id: UUID, usuario: Usuario = Depends(operador), db: Session = Depends(get_db)
) -> ReglaOut:
    return _activar(db, regla_id, usuario, True)


@router.get("/reglas/{regla_id}/historial", response_model=list[HistorialOut])
def historial(
    regla_id: UUID, _: Usuario = Depends(operador), db: Session = Depends(get_db)
) -> list[HistorialOut]:
    _regla(db, regla_id)
    filas = db.execute(
        select(ReglaComisionHistorial, Usuario.email)
        .outerjoin(Usuario, ReglaComisionHistorial.usuario_id == Usuario.id)
        .where(ReglaComisionHistorial.regla_id == regla_id)
        .order_by(ReglaComisionHistorial.fecha.desc())
    ).all()
    return [
        HistorialOut(
            accion=h.accion, usuario=email, fecha=h.fecha.isoformat(), antes=h.antes,
            despues=h.despues,
        )
        for h, email in filas
    ]


@router.get("/catalogo", response_model=CatalogoComisiones)
def catalogo(
    _: Usuario = Depends(operador), db: Session = Depends(get_db)
) -> CatalogoComisiones:
    """Lo que el formulario necesita elegir: tipos con sus subtipos, provincias con
    sus localidades."""
    tipos = db.scalars(select(TipoServicio).order_by(TipoServicio.nombre)).all()
    subtipos = db.scalars(select(SubtipoServicio).order_by(SubtipoServicio.nombre)).all()
    provincias = db.scalars(select(Provincia).order_by(Provincia.nombre)).all()
    localidades = db.scalars(select(Localidad).order_by(Localidad.nombre)).all()
    return CatalogoComisiones(
        tipos=[
            {
                "id": str(t.id), "nombre": t.nombre,
                "subtipos": [
                    {"id": str(s.id), "nombre": s.nombre} for s in subtipos if s.tipo_id == t.id
                ],
            }
            for t in tipos
        ],
        provincias=[
            {
                "id": str(p.id), "nombre": p.nombre,
                "localidades": [
                    {"id": str(x.id), "nombre": x.nombre}
                    for x in localidades
                    if x.provincia_id == p.id
                ],
            }
            for p in provincias
        ],
    )


# --- Simulador ---


@router.post("/simular", response_model=ResultadoSimulacion)
def simular(
    caso: CasoSimulacion, _: Usuario = Depends(operador), db: Session = Depends(get_db)
) -> ResultadoSimulacion:
    """Qué regla aplicaría a un caso y por qué. Solo operadores: la explicación
    nombra todas las reglas, y las condiciones comerciales no son públicas."""
    datos = caso.model_dump()
    datos["fecha_creacion"] = datos["fecha_creacion"] or date.today()
    if caso.subtipo_servicio_id and not caso.tipo_servicio_id:
        sub = db.get(SubtipoServicio, caso.subtipo_servicio_id)
        datos["tipo_servicio_id"] = sub.tipo_id if sub else None
    if caso.localidad_id and not caso.provincia_id:
        loc = db.get(Localidad, caso.localidad_id)
        datos["provincia_id"] = loc.provincia_id if loc else None
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
