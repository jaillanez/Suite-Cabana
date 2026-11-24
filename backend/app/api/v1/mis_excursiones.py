"""Excursiones del prestador (docs/05, etapa 3): turnos, precios por pasajero y el
panel de salidas con sus anotados.

Vive bajo `/mis-publicaciones/{id}/unidades/{unidad}` como el resto del editor.
Turnos y precios devuelven la publicación entera (lo que pinta el editor); las
acciones sobre una salida devuelven esa salida como la ve el panel.

Una salida se elige por `salida_id` si ya está guardada, o por `turno_id` y
`fecha` si todavía es solo el cálculo del turno: en ese caso se guarda en el
momento (`salidas.materializar`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import prestador_actual
from app.api.v1.mis_publicaciones import Dinero, PublicacionOut, _mia, _respuesta, _unidad_de
from app.core.database import get_db
from app.models import (
    CupoTomado,
    ItemReserva,
    PrecioPasajero,
    Prestador,
    Reserva,
    SalidaExcursion,
    TurnoExcursion,
    Unidad,
    Usuario,
)
from app.models.enums import ModoReserva, OrigenBloqueo
from app.models.excursion import DURACION_MAXIMA_MINUTOS
from app.services import reservas_excursion as rx
from app.services import salidas
from app.services.privacidad import ESTADOS_CON_DIRECCION

router = APIRouter(prefix="/mis-publicaciones", tags=["mis excursiones"])

DIAS_POR_CONSULTA = 62
MAX_PRECIOS = 10
MAX_TURNOS = 20
#: Salidas especiales por venir, por actividad: más que esto es un turno.
MAX_SALIDAS_ESPECIALES = 60


# --- Formas ---


class NuevoTurno(BaseModel):
    nombre: Annotated[str, Field(min_length=1, max_length=80)]
    dias_semana: list[Annotated[int, Field(ge=0, le=6)]] = Field(min_length=1, max_length=7)
    hora_inicio: time
    duracion_minutos: Annotated[int, Field(ge=15, le=DURACION_MAXIMA_MINUTOS)]
    cupo: Annotated[int, Field(ge=1, le=salidas.CUPO_MAXIMO)]
    desde: date | None = None
    hasta: date | None = None
    minimo_personas: Annotated[int, Field(ge=1, le=salidas.CUPO_MAXIMO)] = 1
    aviso_minimo_horas: Annotated[int, Field(ge=0, le=salidas.AVISO_MAXIMO_HORAS)] = 24


class NuevoPrecioPasajero(BaseModel):
    nombre: Annotated[str, Field(min_length=1, max_length=60)]
    descripcion: Annotated[str | None, Field(default=None, max_length=200)] = None
    edad_desde: Annotated[int | None, Field(default=None, ge=0, le=120)] = None
    edad_hasta: Annotated[int | None, Field(default=None, ge=0, le=120)] = None
    # Puede ser 0 (menores gratis), a diferencia de una tarifa.
    precio: Annotated[
        Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
    ]
    ocupa_lugar: bool = True

    @model_validator(mode="after")
    def _edades(self) -> NuevoPrecioPasajero:
        if (
            self.edad_desde is not None
            and self.edad_hasta is not None
            and self.edad_hasta < self.edad_desde
        ):
            raise ValueError("La edad hasta no puede ser menor que la edad desde")
        return self


class Eleccion(BaseModel):
    """Qué salida: la guardada (`salida_id`) o la de un turno ese día."""

    fecha: date
    turno_id: uuid.UUID | None = None
    salida_id: uuid.UUID | None = None


class Suspension(Eleccion):
    motivo: Annotated[str, Field(min_length=3, max_length=200)]


class CambioCupo(Eleccion):
    cupo: Annotated[int, Field(ge=1, le=salidas.CUPO_MAXIMO)]


class Anotacion(Eleccion):
    personas: Annotated[int, Field(ge=1, le=salidas.CUPO_MAXIMO)]
    nota: Annotated[str | None, Field(default=None, max_length=200)] = None


class NuevaSalidaEspecial(BaseModel):
    fecha: date
    hora_inicio: time
    duracion_minutos: Annotated[int, Field(ge=15, le=DURACION_MAXIMA_MINUTOS)]
    cupo: Annotated[int, Field(ge=1, le=salidas.CUPO_MAXIMO)]
    nombre: Annotated[str | None, Field(default=None, max_length=200)] = None
    minimo_personas: Annotated[int, Field(ge=1, le=salidas.CUPO_MAXIMO)] = 1
    aviso_minimo_horas: Annotated[int, Field(ge=0, le=salidas.AVISO_MAXIMO_HORAS)] = 24


class AnotadoOut(BaseModel):
    id: uuid.UUID
    personas: int
    origen: OrigenBloqueo
    nota: str | None
    reserva: str | None = Field(description="Código, si es una reserva nuestra")
    viajero: str | None
    estado_reserva: str | None
    vence_en: datetime | None


class SalidaPanelOut(BaseModel):
    turno_id: uuid.UUID | None
    salida_id: uuid.UUID | None
    fecha: date
    nombre: str
    inicio: datetime
    fin: datetime
    cupo: int
    libres: int
    ocupados: int
    suspendida: bool
    motivo: str | None
    minimo_personas: int
    sale_confirmada: bool
    anotados: list[AnotadoOut]


class SuspensionOut(BaseModel):
    salida: SalidaPanelOut
    reservas_canceladas: int
    a_devolver: Dinero


# --- Ayudantes ---


def _excursion(db: Session, publicacion_id, unidad_id, prestador, editable: bool):
    p = _mia(publicacion_id, prestador, db, editable=editable)
    if p.tipo_servicio.modo_reserva is not ModoReserva.TURNO_CUPO:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esto es para excursiones: turnos, cupo y salidas"
        )
    return p, _unidad_de(db, p, unidad_id)


def _invalida(e: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


def _fila(db: Session, unidad: Unidad, e: Eleccion) -> SalidaExcursion:
    """La salida elegida, de esta unidad; la guarda si todavía era solo del turno."""
    if (e.turno_id is None) == (e.salida_id is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elegí una salida")
    if e.salida_id:
        fila = db.get(SalidaExcursion, e.salida_id)
        if fila is None or fila.unidad_id != unidad.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa salida")
        return fila
    turno = db.get(TurnoExcursion, e.turno_id)
    if turno is None or turno.unidad_id != unidad.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese turno")
    try:
        return salidas.materializar(db, turno, e.fecha)
    except salidas.SalidaInvalida as err:
        raise _invalida(err) from err


def _anotados(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[AnotadoOut]]:
    """Quién ocupa cada salida. El nombre del viajero solo con la reserva confirmada,
    como el WhatsApp: antes no hay nada que coordinar con él."""
    if not ids:
        return {}
    filas = db.execute(
        select(CupoTomado, Reserva, Usuario)
        .outerjoin(ItemReserva, CupoTomado.item_reserva_id == ItemReserva.id)
        .outerjoin(Reserva, ItemReserva.reserva_id == Reserva.id)
        .outerjoin(Usuario, Usuario.id == Reserva.usuario_id)
        .where(CupoTomado.salida_id.in_(ids), CupoTomado.activo.is_(True))
        .order_by(CupoTomado.creado_en)
    ).all()
    por_salida: dict[uuid.UUID, list[AnotadoOut]] = {}
    for tomado, reserva, usuario in filas:
        confirmada = reserva is not None and reserva.estado in ESTADOS_CON_DIRECCION
        por_salida.setdefault(tomado.salida_id, []).append(
            AnotadoOut(
                id=tomado.id,
                personas=tomado.personas,
                origen=tomado.origen,
                nota=tomado.nota,
                reserva=reserva.codigo if reserva else None,
                viajero=usuario.nombre if confirmada and usuario else None,
                estado_reserva=reserva.estado.value if reserva else None,
                vence_en=tomado.vence_en,
            )
        )
    return por_salida


def _panel(
    db: Session, unidad: Unidad, desde: date, hasta: date, ahora: datetime | None = None
) -> list[SalidaPanelOut]:
    lista = salidas.salidas(db, unidad, desde, hasta, ahora=ahora, con_suspendidas=True)
    ids = [s.salida_id for s in lista if s.salida_id]
    filas = {
        f.id: f for f in db.scalars(select(SalidaExcursion).where(SalidaExcursion.id.in_(ids)))
    }
    anotados = _anotados(db, ids)
    resultado = []
    for s in lista:
        fila = filas.get(s.salida_id)
        libres = max(s.libres, 0)
        resultado.append(
            SalidaPanelOut(
                turno_id=s.turno_id,
                salida_id=s.salida_id,
                fecha=s.fecha,
                nombre=s.nombre,
                inicio=s.inicio,
                fin=s.fin,
                cupo=s.cupo,
                libres=libres,
                ocupados=s.cupo - libres,
                suspendida=s.suspendida,
                motivo=fila.motivo if fila else None,
                minimo_personas=s.minimo_personas,
                sale_confirmada=bool(fila and fila.sale_confirmada),
                anotados=anotados.get(s.salida_id, []),
            )
        )
    return resultado


def _una(db: Session, unidad: Unidad, fila: SalidaExcursion) -> SalidaPanelOut:
    db.flush()
    for s in _panel(db, unidad, fila.fecha, fila.fecha):
        if s.salida_id == fila.id:
            return s
    raise HTTPException(status.HTTP_409_CONFLICT, "Esa salida ya pasó")


# --- Turnos y precios ---


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/turnos",
    response_model=PublicacionOut,
    status_code=201,
)
def crear_turno(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: NuevoTurno,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    _, unidad = _excursion(db, publicacion_id, unidad_id, prestador, editable=True)
    cantidad = len(
        db.scalars(
            select(TurnoExcursion.id).where(
                TurnoExcursion.unidad_id == unidad.id, TurnoExcursion.activo.is_(True)
            )
        ).all()
    )
    if cantidad >= MAX_TURNOS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Hasta {MAX_TURNOS} turnos por actividad")
    try:
        salidas.crear_turno(db, unidad, **datos.model_dump())
    except salidas.SalidaInvalida as e:
        raise _invalida(e) from e
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.delete(
    "/{publicacion_id}/unidades/{unidad_id}/turnos/{turno_id}", response_model=PublicacionOut
)
def quitar_turno(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    turno_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    """Deja de generar salidas. Las ya guardadas —con gente anotada— siguen."""
    _, unidad = _excursion(db, publicacion_id, unidad_id, prestador, editable=True)
    turno = db.get(TurnoExcursion, turno_id)
    if turno is None or turno.unidad_id != unidad.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese turno")
    turno.activo = False
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/precios-pasajero",
    response_model=PublicacionOut,
    status_code=201,
)
def crear_precio(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: NuevoPrecioPasajero,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    _, unidad = _excursion(db, publicacion_id, unidad_id, prestador, editable=True)
    activos = db.scalars(
        select(PrecioPasajero).where(
            PrecioPasajero.unidad_id == unidad.id, PrecioPasajero.activo.is_(True)
        )
    ).all()
    if len(activos) >= MAX_PRECIOS:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Hasta {MAX_PRECIOS} tipos de pasajero por actividad"
        )
    if any(a.nombre.casefold() == datos.nombre.strip().casefold() for a in activos):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay un precio con ese nombre")
    db.add(
        PrecioPasajero(
            unidad_id=unidad.id,
            **{**datos.model_dump(), "nombre": datos.nombre.strip()},
            orden=max((a.orden for a in activos), default=-1) + 1,
        )
    )
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.delete(
    "/{publicacion_id}/unidades/{unidad_id}/precios-pasajero/{precio_id}",
    response_model=PublicacionOut,
)
def quitar_precio(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    precio_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    """Deja de ofrecerse. Las reservas guardan su precio en el desglose: no cambian."""
    _, unidad = _excursion(db, publicacion_id, unidad_id, prestador, editable=True)
    precio = db.get(PrecioPasajero, precio_id)
    if precio is None or precio.unidad_id != unidad.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese precio")
    precio.activo = False
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


# --- Panel de salidas ---


@router.get(
    "/{publicacion_id}/unidades/{unidad_id}/salidas", response_model=list[SalidaPanelOut]
)
def ver_salidas(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    desde: Annotated[date | None, Query()] = None,
    hasta: Annotated[date | None, Query()] = None,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> list[SalidaPanelOut]:
    """Las próximas salidas con su ocupación y quién va, suspendidas incluidas."""
    _, unidad = _excursion(db, publicacion_id, unidad_id, prestador, editable=False)
    desde = desde or salidas.hoy()
    hasta = hasta or desde + timedelta(days=30)
    if hasta < desde or (hasta - desde).days > DIAS_POR_CONSULTA:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Pedí hasta {DIAS_POR_CONSULTA} días de salidas por vez",
        )
    return _panel(db, unidad, desde, hasta)


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/salidas",
    response_model=SalidaPanelOut,
    status_code=201,
)
def agregar_salida(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: NuevaSalidaEspecial,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> SalidaPanelOut:
    """Una salida especial, fuera de los turnos."""
    _, unidad = _excursion(db, publicacion_id, unidad_id, prestador, editable=False)
    especiales = db.scalars(
        select(SalidaExcursion.id).where(
            SalidaExcursion.unidad_id == unidad.id,
            SalidaExcursion.turno_id.is_(None),
            SalidaExcursion.fecha >= salidas.hoy(),
        )
    ).all()
    if len(especiales) >= MAX_SALIDAS_ESPECIALES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Hasta {MAX_SALIDAS_ESPECIALES} salidas especiales por venir: "
            "si se repiten, cargalas como turno",
        )
    try:
        fila = salidas.agregar_salida(db, unidad, **datos.model_dump())
    except salidas.SalidaInvalida as e:
        raise _invalida(e) from e
    salida = _una(db, unidad, fila)
    db.commit()
    return salida


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/salidas/suspender", response_model=SuspensionOut
)
def suspender(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: Suspension,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> SuspensionOut:
    """No sale ese día. Si hay reservas, se cancelan con el reintegro que eligió el
    prestador (`reintegro_si_no_sale`) y se les avisa."""
    _, unidad = _excursion(db, publicacion_id, unidad_id, prestador, editable=False)
    fila = _fila(db, unidad, datos)
    if fila.inicio_en <= datetime.now(UTC):
        raise HTTPException(status.HTTP_409_CONFLICT, "Esa salida ya salió")
    canceladas = rx.no_sale(db, fila, datos.motivo.strip())
    salida = _una(db, unidad, fila)
    db.commit()
    return SuspensionOut(
        salida=salida,
        reservas_canceladas=len(canceladas),
        a_devolver=sum((r.monto for _, r in canceladas), Decimal(0)),
    )


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/salidas/reanudar", response_model=SalidaPanelOut
)
def reanudar(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: Eleccion,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> SalidaPanelOut:
    """Vuelve a venderse. Las reservas que se cancelaron al suspenderla no vuelven."""
    _, unidad = _excursion(db, publicacion_id, unidad_id, prestador, editable=False)
    fila = salidas.reanudar(db, _fila(db, unidad, datos))
    salida = _una(db, unidad, fila)
    db.commit()
    return salida


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/salidas/cupo", response_model=SalidaPanelOut
)
def cambiar_cupo(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: CambioCupo,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> SalidaPanelOut:
    _, unidad = _excursion(db, publicacion_id, unidad_id, prestador, editable=False)
    fila = _fila(db, unidad, datos)
    if datos.cupo < fila.minimo_personas:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"El cupo no puede ser menor que el mínimo ({fila.minimo_personas})",
        )
    try:
        fila = salidas.cambiar_cupo(db, fila, datos.cupo)
    except salidas.SalidaInvalida as e:
        raise _invalida(e) from e
    salida = _una(db, unidad, fila)
    db.commit()
    return salida


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/salidas/anotar", response_model=SalidaPanelOut
)
def anotar(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: Anotacion,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> SalidaPanelOut:
    """Lugares que el prestador vendió por fuera (teléfono, WhatsApp): ocupan cupo y
    cuentan para el mínimo, sin comisión."""
    _, unidad = _excursion(db, publicacion_id, unidad_id, prestador, editable=False)
    fila = _fila(db, unidad, datos)
    try:
        salidas.tomar(
            db, fila, datos.personas, OrigenBloqueo.EXTERNA,
            nota=(datos.nota or "").strip() or "Venta por fuera",
        )
    except salidas.SinCupo as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except salidas.SalidaInvalida as e:
        raise _invalida(e) from e
    salida = _una(db, unidad, fila)
    db.commit()
    return salida


@router.delete(
    "/{publicacion_id}/unidades/{unidad_id}/salidas/anotados/{tomado_id}",
    response_model=SalidaPanelOut,
)
def quitar_anotado(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    tomado_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> SalidaPanelOut:
    """Suelta lugares anotados a mano. Las reservas nuestras se cancelan desde la reserva."""
    _, unidad = _excursion(db, publicacion_id, unidad_id, prestador, editable=False)
    tomado = db.get(CupoTomado, tomado_id)
    if tomado is None or tomado.salida.unidad_id != unidad.id or not tomado.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esos lugares")
    if tomado.item_reserva_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Es una reserva de la plataforma: se cancela desde la reserva, con su reintegro",
        )
    salidas.soltar(db, tomado)
    salida = _una(db, unidad, tomado.salida)
    db.commit()
    return salida

