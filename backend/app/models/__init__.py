"""Importa todos los modelos para que Alembic los detecte."""

from app.models.base import Base
from app.models.catalogo import Comodidad, SubtipoServicio, TipoServicio
from app.models.comision import ComisionAplicada, ReglaComision, ReglaComisionHistorial
from app.models.notificacion import Favorito, Notificacion
from app.models.politica import PoliticaCancelacion
from app.models.prestador import Prestador
from app.models.publicacion import (
    BloqueoFecha,
    CalendarioExterno,
    Foto,
    Publicacion,
    ReservaExterna,
    Tarifa,
    Unidad,
    publicacion_comodidad,
)
from app.models.reserva import ItemReserva, NotificacionPago, Pago, Resena, Reserva
from app.models.ubicacion import Localidad, Provincia, Zona
from app.models.usuario import Usuario

__all__ = [
    "Base",
    "BloqueoFecha",
    "CalendarioExterno",
    "ComisionAplicada",
    "Favorito",
    "Comodidad",
    "Foto",
    "ItemReserva",
    "Localidad",
    "Notificacion",
    "NotificacionPago",
    "Pago",
    "PoliticaCancelacion",
    "Prestador",
    "Provincia",
    "Publicacion",
    "ReglaComision",
    "ReglaComisionHistorial",
    "Resena",
    "Reserva",
    "ReservaExterna",
    "SubtipoServicio",
    "Tarifa",
    "TipoServicio",
    "Unidad",
    "Usuario",
    "Zona",
    "publicacion_comodidad",
]
