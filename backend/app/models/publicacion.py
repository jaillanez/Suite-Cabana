import uuid
from datetime import date, datetime, time

from geoalchemy2 import Geography
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Table,
    text,
)
from sqlalchemy.dialects.postgresql import DATERANGE, JSONB, ExcludeConstraint, Range
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Dinero, IdMixin, Porcentaje, TiempoMixin, pg_enum
from app.models.enums import EstadoPublicacion, OrigenBloqueo

publicacion_comodidad = Table(
    "publicacion_comodidad",
    Base.metadata,
    Column("publicacion_id", ForeignKey("publicacion.id", ondelete="CASCADE"), primary_key=True),
    Column("comodidad_id", ForeignKey("comodidad.id"), primary_key=True),
)


class Publicacion(IdMixin, TiempoMixin, Base):
    """Ficha visible. Ej.: 'Complejo Los Álamos'."""

    __tablename__ = "publicacion"
    __table_args__ = (Index("ix_publicacion_ubicacion", "ubicacion", postgresql_using="gist"),)

    prestador_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prestador.id"), index=True)
    tipo_servicio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tipo_servicio.id"))
    subtipo_servicio_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subtipo_servicio.id"))
    titulo: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(170), unique=True)
    descripcion: Mapped[str]
    reglas_casa: Mapped[str | None]
    estado: Mapped[EstadoPublicacion] = mapped_column(
        pg_enum(EstadoPublicacion, "estado_publicacion"),
        default=EstadoPublicacion.BORRADOR,
        index=True,
    )
    motivo_rechazo: Mapped[str | None]

    localidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("localidad.id"), index=True)
    zona_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zona.id"))
    direccion: Mapped[str | None] = mapped_column(String(200))
    ubicacion = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=True)

    hora_ingreso: Mapped[time | None]
    hora_salida: Mapped[time | None]
    confirmacion_inmediata: Mapped[bool] = mapped_column(default=True)
    politica_cancelacion_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("politica_cancelacion.id")
    )
    calificacion_promedio: Mapped[float | None]
    cantidad_resenas: Mapped[int] = mapped_column(default=0)

    prestador: Mapped["Prestador"] = relationship(back_populates="publicaciones")  # noqa: F821
    unidades: Mapped[list["Unidad"]] = relationship(back_populates="publicacion")
    fotos: Mapped[list["Foto"]] = relationship(order_by="Foto.orden")
    comodidades: Mapped[list["Comodidad"]] = relationship(  # noqa: F821
        secondary=publicacion_comodidad
    )


class Foto(IdMixin, Base):
    __tablename__ = "foto"

    publicacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publicacion.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str]
    orden: Mapped[int] = mapped_column(default=0)
    descripcion: Mapped[str | None] = mapped_column(String(200))


class Unidad(IdMixin, TiempoMixin, Base):
    """Lo que realmente se reserva. Ej.: 'Cabaña 2, 4 personas'."""

    __tablename__ = "unidad"

    publicacion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publicacion.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    capacidad: Mapped[int] = mapped_column(SmallInteger)
    capacidad_base: Mapped[int | None] = mapped_column(SmallInteger)  # sobre esta, persona extra
    activa: Mapped[bool] = mapped_column(default=True)

    cargo_limpieza: Mapped[Dinero] = mapped_column(default=0)
    cargo_persona_extra: Mapped[Dinero] = mapped_column(default=0)
    cargo_mascota: Mapped[Dinero] = mapped_column(default=0)
    descuento_semanal: Mapped[Porcentaje] = mapped_column(default=0)
    descuento_mensual: Mapped[Porcentaje] = mapped_column(default=0)

    ical_export_token: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, unique=True)

    publicacion: Mapped[Publicacion] = relationship(back_populates="unidades")
    tarifas: Mapped[list["Tarifa"]] = relationship(back_populates="unidad")
    calendarios_externos: Mapped[list["CalendarioExterno"]] = relationship()


class Tarifa(IdMixin, Base):
    """Tarifa base (sin fechas) o por temporada. Gana la de mayor prioridad que cubra la noche.

    precios_dia_semana: {"4": 55000, "5": 60000}  (0 = lunes) sobrescribe precio_noche.
    """

    __tablename__ = "tarifa"

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    fecha_desde: Mapped[date | None]
    fecha_hasta: Mapped[date | None]
    precio_noche: Mapped[Dinero]
    precios_dia_semana: Mapped[dict | None] = mapped_column(JSONB)
    estadia_minima: Mapped[int] = mapped_column(SmallInteger, default=1)
    estadia_maxima: Mapped[int | None] = mapped_column(SmallInteger)
    anticipacion_minima_dias: Mapped[int] = mapped_column(SmallInteger, default=0)
    prioridad: Mapped[int] = mapped_column(default=0)

    unidad: Mapped[Unidad] = relationship(back_populates="tarifas")


class CalendarioExterno(IdMixin, Base):
    """iCal importado (Booking, Airbnb, etc.)."""

    __tablename__ = "calendario_externo"

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(60))
    url: Mapped[str]
    ultima_sincronizacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_error: Mapped[str | None]


class BloqueoFecha(IdMixin, TiempoMixin, Base):
    """Noches no disponibles de una unidad (rango [inicio, fin) ).

    La restricción de exclusión garantiza cero dobles reservas a nivel de BD.
    Las retenciones vencidas se desactivan con una tarea en segundo plano.
    Requiere la extensión btree_gist (migración 0001).
    """

    __tablename__ = "bloqueo_fecha"
    __table_args__ = (
        ExcludeConstraint(
            ("unidad_id", "="),
            ("rango", "&&"),
            name="ex_bloqueo_fecha_sin_superposicion",
            using="gist",
            where=text("activo"),
        ),
        Index("ix_bloqueo_fecha_vence", "vence_en", postgresql_where=text("vence_en IS NOT NULL")),
    )

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    rango: Mapped[Range[date]] = mapped_column(DATERANGE)
    origen: Mapped[OrigenBloqueo] = mapped_column(pg_enum(OrigenBloqueo, "origen_bloqueo"))
    activo: Mapped[bool] = mapped_column(default=True)
    vence_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_reserva_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("item_reserva.id"))
    calendario_externo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("calendario_externo.id", ondelete="CASCADE")
    )
    nota: Mapped[str | None] = mapped_column(String(200))
