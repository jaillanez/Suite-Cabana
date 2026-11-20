import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TiempoMixin, pg_enum
from app.models.enums import CanalNotificacion, EstadoNotificacion


class Notificacion(IdMixin, TiempoMixin, Base):
    """Buzón de salida: toda notificación se registra antes de enviarse.

    Guardar primero y enviar después es lo que permite reintentar sin duplicar y
    saber qué se le dijo a quién. Un envío que se pierde en el aire no se puede
    auditar ni reclamar.
    """

    __tablename__ = "notificacion"
    __table_args__ = (
        Index("ix_notificacion_pendientes", "estado", "creado_en"),
    )

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    reserva_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reserva.id"), index=True)
    canal: Mapped[CanalNotificacion] = mapped_column(
        pg_enum(CanalNotificacion, "canal_notificacion")
    )
    evento: Mapped[str] = mapped_column(String(40), index=True)
    destino: Mapped[str] = mapped_column(String(254))
    asunto: Mapped[str | None] = mapped_column(String(200))
    cuerpo: Mapped[str]
    estado: Mapped[EstadoNotificacion] = mapped_column(
        pg_enum(EstadoNotificacion, "estado_notificacion"),
        default=EstadoNotificacion.PENDIENTE,
    )
    intentos: Mapped[int] = mapped_column(SmallInteger, default=0)
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None]
    datos: Mapped[dict | None] = mapped_column(JSONB)


class Favorito(IdMixin, TiempoMixin, Base):
    """Alojamiento guardado por un viajero (docs/01 §4, historia 8)."""

    __tablename__ = "favorito"
    __table_args__ = (UniqueConstraint("usuario_id", "publicacion_id"),)

    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    publicacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publicacion.id", ondelete="CASCADE"), index=True
    )
