import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Dinero, IdMixin, Porcentaje, TiempoMixin, pg_enum
from app.models.enums import QuienPaga


class ReglaComision(IdMixin, TiempoMixin, Base):
    """Ver docs/00 §7. Toda dimensión nula significa 'cualquiera'."""

    __tablename__ = "regla_comision"
    __table_args__ = (
        Index(
            "uq_regla_comision_default",
            "es_default",
            unique=True,
            postgresql_where=text("es_default"),
        ),
    )

    nombre: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str | None]
    activa: Mapped[bool] = mapped_column(default=True)
    es_default: Mapped[bool] = mapped_column(default=False)
    prioridad: Mapped[int] = mapped_column(default=0)
    vigente_desde: Mapped[date | None]
    vigente_hasta: Mapped[date | None]

    # Dimensiones
    tipo_servicio_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tipo_servicio.id"))
    subtipo_servicio_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subtipo_servicio.id"))
    provincia_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("provincia.id"))
    localidad_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("localidad.id"))
    zona_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zona.id"))
    prestador_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prestador.id"))
    publicacion_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("publicacion.id"))
    servicio_desde: Mapped[date | None]  # temporada
    servicio_hasta: Mapped[date | None]
    creacion_desde: Mapped[date | None]  # promoción
    creacion_hasta: Mapped[date | None]
    monto_desde: Mapped[Dinero | None]
    monto_hasta: Mapped[Dinero | None]
    antiguedad_meses_desde: Mapped[int | None] = mapped_column(SmallInteger)
    antiguedad_meses_hasta: Mapped[int | None] = mapped_column(SmallInteger)
    categoria_prestador: Mapped[str | None] = mapped_column(String(40))

    # Valor
    porcentaje: Mapped[Porcentaje] = mapped_column(default=Decimal(0))
    monto_fijo: Mapped[Dinero] = mapped_column(default=Decimal(0))
    minimo: Mapped[Dinero | None]
    maximo: Mapped[Dinero | None]
    quien_paga: Mapped[QuienPaga] = mapped_column(
        pg_enum(QuienPaga, "quien_paga"), default=QuienPaga.PRESTADOR
    )
    porcentaje_viajero: Mapped[Porcentaje] = mapped_column(default=Decimal(0))  # si es dividido
    iva_incluido: Mapped[bool] = mapped_column(default=False)

    creado_por_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"))


class ReglaComisionHistorial(IdMixin, Base):
    __tablename__ = "regla_comision_historial"

    regla_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("regla_comision.id"), index=True)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"))
    accion: Mapped[str] = mapped_column(String(20))  # alta | edicion | baja
    antes: Mapped[dict | None] = mapped_column(JSONB)
    despues: Mapped[dict | None] = mapped_column(JSONB)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class ComisionAplicada(IdMixin, Base):
    """Snapshot inmutable de la regla y los montos al momento de la reserva."""

    __tablename__ = "comision_aplicada"

    item_reserva_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("item_reserva.id", ondelete="CASCADE"), unique=True
    )
    regla_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("regla_comision.id"))
    regla_snapshot: Mapped[dict] = mapped_column(JSONB)
    base: Mapped[Dinero]
    comision_neta: Mapped[Dinero]
    iva: Mapped[Dinero]
    comision_total: Mapped[Dinero]
    cargo_viajero: Mapped[Dinero]
    descuento_prestador: Mapped[Dinero]

    item_reserva: Mapped["ItemReserva"] = relationship(back_populates="comision")  # noqa: F821
