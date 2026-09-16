import uuid

from geoalchemy2 import Geography
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin


class Provincia(IdMixin, Base):
    __tablename__ = "provincia"

    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)

    localidades: Mapped[list["Localidad"]] = relationship(back_populates="provincia")


class Localidad(IdMixin, Base):
    __tablename__ = "localidad"
    __table_args__ = (
        UniqueConstraint("provincia_id", "slug"),
        Index("ix_localidad_ubicacion", "ubicacion", postgresql_using="gist"),
    )

    provincia_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provincia.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120))
    ubicacion = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=True)

    provincia: Mapped[Provincia] = relationship(back_populates="localidades")
    zonas: Mapped[list["Zona"]] = relationship(back_populates="localidad")


class Zona(IdMixin, Base):
    __tablename__ = "zona"

    localidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("localidad.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))

    localidad: Mapped[Localidad] = relationship(back_populates="zonas")
