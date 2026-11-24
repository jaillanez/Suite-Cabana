"""Importa todos los modelos para que Alembic los detecte."""

from app.models.base import Base
from app.models.catalogo import (
    Comodidad,
    SubtipoServicio,
    TipoServicio,
    comodidad_tipo_servicio,
)
from app.models.comision import ComisionAplicada, ReglaComision, ReglaComisionHistorial
from app.models.excursion import CupoTomado, PrecioPasajero, SalidaExcursion, TurnoExcursion
from app.models.notificacion import Favorito, Notificacion
from app.models.politica import PoliticaCancelacion
from app.models.prestador import Prestador
from app.models.publicacion import (
    Adicional,
    BloqueoFecha,
    BloqueoHorario,
    CalendarioExterno,
    Foto,
    FranjaHoraria,
    Publicacion,
    ReservaExterna,
    Tarifa,
    TarifaHoraria,
    Unidad,
    publicacion_comodidad,
)
from app.models.reserva import ItemReserva, NotificacionPago, Pago, Resena, Reserva
from app.models.ubicacion import Localidad, Provincia, Zona
from app.models.usuario import Usuario

__all__ = [
    "Adicional",
    "FranjaHoraria",
    "TarifaHoraria",
    "Base",
    "BloqueoFecha",
    "BloqueoHorario",
    "CalendarioExterno",
    "ComisionAplicada",
    "CupoTomado",
    "Favorito",
    "Comodidad",
    "comodidad_tipo_servicio",
    "Foto",
    "ItemReserva",
    "Localidad",
    "Notificacion",
    "NotificacionPago",
    "Pago",
    "PoliticaCancelacion",
    "PrecioPasajero",
    "Prestador",
    "Provincia",
    "Publicacion",
    "ReglaComision",
    "ReglaComisionHistorial",
    "Resena",
    "Reserva",
    "ReservaExterna",
    "SalidaExcursion",
    "SubtipoServicio",
    "Tarifa",
    "TipoServicio",
    "TurnoExcursion",
    "Unidad",
    "Usuario",
    "Zona",
    "publicacion_comodidad",
]
