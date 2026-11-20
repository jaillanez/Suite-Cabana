import uuid
from datetime import date

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TiempoMixin


class Prestador(IdMixin, TiempoMixin, Base):
    __tablename__ = "prestador"

    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), unique=True)
    razon_social: Mapped[str] = mapped_column(String(200))
    cuit: Mapped[str | None] = mapped_column(String(13), unique=True)
    condicion_iva: Mapped[str | None] = mapped_column(String(40))
    categoria: Mapped[str | None] = mapped_column(String(40))  # usada por reglas de comisión
    fecha_alta: Mapped[date] = mapped_column(default=date.today)
    verificado: Mapped[bool] = mapped_column(default=False)
    es_demo: Mapped[bool] = mapped_column(default=False)  # datos de ejemplo, nunca reales

    # Mercado Pago (OAuth marketplace)
    mp_user_id: Mapped[str | None] = mapped_column(String(40))
    mp_access_token: Mapped[str | None]  # cifrar antes de producción
    mp_refresh_token: Mapped[str | None]

    # Seña configurable (porcentaje del total); nulo = pago total
    porcentaje_sena: Mapped[int | None]

    usuario: Mapped["Usuario"] = relationship(back_populates="prestador")  # noqa: F821
    publicaciones: Mapped[list["Publicacion"]] = relationship(  # noqa: F821
        back_populates="prestador"
    )

    @property
    def puede_publicar(self) -> bool:
        return bool(self.cuit and self.condicion_iva and self.mp_user_id)
