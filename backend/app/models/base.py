import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from sqlalchemy import DateTime, Enum, MetaData, Numeric, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Dinero = Annotated[Decimal, mapped_column(Numeric(14, 2))]
Porcentaje = Annotated[Decimal, mapped_column(Numeric(7, 4))]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TiempoMixin:
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def pg_enum(enum_cls: type[StrEnum], nombre: str, crear: bool = True) -> Enum:
    """Enum de PostgreSQL que guarda los valores ('pendiente_pago'), no los nombres.

    `crear=False` cuando otra tabla ya define el mismo tipo: se reutiliza.
    """
    return Enum(
        enum_cls,
        name=nombre,
        values_callable=lambda e: [m.value for m in e],
        create_type=crear,
    )
