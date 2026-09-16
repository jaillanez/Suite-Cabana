from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TiempoMixin


class Usuario(IdMixin, TiempoMixin, Base):
    __tablename__ = "usuario"

    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    hash_password: Mapped[str | None]  # nulo si ingresa solo con Google
    google_sub: Mapped[str | None] = mapped_column(unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    apellido: Mapped[str] = mapped_column(String(120))
    telefono: Mapped[str | None] = mapped_column(String(30))
    email_verificado: Mapped[bool] = mapped_column(default=False)
    telefono_verificado: Mapped[bool] = mapped_column(default=False)
    es_viajero: Mapped[bool] = mapped_column(default=True)
    es_prestador: Mapped[bool] = mapped_column(default=False)
    es_operador: Mapped[bool] = mapped_column(default=False)
    activo: Mapped[bool] = mapped_column(default=True)

    prestador: Mapped["Prestador | None"] = relationship(back_populates="usuario")  # noqa: F821
