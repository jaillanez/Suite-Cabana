import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TiempoMixin


class Prestador(IdMixin, TiempoMixin, Base):
    __tablename__ = "prestador"
    __table_args__ = (
        CheckConstraint(
            "porcentaje_sena IS NULL OR porcentaje_sena BETWEEN 0 AND 100",
            name="porcentaje_sena_rango",
        ),
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), unique=True)
    razon_social: Mapped[str] = mapped_column(String(200))
    cuit: Mapped[str | None] = mapped_column(String(13), unique=True)
    condicion_iva: Mapped[str | None] = mapped_column(String(40))
    categoria: Mapped[str | None] = mapped_column(String(40))  # usada por reglas de comisión
    fecha_alta: Mapped[date] = mapped_column(default=date.today)
    verificado: Mapped[bool] = mapped_column(default=False)
    es_demo: Mapped[bool] = mapped_column(default=False)  # datos de ejemplo, nunca reales

    # Mercado Pago. `mp_access_token` va cifrado (app/services/cifrado.py): nunca
    # se lee directo, sino con app/services/cuenta_cobro.py.
    mp_user_id: Mapped[str | None] = mapped_column(String(40))
    mp_cuenta: Mapped[str | None] = mapped_column(String(200))  # cómo se la mostramos
    mp_access_token: Mapped[str | None]
    mp_refresh_token: Mapped[str | None]  # cifrado, como el token
    #: Conectada con el botón (OAuth de la aplicación de la plataforma): solo así
    #: Mercado Pago deja retener la comisión en el mismo pago. Una credencial
    #: pegada a mano cobra, pero la comisión se factura aparte.
    mp_oauth: Mapped[bool] = mapped_column(default=False)
    mp_token_vence_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Seña configurable (porcentaje del total); nulo = pago total
    porcentaje_sena: Mapped[int | None]

    usuario: Mapped["Usuario"] = relationship(back_populates="prestador")  # noqa: F821
    publicaciones: Mapped[list["Publicacion"]] = relationship(  # noqa: F821
        back_populates="prestador"
    )

    @property
    def puede_publicar(self) -> bool:
        return bool(self.cuit and self.condicion_iva and self.mp_user_id)
