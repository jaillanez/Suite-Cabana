from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin


class PoliticaCancelacion(IdMixin, Base):
    """Plantillas flexible / moderada / estricta, editables por el operador.

    tramos: [{"dias_antes": 7, "porcentaje_reintegro": 100}, {"dias_antes": 2, ...}]
    """

    __tablename__ = "politica_cancelacion"

    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    descripcion: Mapped[str | None]
    tramos: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    activa: Mapped[bool] = mapped_column(default=True)
