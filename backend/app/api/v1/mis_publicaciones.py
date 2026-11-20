"""Alta y edición de publicaciones por el prestador (docs/01 §5 R2).

Todo lo de acá exige sesión y que la publicación sea del prestador que pide: no
alcanza con adivinar un id. La validación de completitud vive en
`app.services.edicion`, no en los endpoints, porque la misma regla la necesita la
pantalla para mostrar qué falta antes de intentar.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import prestador_actual
from app.api.v1.publicaciones import Dinero
from app.core.database import get_db
from app.models import (
    CalendarioExterno,
    Comodidad,
    Foto,
    Localidad,
    Prestador,
    Publicacion,
    SubtipoServicio,
    Tarifa,
    TipoServicio,
    Unidad,
)
from app.models.enums import EstadoPublicacion
from app.services import calendario as agenda
from app.services import edicion
from app.services import fotos as almacen

router = APIRouter(prefix="/mis-publicaciones", tags=["mis publicaciones"])


# --- Formas de entrada y salida ---


class NuevaPublicacion(BaseModel):
    titulo: Annotated[str, Field(min_length=3, max_length=150)]
    localidad_id: uuid.UUID
    subtipo_servicio_id: uuid.UUID | None = None


class CambioPublicacion(BaseModel):
    titulo: Annotated[str | None, Field(default=None, min_length=3, max_length=150)] = None
    descripcion: str | None = None
    reglas_casa: str | None = None
    subtipo_servicio_id: uuid.UUID | None = None
    localidad_id: uuid.UUID | None = None
    zona_id: uuid.UUID | None = None
    direccion: Annotated[str | None, Field(default=None, max_length=200)] = None
    lat: Annotated[float | None, Field(default=None, ge=-90, le=90)] = None
    lon: Annotated[float | None, Field(default=None, ge=-180, le=180)] = None
    hora_ingreso: time | None = None
    hora_salida: time | None = None
    confirmacion_inmediata: bool | None = None
    politica_cancelacion_id: uuid.UUID | None = None
    comodidades: list[str] | None = Field(default=None, description="Códigos de comodidad")


class NuevaUnidad(BaseModel):
    nombre: Annotated[str, Field(min_length=1, max_length=120)]
    capacidad: Annotated[int, Field(ge=1, le=30)]
    capacidad_base: Annotated[int | None, Field(default=None, ge=1, le=30)] = None
    cargo_limpieza: Decimal = Decimal(0)
    cargo_persona_extra: Decimal = Decimal(0)
    cargo_mascota: Decimal = Decimal(0)
    descuento_semanal: Annotated[Decimal, Field(default=Decimal(0), ge=0, le=90)] = Decimal(0)
    descuento_mensual: Annotated[Decimal, Field(default=Decimal(0), ge=0, le=90)] = Decimal(0)
    activa: bool = True


class NuevaTarifa(BaseModel):
    nombre: Annotated[str, Field(min_length=1, max_length=80)]
    precio_noche: Annotated[Decimal, Field(gt=0)]
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    precios_dia_semana: dict[str, str] | None = None
    estadia_minima: Annotated[int, Field(default=1, ge=1, le=90)] = 1
    estadia_maxima: Annotated[int | None, Field(default=None, ge=1, le=365)] = None
    anticipacion_minima_dias: Annotated[int, Field(default=0, ge=0, le=90)] = 0
    prioridad: int = 0


class TarifaOut(BaseModel):
    id: uuid.UUID
    nombre: str
    precio_noche: Dinero
    fecha_desde: date | None
    fecha_hasta: date | None
    estadia_minima: int
    estadia_maxima: int | None
    anticipacion_minima_dias: int
    prioridad: int


class UnidadOut(BaseModel):
    id: uuid.UUID
    nombre: str
    capacidad: int
    capacidad_base: int | None
    cargo_limpieza: Dinero
    cargo_persona_extra: Dinero
    cargo_mascota: Dinero
    descuento_semanal: Dinero
    descuento_mensual: Dinero
    activa: bool
    tarifas: list[TarifaOut]


class FotoOut(BaseModel):
    id: uuid.UUID
    url: str
    orden: int
    descripcion: str | None


class PublicacionOut(BaseModel):
    id: uuid.UUID
    slug: str
    titulo: str
    descripcion: str
    reglas_casa: str | None
    estado: EstadoPublicacion
    motivo_rechazo: str | None
    subtipo_servicio_id: uuid.UUID | None
    localidad_id: uuid.UUID
    localidad: str
    provincia: str
    zona_id: uuid.UUID | None
    direccion: str | None
    lat: float | None
    lon: float | None
    hora_ingreso: time | None
    hora_salida: time | None
    confirmacion_inmediata: bool
    politica_cancelacion_id: uuid.UUID | None
    comodidades: list[str]
    fotos: list[FotoOut]
    unidades: list[UnidadOut]
    faltantes: list[str]


class Rechazo(BaseModel):
    motivo: Annotated[str, Field(min_length=5, max_length=500)]


class NuevoBloqueo(BaseModel):
    desde: date
    hasta: date = Field(description="Exclusivo: es el día de salida, queda libre")
    nota: Annotated[str | None, Field(default=None, max_length=200)] = None


class NuevoCalendario(BaseModel):
    nombre: Annotated[str, Field(min_length=1, max_length=60)]
    url: Annotated[str, Field(min_length=10, max_length=2000)]
    plataforma: Annotated[str | None, Field(default=None, max_length=30)] = None


class TramoOut(BaseModel):
    id: uuid.UUID
    desde: date
    hasta: date
    origen: str
    etiqueta: str
    nota: str | None
    calendario: str | None
    editable: bool = Field(description="Solo los bloqueos manuales se pueden soltar")


class CalendarioExternoOut(BaseModel):
    id: uuid.UUID
    nombre: str
    plataforma: str
    url: str
    ultima_sincronizacion: datetime | None
    ultimo_error: str | None


class AgendaOut(BaseModel):
    unidad_id: uuid.UUID
    unidad: str
    url_exportacion: str = Field(description="Pegala en Booking o Airbnb")
    tramos: list[TramoOut]
    calendarios: list[CalendarioExternoOut]


class SincronizacionOut(BaseModel):
    importados: int
    descartados: int
    detalle: str
    calendarios: list[CalendarioExternoOut]


class Orden(BaseModel):
    fotos: list[uuid.UUID] = Field(description="Ids en el orden deseado")


# --- Ayudantes ---


def _mia(
    publicacion_id: uuid.UUID, prestador: Prestador, db: Session, editable: bool = False
) -> Publicacion:
    publicacion = db.scalar(
        select(Publicacion)
        .where(Publicacion.id == publicacion_id)
        .options(
            selectinload(Publicacion.fotos),
            selectinload(Publicacion.comodidades),
            selectinload(Publicacion.unidades).selectinload(Unidad.tarifas),
            selectinload(Publicacion.localidad).selectinload(Localidad.provincia),
        )
    )
    if publicacion is None or publicacion.prestador_id != prestador.id:
        # Mismo 404 exista o no: un id ajeno no debería poder confirmarse.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa publicación")
    if editable and publicacion.estado is EstadoPublicacion.EN_REVISION:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La publicación está en revisión. Esperá la respuesta del operador para editarla.",
        )
    return publicacion


def _coordenadas(db: Session, publicacion_id: uuid.UUID) -> tuple[float | None, float | None]:
    from app.services.busqueda import lat_lon

    lat_col, lon_col = lat_lon(Publicacion.ubicacion)
    fila = db.execute(
        select(lat_col, lon_col).where(
            Publicacion.id == publicacion_id, Publicacion.ubicacion.is_not(None)
        )
    ).first()
    return (fila[0], fila[1]) if fila else (None, None)


def _respuesta(db: Session, publicacion_id: uuid.UUID, prestador: Prestador) -> PublicacionOut:
    """Vuelve a leer desde la base después de escribir.

    La sesión no expira los objetos al commitear (`expire_on_commit=False`), así que
    sin esto la publicación que ya estaba en memoria se devolvería sin la unidad o
    la foto recién creadas.
    """
    db.expire_all()
    return _salida(db, _mia(publicacion_id, prestador, db))


def _salida(db: Session, p: Publicacion) -> PublicacionOut:
    lat, lon = _coordenadas(db, p.id)
    return PublicacionOut(
        id=p.id,
        slug=p.slug,
        titulo=p.titulo,
        descripcion=p.descripcion,
        reglas_casa=p.reglas_casa,
        estado=p.estado,
        motivo_rechazo=p.motivo_rechazo,
        subtipo_servicio_id=p.subtipo_servicio_id,
        localidad_id=p.localidad_id,
        localidad=p.localidad.nombre,
        provincia=p.localidad.provincia.nombre,
        zona_id=p.zona_id,
        direccion=p.direccion,
        lat=lat,
        lon=lon,
        hora_ingreso=p.hora_ingreso,
        hora_salida=p.hora_salida,
        confirmacion_inmediata=p.confirmacion_inmediata,
        politica_cancelacion_id=p.politica_cancelacion_id,
        comodidades=sorted(c.codigo for c in p.comodidades),
        fotos=[
            FotoOut(id=f.id, url=f.url, orden=f.orden, descripcion=f.descripcion)
            for f in sorted(p.fotos, key=lambda x: x.orden)
        ],
        unidades=[
            UnidadOut(
                id=u.id,
                nombre=u.nombre,
                capacidad=u.capacidad,
                capacidad_base=u.capacidad_base,
                cargo_limpieza=u.cargo_limpieza,
                cargo_persona_extra=u.cargo_persona_extra,
                cargo_mascota=u.cargo_mascota,
                descuento_semanal=u.descuento_semanal,
                descuento_mensual=u.descuento_mensual,
                activa=u.activa,
                tarifas=[
                    TarifaOut(
                        id=t.id,
                        nombre=t.nombre,
                        precio_noche=t.precio_noche,
                        fecha_desde=t.fecha_desde,
                        fecha_hasta=t.fecha_hasta,
                        estadia_minima=t.estadia_minima,
                        estadia_maxima=t.estadia_maxima,
                        anticipacion_minima_dias=t.anticipacion_minima_dias,
                        prioridad=t.prioridad,
                    )
                    for t in sorted(u.tarifas, key=lambda x: (x.prioridad, x.nombre))
                ],
            )
            for u in sorted(p.unidades, key=lambda x: (x.capacidad, x.nombre))
        ],
        faltantes=edicion.faltantes(db, p),
    )


# --- Publicación ---


@router.post("", response_model=PublicacionOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: NuevaPublicacion,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    localidad = db.get(Localidad, datos.localidad_id)
    if localidad is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Esa localidad no existe")
    tipo = db.scalar(select(TipoServicio).where(TipoServicio.codigo == "alojamiento"))

    publicacion = Publicacion(
        prestador_id=prestador.id,
        tipo_servicio_id=tipo.id,
        subtipo_servicio_id=datos.subtipo_servicio_id,
        titulo=datos.titulo.strip(),
        slug=edicion.slug_libre(db, datos.titulo, localidad.slug),
        descripcion="",
        estado=EstadoPublicacion.BORRADOR,
        localidad_id=localidad.id,
    )
    db.add(publicacion)
    db.commit()
    return _respuesta(db, publicacion.id, prestador)


@router.get("", response_model=list[PublicacionOut])
def listar(
    estado: Annotated[EstadoPublicacion | None, Query()] = None,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> list[PublicacionOut]:
    consulta = select(Publicacion).where(Publicacion.prestador_id == prestador.id)
    if estado:
        consulta = consulta.where(Publicacion.estado == estado)
    ids = list(db.scalars(consulta.order_by(Publicacion.creado_en.desc())))
    return [_salida(db, _mia(p.id, prestador, db)) for p in ids]


@router.get("/{publicacion_id}", response_model=PublicacionOut)
def ver(
    publicacion_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    return _respuesta(db, publicacion_id, prestador)


@router.patch("/{publicacion_id}", response_model=PublicacionOut)
def editar(
    publicacion_id: uuid.UUID,
    cambios: CambioPublicacion,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    datos = cambios.model_dump(exclude_unset=True)

    # Se sacan siempre las dos, aunque venga una sola: la ubicación es un punto.
    lat = datos.pop("lat", None)
    lon = datos.pop("lon", None)
    if lat is not None or lon is not None:
        actuales = _coordenadas(db, p.id)
        lat = lat if lat is not None else actuales[0]
        lon = lon if lon is not None else actuales[1]
        if lat is None or lon is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "La ubicación necesita latitud y longitud"
            )
        p.ubicacion = f"SRID=4326;POINT({lon} {lat})"

    if (codigos := datos.pop("comodidades", None)) is not None:
        p.comodidades = list(db.scalars(select(Comodidad).where(Comodidad.codigo.in_(codigos))))

    if (subtipo := datos.get("subtipo_servicio_id")) is not None and not db.get(
        SubtipoServicio, subtipo
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ese tipo no existe")

    for campo, valor in datos.items():
        setattr(p, campo, valor.strip() if isinstance(valor, str) else valor)

    db.commit()
    return _respuesta(db, publicacion_id, prestador)


# --- Fotos ---


@router.post("/{publicacion_id}/fotos", response_model=PublicacionOut, status_code=201)
async def subir_foto(
    publicacion_id: uuid.UUID,
    archivo: Annotated[UploadFile, File(description="Imagen del alojamiento")],
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    try:
        guardada = almacen.guardar(p.id, await archivo.read(), archivo.content_type)
    except almacen.FotoInvalida as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    ultimo = db.scalar(
        select(func.coalesce(func.max(Foto.orden), -1)).where(Foto.publicacion_id == p.id)
    )
    db.add(Foto(publicacion_id=p.id, url=guardada.url, orden=ultimo + 1))
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.delete("/{publicacion_id}/fotos/{foto_id}", response_model=PublicacionOut)
def borrar_foto(
    publicacion_id: uuid.UUID,
    foto_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    foto = db.scalar(select(Foto).where(Foto.id == foto_id, Foto.publicacion_id == p.id))
    if foto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa foto")
    almacen.borrar(foto.url)
    db.delete(foto)
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.patch("/{publicacion_id}/fotos", response_model=PublicacionOut)
def reordenar_fotos(
    publicacion_id: uuid.UUID,
    orden: Orden,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    propias = {f.id: f for f in p.fotos}
    if set(orden.fotos) != set(propias):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "La lista tiene que incluir todas las fotos"
        )
    for posicion, foto_id in enumerate(orden.fotos):
        propias[foto_id].orden = posicion
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


# --- Unidades y tarifas ---


@router.post("/{publicacion_id}/unidades", response_model=PublicacionOut, status_code=201)
def crear_unidad(
    publicacion_id: uuid.UUID,
    datos: NuevaUnidad,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    if datos.capacidad_base and datos.capacidad_base > datos.capacidad:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "La capacidad sin cargo no puede superar la capacidad total",
        )
    db.add(Unidad(publicacion_id=p.id, **datos.model_dump()))
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.patch("/{publicacion_id}/unidades/{unidad_id}", response_model=PublicacionOut)
def editar_unidad(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    cambios: NuevaUnidad,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    unidad = db.scalar(select(Unidad).where(Unidad.id == unidad_id, Unidad.publicacion_id == p.id))
    if unidad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa unidad")
    for campo, valor in cambios.model_dump().items():
        setattr(unidad, campo, valor)
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.delete("/{publicacion_id}/unidades/{unidad_id}", response_model=PublicacionOut)
def borrar_unidad(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    unidad = db.scalar(select(Unidad).where(Unidad.id == unidad_id, Unidad.publicacion_id == p.id))
    if unidad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa unidad")
    # Si ya tuvo movimiento no se borra: se desactiva, para no perder el historial.
    from app.models import BloqueoFecha, ItemReserva

    con_historia = db.scalar(
        select(ItemReserva.id).where(ItemReserva.unidad_id == unidad.id)
    ) or db.scalar(select(BloqueoFecha.id).where(BloqueoFecha.unidad_id == unidad.id))
    if con_historia:
        unidad.activa = False
    else:
        for t in list(unidad.tarifas):
            db.delete(t)
        db.delete(unidad)
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.post("/{publicacion_id}/unidades/{unidad_id}/tarifas", response_model=PublicacionOut,
             status_code=201)
def crear_tarifa(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: NuevaTarifa,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    unidad = db.scalar(select(Unidad).where(Unidad.id == unidad_id, Unidad.publicacion_id == p.id))
    if unidad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa unidad")
    if datos.fecha_desde and datos.fecha_hasta and datos.fecha_hasta < datos.fecha_desde:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "El rango de fechas está al revés"
        )
    if edicion.tarifa_se_superpone(db, unidad.id, datos.fecha_desde, datos.fecha_hasta):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ya hay una tarifa de temporada que se pisa con esas fechas",
        )
    db.add(Tarifa(unidad_id=unidad.id, **datos.model_dump()))
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.delete("/{publicacion_id}/unidades/{unidad_id}/tarifas/{tarifa_id}",
               response_model=PublicacionOut)
def borrar_tarifa(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    tarifa_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    tarifa = db.scalar(
        select(Tarifa)
        .join(Unidad, Tarifa.unidad_id == Unidad.id)
        .where(Tarifa.id == tarifa_id, Unidad.publicacion_id == p.id)
    )
    if tarifa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa tarifa")
    db.delete(tarifa)
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


# --- Estados ---


@router.post("/{publicacion_id}/enviar-a-revision", response_model=PublicacionOut)
def enviar_a_revision(
    publicacion_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db)
    if not prestador.puede_publicar:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Para publicar necesitás CUIT, condición frente al IVA y tu cuenta de "
            "Mercado Pago vinculada.",
        )
    try:
        edicion.enviar_a_revision(db, p)
    except edicion.PublicacionIncompleta as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"mensaje": "Todavía falta información", "faltantes": e.faltantes},
        ) from e
    except edicion.TransicionInvalida as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


def _cambiar(accion, publicacion_id, prestador, db) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db)
    try:
        accion(p)
    except edicion.TransicionInvalida as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.post("/{publicacion_id}/pausar", response_model=PublicacionOut)
def pausar(
    publicacion_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    return _cambiar(edicion.pausar, publicacion_id, prestador, db)


@router.post("/{publicacion_id}/reactivar", response_model=PublicacionOut)
def reactivar(
    publicacion_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    return _cambiar(edicion.reactivar, publicacion_id, prestador, db)


@router.post("/{publicacion_id}/volver-a-borrador", response_model=PublicacionOut)
def volver_a_borrador(
    publicacion_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    return _cambiar(edicion.volver_a_borrador, publicacion_id, prestador, db)


# --- Calendario: bloqueos propios y calendarios ajenos (docs/01 §5 R3) ---


def _mi_unidad(publicacion_id: uuid.UUID, unidad_id: uuid.UUID, prestador, db) -> Unidad:
    p = _mia(publicacion_id, prestador, db)
    unidad = db.scalar(select(Unidad).where(Unidad.id == unidad_id, Unidad.publicacion_id == p.id))
    if unidad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa unidad")
    return unidad


def _agenda(db: Session, unidad: Unidad) -> AgendaOut:
    from app.core.config import get_settings

    externos = list(
        db.scalars(
            select(CalendarioExterno)
            .where(CalendarioExterno.unidad_id == unidad.id)
            .order_by(CalendarioExterno.nombre)
        )
    )
    base = get_settings().url_publica_api.rstrip("/")
    return AgendaOut(
        unidad_id=unidad.id,
        unidad=unidad.nombre,
        url_exportacion=f"{base}/api/v1/ical/{unidad.ical_export_token}.ics",
        tramos=[
            TramoOut(
                id=t.id,
                desde=t.desde,
                hasta=t.hasta,
                origen=t.origen.value,
                etiqueta=t.etiqueta,
                nota=t.nota,
                calendario=t.calendario,
                editable=t.origen.value == "manual",
            )
            for t in agenda.ocupacion(db, unidad.id)
        ],
        calendarios=[
            CalendarioExternoOut(
                id=c.id,
                nombre=c.nombre,
                plataforma=c.plataforma,
                url=c.url,
                ultima_sincronizacion=c.ultima_sincronizacion,
                ultimo_error=c.ultimo_error,
            )
            for c in externos
        ],
    )


@router.get("/{publicacion_id}/unidades/{unidad_id}/calendario", response_model=AgendaOut)
def ver_calendario(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> AgendaOut:
    return _agenda(db, _mi_unidad(publicacion_id, unidad_id, prestador, db))


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/bloqueos", response_model=AgendaOut, status_code=201
)
def bloquear_fechas(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: NuevoBloqueo,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> AgendaOut:
    unidad = _mi_unidad(publicacion_id, unidad_id, prestador, db)
    try:
        agenda.bloquear(db, unidad.id, datos.desde, datos.hasta, datos.nota)
    except agenda.RangoInvalido as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except agenda.FechasOcupadas as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    db.commit()
    return _agenda(db, _mi_unidad(publicacion_id, unidad_id, prestador, db))


@router.delete(
    "/{publicacion_id}/unidades/{unidad_id}/bloqueos/{bloqueo_id}", response_model=AgendaOut
)
def soltar_fechas(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    bloqueo_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> AgendaOut:
    unidad = _mi_unidad(publicacion_id, unidad_id, prestador, db)
    if not agenda.desbloquear(db, unidad.id, bloqueo_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Ese bloqueo no existe o no es manual: los de reservas y calendarios los "
            "maneja su propia fuente.",
        )
    db.commit()
    return _agenda(db, _mi_unidad(publicacion_id, unidad_id, prestador, db))


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/calendarios", response_model=AgendaOut, status_code=201
)
def agregar_calendario(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: NuevoCalendario,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> AgendaOut:
    unidad = _mi_unidad(publicacion_id, unidad_id, prestador, db)
    from app.services import canales, red

    try:
        red.validar_forma(datos.url)
    except red.DireccionNoPermitida as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    db.add(
        CalendarioExterno(
            unidad_id=unidad.id,
            nombre=datos.nombre.strip(),
            url=datos.url.strip(),
            plataforma=datos.plataforma or canales.detectar(datos.url),
        )
    )
    db.commit()
    return _agenda(db, _mi_unidad(publicacion_id, unidad_id, prestador, db))


@router.delete(
    "/{publicacion_id}/unidades/{unidad_id}/calendarios/{calendario_id}", response_model=AgendaOut
)
def quitar_calendario(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    calendario_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> AgendaOut:
    unidad = _mi_unidad(publicacion_id, unidad_id, prestador, db)
    externo = db.scalar(
        select(CalendarioExterno).where(
            CalendarioExterno.id == calendario_id, CalendarioExterno.unidad_id == unidad.id
        )
    )
    if externo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese calendario")
    # Al sacarlo se liberan las fechas que había traído.
    db.delete(externo)
    db.commit()
    return _agenda(db, _mi_unidad(publicacion_id, unidad_id, prestador, db))


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/calendarios/{calendario_id}/sincronizar",
    response_model=SincronizacionOut,
)
def sincronizar_calendario(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    calendario_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> SincronizacionOut:
    unidad = _mi_unidad(publicacion_id, unidad_id, prestador, db)
    externo = db.scalar(
        select(CalendarioExterno).where(
            CalendarioExterno.id == calendario_id, CalendarioExterno.unidad_id == unidad.id
        )
    )
    if externo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese calendario")
    try:
        resultado = agenda.sincronizar(db, externo)
    except Exception as e:  # noqa: BLE001 - descarga o parseo
        db.commit()  # el error queda registrado en el calendario
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, externo.ultimo_error or f"Falló: {type(e).__name__}"
        ) from e
    db.commit()
    salida = _agenda(db, _mi_unidad(publicacion_id, unidad_id, prestador, db))
    return SincronizacionOut(
        importados=resultado.importados,
        descartados=resultado.descartados,
        detalle=resultado.detalle,
        calendarios=salida.calendarios,
    )
