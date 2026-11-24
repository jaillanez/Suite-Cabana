"""Excursiones y actividades: se reservan por turno y cupo (docs/05).

Tres piezas:

- `TurnoExcursion`: la regla que se repite ("martes y jueves a las 9, 12 lugares").
- `SalidaExcursion`: una salida concreta de un día. Se crea recién cuando hace
  falta (alguien toma lugar, el prestador la suspende o le cambia el cupo); las
  demás se calculan del turno. Guarda su propia hora y su cupo: si el prestador
  cambia el turno, lo que ya se vendió no se mueve.
- `CupoTomado`: los lugares que ocupa una retención o una reserva.

Cero sobreventa (CLAUDE.md §6): `ocupados` no puede pasar de `cupo` por una
restricción de la base, y se suma con un UPDATE sobre la fila de la salida, que
Postgres serializa. Dos transacciones que piden los últimos lugares a la vez no
pueden pasar las dos: la segunda ve el valor de la primera y choca con la
restricción.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Dinero, IdMixin, TiempoMixin, pg_enum
from app.models.enums import OrigenBloqueo

#: Ninguna salida dura más que esto (una travesía de varios días entra).
DURACION_MAXIMA_MINUTOS = 14 * 24 * 60


class TurnoExcursion(IdMixin, TiempoMixin, Base):
    """Un turno que se repite: días de la semana, hora de salida, duración y cupo.

    `dias_semana` va de 0 (lunes) a 6 (domingo). `desde` y `hasta`, si están,
    limitan la temporada en la que el turno sale.
    """

    __tablename__ = "turno_excursion"
    __table_args__ = (
        CheckConstraint("cupo > 0", name="cupo_positivo"),
        CheckConstraint(
            f"duracion_minutos BETWEEN 15 AND {DURACION_MAXIMA_MINUTOS}",
            name="duracion_rango",
        ),
        CheckConstraint(
            "cardinality(dias_semana) > 0 AND dias_semana <@ ARRAY[0,1,2,3,4,5,6]::smallint[]",
            name="dias_validos",
        ),
        CheckConstraint("hasta IS NULL OR desde IS NULL OR hasta >= desde", name="temporada"),
        CheckConstraint("minimo_personas BETWEEN 1 AND cupo", name="minimo_rango"),
        CheckConstraint("aviso_minimo_horas BETWEEN 0 AND 720", name="aviso_rango"),
    )

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    dias_semana: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger))
    hora_inicio: Mapped[time]
    duracion_minutos: Mapped[int]
    cupo: Mapped[int] = mapped_column(SmallInteger)
    desde: Mapped[date | None]
    hasta: Mapped[date | None]
    #: Lo decide cada prestador (docs/05 §2): con menos personas anotadas que
    #: esto, a `aviso_minimo_horas` de la salida se cancela sola. 1 = sin mínimo.
    minimo_personas: Mapped[int] = mapped_column(SmallInteger, default=1)
    aviso_minimo_horas: Mapped[int] = mapped_column(SmallInteger, default=24)
    activo: Mapped[bool] = mapped_column(default=True)

    unidad: Mapped[Unidad] = relationship()  # noqa: F821


class SalidaExcursion(IdMixin, TiempoMixin, Base):
    """Una salida de un día. Con `turno_id` nulo es una salida extra, fuera del turno."""

    __tablename__ = "salida_excursion"
    __table_args__ = (
        # La garantía contra la sobreventa: la base, no un `if`.
        CheckConstraint("ocupados >= 0 AND ocupados <= cupo", name="cupo_no_se_pasa"),
        CheckConstraint("cupo > 0", name="cupo_positivo"),
        CheckConstraint("fin_en > inicio_en", name="horario_valido"),
        CheckConstraint("minimo_personas >= 1", name="minimo_positivo"),
        # Un turno sale una vez por día. Las extras (turno nulo) no chocan entre sí.
        UniqueConstraint("turno_id", "fecha", name="uq_salida_excursion_turno_fecha"),
        Index("ix_salida_excursion_unidad_fecha", "unidad_id", "fecha"),
    )

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"))
    turno_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("turno_excursion.id"))
    #: El día de la salida en hora argentina: es lo que se busca y lo que se muestra.
    fecha: Mapped[date]
    inicio_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fin_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cupo: Mapped[int] = mapped_column(SmallInteger)
    ocupados: Mapped[int] = mapped_column(SmallInteger, default=0)
    #: Suspendida por el prestador (lluvia, feriado, sin guía): no se vende.
    suspendida: Mapped[bool] = mapped_column(default=False)
    motivo: Mapped[str | None] = mapped_column(String(200))
    #: Copiados del turno al crear la salida: cambiar el turno no cambia el trato
    #: con quien ya reservó.
    minimo_personas: Mapped[int] = mapped_column(SmallInteger, default=1)
    aviso_minimo_horas: Mapped[int] = mapped_column(SmallInteger, default=24)
    #: Se llegó al mínimo a tiempo: la salida va, aunque después alguien cancele.
    sale_confirmada: Mapped[bool] = mapped_column(default=False)

    turno: Mapped[TurnoExcursion | None] = relationship()


class CupoTomado(IdMixin, TiempoMixin, Base):
    """Lugares de una salida que ocupa alguien: una retención mientras paga, una
    reserva, o una venta que el prestador hizo por fuera."""

    __tablename__ = "cupo_tomado"
    __table_args__ = (
        CheckConstraint("personas > 0", name="personas_positivas"),
        Index("ix_cupo_tomado_vence", "vence_en", postgresql_where=text("activo")),
    )

    salida_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("salida_excursion.id"), index=True)
    personas: Mapped[int] = mapped_column(SmallInteger)
    origen: Mapped[OrigenBloqueo] = mapped_column(
        pg_enum(OrigenBloqueo, "origen_bloqueo", crear=False)
    )
    activo: Mapped[bool] = mapped_column(default=True)
    vence_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_reserva_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("item_reserva.id"))
    nota: Mapped[str | None] = mapped_column(String(200))

    salida: Mapped[SalidaExcursion] = relationship()


class PrecioPasajero(IdMixin, Base):
    """Un precio por tipo de pasajero: "Adulto", "Menor de 3 a 12 años", "Jubilado".

    Cada prestador define los suyos (docs/05 §2): la plataforma no fija edades ni
    quién es jubilado. `edad_desde` y `edad_hasta` son informativas, para mostrar;
    `ocupa_lugar` en False es para quien no usa cupo (un bebé en brazos).
    """

    __tablename__ = "precio_pasajero"
    __table_args__ = (
        CheckConstraint("precio >= 0", name="precio_no_negativo"),
        CheckConstraint(
            "edad_desde IS NULL OR edad_hasta IS NULL OR edad_hasta >= edad_desde",
            name="edades",
        ),
    )

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(60))
    descripcion: Mapped[str | None] = mapped_column(String(200))
    edad_desde: Mapped[int | None] = mapped_column(SmallInteger)
    edad_hasta: Mapped[int | None] = mapped_column(SmallInteger)
    precio: Mapped[Dinero]
    ocupa_lugar: Mapped[bool] = mapped_column(default=True)
    orden: Mapped[int] = mapped_column(SmallInteger, default=0)
    activo: Mapped[bool] = mapped_column(default=True)
