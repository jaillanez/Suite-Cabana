import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, pg_enum
from app.models.enums import ModoReserva


class TipoServicio(IdMixin, Base):
    """alojamiento | excursion | gastronomia | traslado. Alojamiento es solo el primero."""

    __tablename__ = "tipo_servicio"

    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    modo_reserva: Mapped[ModoReserva] = mapped_column(pg_enum(ModoReserva, "modo_reserva"))
    activo: Mapped[bool] = mapped_column(default=True)

    subtipos: Mapped[list["SubtipoServicio"]] = relationship(back_populates="tipo")


class SubtipoServicio(IdMixin, Base):
    """Ej.: cabaña, departamento, hotel; cabalgata, bodega."""

    __tablename__ = "subtipo_servicio"

    tipo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tipo_servicio.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))

    tipo: Mapped[TipoServicio] = relationship(back_populates="subtipos")


class Comodidad(IdMixin, Base):
    """Pileta, WiFi, mascotas, cochera, etc."""

    __tablename__ = "comodidad"

    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    icono: Mapped[str | None] = mapped_column(String(40))
