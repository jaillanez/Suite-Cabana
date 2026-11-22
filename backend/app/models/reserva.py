import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Dinero, IdMixin, TiempoMixin, pg_enum
from app.models.enums import EstadoReserva, TipoPago


class Reserva(IdMixin, TiempoMixin, Base):
    __tablename__ = "reserva"

    codigo: Mapped[str] = mapped_column(String(12), unique=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    estado: Mapped[EstadoReserva] = mapped_column(
        pg_enum(EstadoReserva, "estado_reserva"),
        default=EstadoReserva.PENDIENTE_PAGO,
        index=True,
    )
    moneda: Mapped[str] = mapped_column(String(3), default="ARS")
    total: Mapped[Dinero]  # lo que paga el viajero (incluye cargo de servicio)
    monto_sena: Mapped[Dinero | None]
    vence_pago_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vence_aprobacion_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    politica_cancelacion: Mapped[dict | None] = mapped_column(JSONB)  # snapshot
    # docs/01 §5 R11: también se aceptan al reservar.
    acepto_terminos_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version_terminos: Mapped[str | None] = mapped_column(String(20))
    cancelada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_cancelacion: Mapped[str | None]

    items: Mapped[list["ItemReserva"]] = relationship(back_populates="reserva")
    pagos: Mapped[list["Pago"]] = relationship(back_populates="reserva")


class ItemReserva(IdMixin, Base):
    """Un servicio dentro de la reserva. En Fase 1 hay uno; en Fase 3, varios (paquetes)."""

    __tablename__ = "item_reserva"
    __table_args__ = (CheckConstraint("fecha_fin >= fecha_inicio", name="fechas_validas"),)

    reserva_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reserva.id", ondelete="CASCADE"), index=True
    )
    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    prestador_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prestador.id"), index=True)
    fecha_inicio: Mapped[date]
    fecha_fin: Mapped[date]
    # Solo para lo que se reserva por horario (salones): el rango exacto del
    # evento. `fecha_inicio` es el día del evento, aunque termine pasada la medianoche.
    inicio_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fin_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    adultos: Mapped[int] = mapped_column(SmallInteger, default=1)
    menores: Mapped[int] = mapped_column(SmallInteger, default=0)
    mascotas: Mapped[int] = mapped_column(SmallInteger, default=0)
    desglose: Mapped[dict] = mapped_column(JSONB)  # noches, limpieza, extras, descuentos
    subtotal: Mapped[Dinero]  # precio del prestador

    reserva: Mapped[Reserva] = relationship(back_populates="items")
    unidad: Mapped["Unidad"] = relationship()  # noqa: F821
    comision: Mapped["ComisionAplicada | None"] = relationship(  # noqa: F821
        back_populates="item_reserva"
    )


class Pago(IdMixin, TiempoMixin, Base):
    __tablename__ = "pago"
    # El id externo solo tiene que ser único dentro de su pasarela. Declarado acá
    # y no solo en la migración: lo que no está en el modelo, autogenerate lo borra.
    __table_args__ = (UniqueConstraint("pasarela", "id_externo", name="uq_pago_pasarela"),)

    reserva_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reserva.id"), index=True)
    tipo: Mapped[TipoPago] = mapped_column(pg_enum(TipoPago, "tipo_pago"))
    pasarela: Mapped[str] = mapped_column(String(40), default="mercadopago")
    id_externo: Mapped[str | None] = mapped_column(String(80))
    id_preferencia: Mapped[str | None] = mapped_column(String(80))
    estado: Mapped[str] = mapped_column(String(30))
    monto: Mapped[Dinero]
    monto_prestador: Mapped[Dinero]
    monto_comision: Mapped[Dinero]
    iva_comision: Mapped[Dinero]
    datos: Mapped[dict | None] = mapped_column(JSONB)

    reserva: Mapped[Reserva] = relationship(back_populates="pagos")


class NotificacionPago(IdMixin, TiempoMixin, Base):
    """Webhook de una pasarela, registrado para procesarlo una sola vez.

    La unicidad es por (pasarela, id_externo): dos billeteras distintas pueden
    usar el mismo id sin pisarse.
    """

    __tablename__ = "notificacion_pago"
    __table_args__ = (UniqueConstraint("pasarela", "id_externo"),)

    pasarela: Mapped[str] = mapped_column(String(40), index=True)
    id_externo: Mapped[str] = mapped_column(String(80))
    topico: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB)
    procesada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None]


class Resena(IdMixin, TiempoMixin, Base):
    __tablename__ = "resena"
    __table_args__ = (CheckConstraint("puntaje BETWEEN 1 AND 5", name="puntaje_rango"),)

    reserva_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reserva.id"), unique=True)
    publicacion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publicacion.id"), index=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    puntaje: Mapped[int] = mapped_column(SmallInteger)
    comentario: Mapped[str | None]
    respuesta_prestador: Mapped[str | None]
    visible: Mapped[bool] = mapped_column(default=True)
