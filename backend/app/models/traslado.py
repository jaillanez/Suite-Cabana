"""Traslados (docs/06): lugares con nombre, tramos fijos y la tarifa de cada vehículo.

El vehículo es una `Unidad`: `capacidad` son los pasajeros, `equipaje` las valijas
y `preparacion_minutos` lo que queda ocupado entre un viaje y otro. Lo que está
ocupado va en `bloqueo_horario`, como los salones: la base impide que dos viajes
del mismo vehículo se pisen.
"""

from __future__ import annotations

import uuid
from datetime import time
from decimal import Decimal

from geoalchemy2 import Geography
from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Dinero, IdMixin, Porcentaje


class LugarTraslado(IdMixin, Base):
    """Un punto con nombre de un prestador: "Aeropuerto de San Juan", "Centro".

    `es_base` marca de dónde salen los vehículos: el radio de la tarifa por km se
    mide desde ahí (si no hay, desde la ubicación de la publicación).
    """

    __tablename__ = "lugar_traslado"
    __table_args__ = (
        UniqueConstraint("publicacion_id", "nombre", name="uq_lugar_traslado_nombre"),
    )

    publicacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publicacion.id"), index=True
    )
    nombre: Mapped[str] = mapped_column(String(120))
    ubicacion = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    es_base: Mapped[bool] = mapped_column(default=False)
    activo: Mapped[bool] = mapped_column(default=True)


class TramoTraslado(IdMixin, Base):
    """Un recorrido fijo de un vehículo con su precio: "Aeropuerto → Centro, $ 25.000"."""

    __tablename__ = "tramo_traslado"
    __table_args__ = (
        UniqueConstraint("unidad_id", "origen_id", "destino_id", name="uq_tramo_traslado"),
        CheckConstraint("origen_id <> destino_id", name="origen_distinto_destino"),
        CheckConstraint("precio > 0", name="precio_positivo"),
        CheckConstraint("duracion_minutos BETWEEN 5 AND 2880", name="duracion_rango"),
    )

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    origen_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lugar_traslado.id"))
    destino_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lugar_traslado.id"))
    precio: Mapped[Dinero]
    #: True: el precio es por pasajero. False: por el vehículo entero.
    por_persona: Mapped[bool] = mapped_column(default=False)
    duracion_minutos: Mapped[int] = mapped_column(SmallInteger)
    #: El mismo precio y duración a la vuelta (Centro → Aeropuerto).
    ambos_sentidos: Mapped[bool] = mapped_column(default=True)
    activo: Mapped[bool] = mapped_column(default=True)

    origen: Mapped[LugarTraslado] = relationship(foreign_keys=[origen_id])
    destino: Mapped[LugarTraslado] = relationship(foreign_keys=[destino_id])


class TarifaTraslado(IdMixin, Base):
    """La tarifa por km y las reglas de un vehículo. Sin fila, rigen los valores por
    defecto: sin km, sin recargo, vuelve a la base, 12 h de anticipación."""

    __tablename__ = "tarifa_traslado"
    __table_args__ = (
        CheckConstraint("precio_km IS NULL OR precio_km > 0", name="precio_km_positivo"),
        CheckConstraint("bajada >= 0 AND minimo >= 0", name="montos_no_negativos"),
        CheckConstraint("radio_km IS NULL OR radio_km > 0", name="radio_positivo"),
        CheckConstraint("factor_ruta BETWEEN 1 AND 3", name="factor_ruta_rango"),
        CheckConstraint("velocidad_kmh BETWEEN 10 AND 150", name="velocidad_rango"),
        CheckConstraint(
            "recargo_nocturno_porcentaje BETWEEN 0 AND 200", name="recargo_rango"
        ),
        CheckConstraint(
            "anticipacion_minima_horas BETWEEN 0 AND 720", name="anticipacion_rango"
        ),
    )

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), unique=True)
    #: Nulo: este vehículo no cobra por km, solo por tramos fijos.
    precio_km: Mapped[Dinero | None]
    bajada: Mapped[Dinero] = mapped_column(default=Decimal(0))
    minimo: Mapped[Dinero] = mapped_column(default=Decimal(0))
    #: Hasta dónde va desde la base, en línea recta. Nulo: sin límite.
    radio_km: Mapped[int | None] = mapped_column(SmallInteger)
    factor_ruta: Mapped[Porcentaje] = mapped_column(default=Decimal("1.3"))
    velocidad_kmh: Mapped[int] = mapped_column(SmallInteger, default=60)
    recargo_nocturno_desde: Mapped[time | None]
    recargo_nocturno_hasta: Mapped[time | None]
    recargo_nocturno_porcentaje: Mapped[Porcentaje] = mapped_column(default=Decimal(0))
    vuelve_a_base: Mapped[bool] = mapped_column(default=True)
    anticipacion_minima_horas: Mapped[int] = mapped_column(SmallInteger, default=12)
