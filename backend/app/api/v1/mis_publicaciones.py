"""Alta y edición de publicaciones por el prestador (docs/01 §5 R2).

Todo lo de acá exige sesión y que la publicación sea del prestador que pide: no
alcanza con adivinar un id. La validación de completitud vive en
`app.services.edicion`, no en los endpoints, porque la misma regla la necesita la
pantalla para mostrar qué falta antes de intentar.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import prestador_actual
from app.api.v1.publicaciones import Dinero
from app.core.database import get_db
from app.models import (
    Adicional,
    BloqueoHorario,
    CalendarioExterno,
    Comodidad,
    Foto,
    FranjaHoraria,
    Localidad,
    PoliticaCancelacion,
    Prestador,
    Publicacion,
    SubtipoServicio,
    Tarifa,
    TarifaHoraria,
    TipoServicio,
    Unidad,
    comodidad_tipo_servicio,
)
from app.models.enums import EstadoPublicacion, ModoReserva, OrigenBloqueo
from app.services import calendario as agenda
from app.services import edicion, horarios
from app.services import fotos as almacen
from app.services.precios_eventos import ZONA, en_hora

router = APIRouter(prefix="/mis-publicaciones", tags=["mis publicaciones"])


# --- Formas de entrada y salida ---


class NuevaPublicacion(BaseModel):
    titulo: Annotated[str, Field(min_length=3, max_length=150)]
    localidad_id: uuid.UUID
    subtipo_servicio_id: uuid.UUID | None = None
    tipo: Literal["alojamiento", "salon_eventos"] = "alojamiento"


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
    porcentaje_sena: Annotated[
        int | None, Field(default=None, ge=0, le=100, description="0: sin seña, se cobra todo")
    ] = None


#: Una unidad de alojamiento no pasa de esto; un salón sí (docs/04 §5 S3).
CAPACIDAD_MAXIMA_ALOJAMIENTO = 30


class NuevaUnidad(BaseModel):
    nombre: Annotated[str, Field(min_length=1, max_length=120)]
    capacidad: Annotated[int, Field(ge=1, le=5000)]
    capacidad_base: Annotated[int | None, Field(default=None, ge=1, le=5000)] = None
    capacidad_sentados: Annotated[int | None, Field(default=None, ge=1, le=5000)] = None
    preparacion_minutos: Annotated[int, Field(default=0, ge=0, le=720)] = 0
    cargo_limpieza: Decimal = Decimal(0)
    cargo_persona_extra: Decimal = Decimal(0)
    cargo_mascota: Decimal = Decimal(0)
    descuento_semanal: Annotated[Decimal, Field(default=Decimal(0), ge=0, le=90)] = Decimal(0)
    descuento_mensual: Annotated[Decimal, Field(default=Decimal(0), ge=0, le=90)] = Decimal(0)
    activa: bool = True


DiaSemana = Literal["0", "1", "2", "3", "4", "5", "6"]
#: Un precio cargado por el prestador. El mismo límite para el precio base y para
#: el de cada día: un "1e30" o un "inf" guardado rompería cada cotización.
Precio = Annotated[
    Decimal, Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
]
PreciosPorDia = dict[DiaSemana, Precio]


class NuevaTarifa(BaseModel):
    nombre: Annotated[str, Field(min_length=1, max_length=80)]
    precio_noche: Precio
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    precios_dia_semana: PreciosPorDia | None = None
    estadia_minima: Annotated[int, Field(default=1, ge=1, le=90)] = 1
    estadia_maxima: Annotated[int | None, Field(default=None, ge=1, le=365)] = None
    anticipacion_minima_dias: Annotated[int, Field(default=0, ge=0, le=90)] = 0
    prioridad: int = 0

    @model_validator(mode="after")
    def _minimo_hasta_el_maximo(self) -> NuevaTarifa:
        if self.estadia_maxima is not None and self.estadia_minima > self.estadia_maxima:
            raise ValueError("El mínimo de noches no puede superar al máximo")
        return self


class NuevaFranja(BaseModel):
    nombre: Annotated[str, Field(min_length=1, max_length=80)]
    hora_inicio: time
    hora_fin: time = Field(description="Si es menor o igual que el inicio, termina al otro día")
    precio: Precio
    precios_dia_semana: PreciosPorDia | None = None


class NuevaTarifaHoraria(BaseModel):
    precio_hora: Precio
    horas_minimas: Annotated[int, Field(ge=1, le=24)] = 1
    hora_apertura: time
    hora_cierre: time = Field(description="Si es menor o igual que la apertura, al otro día")
    precios_dia_semana: PreciosPorDia | None = None
    recargo_nocturno_desde: time | None = None
    recargo_nocturno_porcentaje: Annotated[Decimal, Field(ge=0, le=100)] = Decimal(0)


class NuevoAdicional(BaseModel):
    nombre: Annotated[str, Field(min_length=1, max_length=80)]
    descripcion: Annotated[str | None, Field(default=None, max_length=200)] = None
    precio: Precio
    por_persona: bool = False


class FranjaOut(BaseModel):
    id: uuid.UUID
    nombre: str
    hora_inicio: time
    hora_fin: time
    precio: Dinero
    precios_dia_semana: dict[str, str] | None


class TarifaHorariaOut(BaseModel):
    precio_hora: Dinero
    horas_minimas: int
    hora_apertura: time
    hora_cierre: time
    precios_dia_semana: dict[str, str] | None
    recargo_nocturno_desde: time | None
    recargo_nocturno_porcentaje: Decimal


class AdicionalOut(BaseModel):
    id: uuid.UUID
    nombre: str
    descripcion: str | None
    precio: Dinero
    por_persona: bool


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
    # Salones (docs/04)
    capacidad_sentados: int | None = None
    preparacion_minutos: int = 0
    franjas: list[FranjaOut] = Field(default_factory=list)
    tarifa_horaria: TarifaHorariaOut | None = None
    adicionales: list[AdicionalOut] = Field(default_factory=list)


class FotoOut(BaseModel):
    id: uuid.UUID
    url: str
    orden: int
    descripcion: str | None


class PublicacionOut(BaseModel):
    id: uuid.UUID
    tipo: str = Field(description="Código del tipo de servicio: alojamiento, salon_eventos")
    modo_reserva: ModoReserva
    porcentaje_sena: int | None
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
            selectinload(Publicacion.unidades).selectinload(Unidad.franjas),
            selectinload(Publicacion.unidades).selectinload(Unidad.tarifa_horaria),
            selectinload(Publicacion.unidades).selectinload(Unidad.adicionales),
            selectinload(Publicacion.tipo_servicio),
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
        tipo=p.tipo_servicio.codigo,
        modo_reserva=p.tipo_servicio.modo_reserva,
        porcentaje_sena=p.porcentaje_sena,
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
                capacidad_sentados=u.capacidad_sentados,
                preparacion_minutos=u.preparacion_minutos or 0,
                franjas=[
                    FranjaOut(
                        id=f.id, nombre=f.nombre, hora_inicio=f.hora_inicio,
                        hora_fin=f.hora_fin, precio=f.precio,
                        precios_dia_semana=_por_dia_out(f.precios_dia_semana),
                    )
                    for f in sorted(u.franjas, key=lambda x: x.hora_inicio)
                    if f.activa
                ],
                tarifa_horaria=(
                    TarifaHorariaOut(
                        precio_hora=u.tarifa_horaria.precio_hora,
                        horas_minimas=u.tarifa_horaria.horas_minimas,
                        hora_apertura=u.tarifa_horaria.hora_apertura,
                        hora_cierre=u.tarifa_horaria.hora_cierre,
                        precios_dia_semana=_por_dia_out(u.tarifa_horaria.precios_dia_semana),
                        recargo_nocturno_desde=u.tarifa_horaria.recargo_nocturno_desde,
                        recargo_nocturno_porcentaje=u.tarifa_horaria.recargo_nocturno_porcentaje,
                    )
                    if u.tarifa_horaria and u.tarifa_horaria.activa
                    else None
                ),
                adicionales=[
                    AdicionalOut(
                        id=a.id, nombre=a.nombre, descripcion=a.descripcion, precio=a.precio,
                        por_persona=a.por_persona,
                    )
                    for a in sorted(u.adicionales, key=lambda x: x.nombre)
                    if a.activo
                ],
            )
            for u in sorted(p.unidades, key=lambda x: (x.capacidad, x.nombre))
        ],
        faltantes=edicion.faltantes(db, p),
    )


# --- Publicación ---


def _por_dia_out(precios: dict | None) -> dict[str, str] | None:
    return {k: str(v) for k, v in precios.items()} if precios else None


def _por_dia_in(precios: dict | None) -> dict[str, str] | None:
    """Precios por día como texto en el JSON: un float perdería centavos."""
    return {k: str(v) for k, v in precios.items()} if precios else None


def _de_salon(p: Publicacion) -> None:
    if p.tipo_servicio.modo_reserva is not ModoReserva.HORAS:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esto es para salones: un alojamiento se cobra por noche"
        )


def _unidad_de(db: Session, p: Publicacion, unidad_id: uuid.UUID) -> Unidad:
    unidad = db.scalar(select(Unidad).where(Unidad.id == unidad_id, Unidad.publicacion_id == p.id))
    if unidad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa unidad")
    return unidad


def _validar_unidad(p: Publicacion, datos: NuevaUnidad) -> None:
    if (
        p.tipo_servicio.modo_reserva is not ModoReserva.HORAS
        and datos.capacidad > CAPACIDAD_MAXIMA_ALOJAMIENTO
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Una unidad de alojamiento admite hasta {CAPACIDAD_MAXIMA_ALOJAMIENTO} personas",
        )
    if datos.capacidad_base and datos.capacidad_base > datos.capacidad:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "La capacidad sin cargo no puede superar la capacidad total",
        )
    if datos.capacidad_sentados and datos.capacidad_sentados > datos.capacidad:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Sentados no pueden ser más que la capacidad total",
        )


def _exigir_subtipo_del_tipo(db: Session, subtipo_id, tipo_id) -> None:
    """El subtipo tiene que ser del tipo de la publicación: una cabaña no es "quincho"."""
    if subtipo_id is None:
        return
    subtipo = db.get(SubtipoServicio, subtipo_id)
    if subtipo is None or subtipo.tipo_id != tipo_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ese tipo no existe")


@router.post("", response_model=PublicacionOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: NuevaPublicacion,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    localidad = db.get(Localidad, datos.localidad_id)
    if localidad is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Esa localidad no existe")
    tipo = db.scalar(select(TipoServicio).where(TipoServicio.codigo == datos.tipo))
    if tipo is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ese tipo no existe")
    _exigir_subtipo_del_tipo(db, datos.subtipo_servicio_id, tipo.id)
    # Un salón arranca con la política de eventos y "a solicitud": un evento se
    # coordina antes de cerrarse (docs/04 §2). El prestador lo puede cambiar.
    es_salon = tipo.modo_reserva is ModoReserva.HORAS
    politica = (
        db.scalar(select(PoliticaCancelacion).where(PoliticaCancelacion.codigo == "eventos"))
        if es_salon
        else None
    )

    publicacion = Publicacion(
        prestador_id=prestador.id,
        tipo_servicio_id=tipo.id,
        subtipo_servicio_id=datos.subtipo_servicio_id,
        titulo=datos.titulo.strip(),
        slug=edicion.slug_libre(db, datos.titulo, localidad.slug),
        descripcion="",
        estado=EstadoPublicacion.BORRADOR,
        localidad_id=localidad.id,
        confirmacion_inmediata=not es_salon,
        politica_cancelacion_id=politica.id if politica else None,
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
        # Solo las que aplican a este tipo de servicio: "pista de baile" no se le
        # pone a una cabaña aunque alguien la mande.
        p.comodidades = list(
            db.scalars(
                select(Comodidad)
                .join(comodidad_tipo_servicio)
                .where(
                    Comodidad.codigo.in_(codigos),
                    comodidad_tipo_servicio.c.tipo_servicio_id == p.tipo_servicio_id,
                )
            )
        )

    if (subtipo := datos.get("subtipo_servicio_id")) is not None:
        _exigir_subtipo_del_tipo(db, subtipo, p.tipo_servicio_id)

    if datos.get("porcentaje_sena") == 0:
        datos["porcentaje_sena"] = None  # 0: sin seña, se cobra el total

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
    _validar_unidad(p, datos)
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
    unidad = _unidad_de(db, p, unidad_id)
    _validar_unidad(p, cambios)
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

    con_historia = (
        db.scalar(select(ItemReserva.id).where(ItemReserva.unidad_id == unidad.id))
        or db.scalar(select(BloqueoFecha.id).where(BloqueoFecha.unidad_id == unidad.id))
        or db.scalar(select(BloqueoHorario.id).where(BloqueoHorario.unidad_id == unidad.id))
    )
    if con_historia:
        unidad.activa = False
    else:
        for hijo in [
            *unidad.tarifas, *unidad.franjas, *unidad.adicionales,
            *([unidad.tarifa_horaria] if unidad.tarifa_horaria else []),
        ]:
            db.delete(hijo)
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
    unidad = _unidad_de(db, p, unidad_id)
    if p.tipo_servicio.modo_reserva is not ModoReserva.NOCHES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Un salón no se cobra por noche: cargá turnos o precio por hora",
        )
    if datos.fecha_desde and datos.fecha_hasta and datos.fecha_hasta < datos.fecha_desde:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "El rango de fechas está al revés"
        )
    if edicion.tarifa_se_superpone(db, unidad.id, datos.fecha_desde, datos.fecha_hasta):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ya hay una tarifa de temporada que se pisa con esas fechas",
        )
    campos = datos.model_dump()
    campos["precios_dia_semana"] = _por_dia_in(datos.precios_dia_semana)
    db.add(Tarifa(unidad_id=unidad.id, **campos))
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


# --- Salones: turnos, precio por hora y adicionales (docs/04 §4) ---


@router.post("/{publicacion_id}/unidades/{unidad_id}/franjas", response_model=PublicacionOut,
             status_code=201)
def crear_franja(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: NuevaFranja,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    _de_salon(p)
    unidad = _unidad_de(db, p, unidad_id)
    if datos.hora_inicio == datos.hora_fin:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "El turno tiene que empezar y terminar distinto"
        )
    db.add(
        FranjaHoraria(
            unidad_id=unidad.id,
            nombre=datos.nombre.strip(),
            hora_inicio=datos.hora_inicio,
            hora_fin=datos.hora_fin,
            precio=datos.precio,
            precios_dia_semana=_por_dia_in(datos.precios_dia_semana),
        )
    )
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.delete("/{publicacion_id}/unidades/{unidad_id}/franjas/{franja_id}",
               response_model=PublicacionOut)
def borrar_franja(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    franja_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    unidad = _unidad_de(db, p, unidad_id)
    franja = db.scalar(
        select(FranjaHoraria).where(
            FranjaHoraria.id == franja_id, FranjaHoraria.unidad_id == unidad.id
        )
    )
    if franja is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese turno")
    # Las reservas guardan el turno en su desglose: borrarlo no las toca.
    db.delete(franja)
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.put("/{publicacion_id}/unidades/{unidad_id}/tarifa-horaria",
            response_model=PublicacionOut)
def guardar_tarifa_horaria(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: NuevaTarifaHoraria,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    _de_salon(p)
    unidad = _unidad_de(db, p, unidad_id)
    campos = datos.model_dump()
    campos["precios_dia_semana"] = _por_dia_in(datos.precios_dia_semana)
    tarifa = unidad.tarifa_horaria
    if tarifa is None:
        db.add(TarifaHoraria(unidad_id=unidad.id, **campos))
    else:
        for campo, valor in campos.items():
            setattr(tarifa, campo, valor)
        tarifa.activa = True
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.delete("/{publicacion_id}/unidades/{unidad_id}/tarifa-horaria",
               response_model=PublicacionOut)
def quitar_tarifa_horaria(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    unidad = _unidad_de(db, p, unidad_id)
    if unidad.tarifa_horaria is not None:
        db.delete(unidad.tarifa_horaria)
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.post("/{publicacion_id}/unidades/{unidad_id}/adicionales",
             response_model=PublicacionOut, status_code=201)
def crear_adicional(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: NuevoAdicional,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    _de_salon(p)
    unidad = _unidad_de(db, p, unidad_id)
    db.add(Adicional(unidad_id=unidad.id, **datos.model_dump()))
    db.commit()
    return _respuesta(db, publicacion_id, prestador)


@router.delete("/{publicacion_id}/unidades/{unidad_id}/adicionales/{adicional_id}",
               response_model=PublicacionOut)
def borrar_adicional(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    adicional_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PublicacionOut:
    p = _mia(publicacion_id, prestador, db, editable=True)
    unidad = _unidad_de(db, p, unidad_id)
    adicional = db.scalar(
        select(Adicional).where(Adicional.id == adicional_id, Adicional.unidad_id == unidad.id)
    )
    if adicional is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese adicional")
    db.delete(adicional)
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
    """Unidad para el calendario por días (alojamiento)."""
    p = _mia(publicacion_id, prestador, db)
    if p.tipo_servicio.modo_reserva is not ModoReserva.NOCHES:
        # Un bloqueo por días en un salón no lo vería la reserva por horario.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Un salón usa la agenda por horas, no por días"
        )
    unidad = db.scalar(select(Unidad).where(Unidad.id == unidad_id, Unidad.publicacion_id == p.id))
    if unidad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa unidad")
    return unidad


# --- Agenda por horas de un salón (docs/04, etapa 5) ---

DIAS_AGENDA_MAX = 31


class TramoHorarioOut(BaseModel):
    id: uuid.UUID
    inicio: datetime
    fin: datetime
    origen: str
    etiqueta: str
    nota: str | None
    reserva: str | None = Field(description="Código de la reserva, si la hay")
    editable: bool = Field(description="Solo los bloqueos a mano se pueden soltar")


class AgendaHorariaOut(BaseModel):
    unidad_id: uuid.UUID
    unidad: str
    desde: date
    dias: int
    preparacion_minutos: int
    tramos: list[TramoHorarioOut]


class NuevoBloqueoHorario(BaseModel):
    dia: date
    hora_desde: time
    hora_hasta: time = Field(description="Si es menor o igual que la de inicio, al otro día")
    nota: Annotated[str | None, Field(default=None, max_length=200)] = None


ETIQUETAS_HORARIO = {
    OrigenBloqueo.RESERVA: "Reserva",
    OrigenBloqueo.RETENCION: "Esperando el pago",
    OrigenBloqueo.MANUAL: "Bloqueado a mano",
    OrigenBloqueo.EXTERNA: "Vendido por fuera",
}


def _mi_salon(publicacion_id: uuid.UUID, unidad_id: uuid.UUID, prestador, db) -> Unidad:
    p = _mia(publicacion_id, prestador, db)
    _de_salon(p)
    return _unidad_de(db, p, unidad_id)


def _agenda_horaria(db: Session, unidad: Unidad, desde: date, dias: int) -> AgendaHorariaOut:
    from app.models import ItemReserva, Reserva

    inicio = en_hora(desde, time(0, 0))
    fin = inicio + timedelta(days=dias)
    # Lo vigente: una retención vencida ya no ocupa, aunque la tarea no la haya soltado.
    filas = horarios.vigentes(db, unidad.id, inicio, fin)
    codigos = dict(
        db.execute(
            select(ItemReserva.id, Reserva.codigo)
            .join(Reserva, ItemReserva.reserva_id == Reserva.id)
            .where(ItemReserva.id.in_([b.item_reserva_id for b in filas if b.item_reserva_id]))
        ).all()
    )
    return AgendaHorariaOut(
        unidad_id=unidad.id,
        unidad=unidad.nombre,
        desde=desde,
        dias=dias,
        preparacion_minutos=unidad.preparacion_minutos or 0,
        tramos=[
            TramoHorarioOut(
                id=b.id,
                inicio=b.rango.lower,
                fin=b.rango.upper,
                origen=b.origen.value,
                etiqueta=ETIQUETAS_HORARIO.get(b.origen, b.origen.value),
                # La nota de una reserva la pone el sistema ("Reserva XXX") y
                # repetiría el código: solo se muestra la que escribió el anfitrión.
                nota=b.nota if b.origen is OrigenBloqueo.MANUAL else None,
                reserva=codigos.get(b.item_reserva_id),
                editable=b.origen is OrigenBloqueo.MANUAL,
            )
            for b in filas
        ],
    )


@router.get(
    "/{publicacion_id}/unidades/{unidad_id}/agenda-horaria", response_model=AgendaHorariaOut
)
def ver_agenda_horaria(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    desde: date | None = None,
    dias: Annotated[int, Query(ge=1, le=DIAS_AGENDA_MAX)] = 7,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> AgendaHorariaOut:
    """Lo tomado de un espacio, día por día: reservas, pagos en curso y bloqueos."""
    unidad = _mi_salon(publicacion_id, unidad_id, prestador, db)
    return _agenda_horaria(db, unidad, desde or date.today(), dias)


@router.post(
    "/{publicacion_id}/unidades/{unidad_id}/bloqueos-horarios",
    response_model=AgendaHorariaOut,
    status_code=201,
)
def bloquear_horas(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    datos: NuevoBloqueoHorario,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> AgendaHorariaOut:
    """Toma horas a mano: un evento vendido por WhatsApp, un mantenimiento.

    Pasa por la misma restricción de la base que las reservas: si choca con una
    reserva o con otro bloqueo, se rechaza.
    """
    unidad = _mi_salon(publicacion_id, unidad_id, prestador, db)
    if datos.dia < date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ese día ya pasó")
    inicio = en_hora(datos.dia, datos.hora_desde)
    fin = en_hora(datos.dia, datos.hora_hasta)
    if fin <= inicio:
        fin += timedelta(days=1)
    try:
        horarios.bloquear(
            db, unidad, inicio, fin, OrigenBloqueo.MANUAL,
            nota=(datos.nota or "").strip() or None,
        )
    except horarios.HorarioOcupado as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ese horario se pisa con una reserva o con otro bloqueo",
        ) from e
    except horarios.HorarioInvalido as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    db.commit()
    return _agenda_horaria(db, unidad, datos.dia, 7)


@router.delete(
    "/{publicacion_id}/unidades/{unidad_id}/bloqueos-horarios/{bloqueo_id}",
    response_model=AgendaHorariaOut,
)
def soltar_horas(
    publicacion_id: uuid.UUID,
    unidad_id: uuid.UUID,
    bloqueo_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> AgendaHorariaOut:
    unidad = _mi_salon(publicacion_id, unidad_id, prestador, db)
    bloqueo = db.scalar(
        select(BloqueoHorario).where(
            BloqueoHorario.id == bloqueo_id, BloqueoHorario.unidad_id == unidad.id
        )
    )
    if bloqueo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos ese bloqueo")
    if bloqueo.origen is not OrigenBloqueo.MANUAL:
        # Una reserva se cancela desde la reserva: soltarla acá dejaría al viajero
        # con una reserva confirmada y el horario libre para otro.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Solo se pueden soltar los bloqueos hechos a mano"
        )
    dia = bloqueo.rango.lower.astimezone(ZONA).date()
    db.delete(bloqueo)
    db.commit()
    return _agenda_horaria(db, unidad, dia, 7)


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
    # Cada calendario se descarga solo cada hora: el tope evita que una cuenta
    # use el servidor para pedirle a terceros cientos de direcciones.
    from app.services import calendario as agenda_externa

    # Bloquea la unidad mientras cuenta: dos pedidos a la vez no pasan el tope.
    db.execute(select(Unidad.id).where(Unidad.id == unidad.id).with_for_update())
    ya_tiene = db.scalar(
        select(func.count(CalendarioExterno.id)).where(
            CalendarioExterno.unidad_id == unidad.id
        )
    )
    if ya_tiene >= agenda_externa.MAX_POR_UNIDAD:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Una unidad puede tener hasta {agenda_externa.MAX_POR_UNIDAD} calendarios",
        )

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
