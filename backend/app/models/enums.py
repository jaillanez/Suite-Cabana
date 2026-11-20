from enum import StrEnum


class ModoReserva(StrEnum):
    NOCHES = "noches"  # alojamiento
    TURNO_CUPO = "turno_cupo"  # excursiones (Fase 2)
    HORARIO = "horario"  # gastronomía (Fase 2)
    TRAMO = "tramo"  # traslados (Fase 2)


class EstadoPublicacion(StrEnum):
    BORRADOR = "borrador"
    EN_REVISION = "en_revision"
    APROBADA = "aprobada"
    PAUSADA = "pausada"
    RECHAZADA = "rechazada"


class OrigenBloqueo(StrEnum):
    MANUAL = "manual"
    ICAL = "ical"
    RETENCION = "retencion"  # fechas retenidas mientras el viajero paga
    RESERVA = "reserva"
    #: Vendida fuera de la plataforma: por Despegar, por WhatsApp, por teléfono.
    #: No lleva comisión —no la vendimos nosotros— pero sí ocupa la noche.
    EXTERNA = "externa"


class OrigenReservaExterna(StrEnum):
    """De dónde entró una venta que no pasó por Suite Cabaña."""

    PARTICULAR = "particular"  # WhatsApp, teléfono, un huésped que vuelve
    CORREO = "correo"  # la leímos de un mail de la plataforma


class EstadoReservaExterna(StrEnum):
    #: La entendimos entera y ya bloqueó las fechas.
    CONFIRMADA = "confirmada"
    #: Algo no se entendió del mail: espera que el anfitrión la revise. No bloquea.
    POR_REVISAR = "por_revisar"
    #: El anfitrión la descartó, o la venta se cayó.
    DESCARTADA = "descartada"


class EstadoReserva(StrEnum):
    PENDIENTE_PAGO = "pendiente_pago"
    PENDIENTE_APROBACION = "pendiente_aprobacion"
    CONFIRMADA = "confirmada"
    CANCELADA = "cancelada"
    COMPLETADA = "completada"
    EN_RECLAMO = "en_reclamo"


class TipoPago(StrEnum):
    TOTAL = "total"
    SENA = "sena"
    SALDO = "saldo"
    REINTEGRO = "reintegro"


class QuienPaga(StrEnum):
    PRESTADOR = "prestador"
    VIAJERO = "viajero"
    DIVIDIDO = "dividido"


class CanalNotificacion(StrEnum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class EstadoNotificacion(StrEnum):
    PENDIENTE = "pendiente"
    ENVIADA = "enviada"
    FALLIDA = "fallida"
    DESCARTADA = "descartada"  # el canal no está configurado
