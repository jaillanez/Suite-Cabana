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
