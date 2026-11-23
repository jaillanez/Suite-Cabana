import uuid
from datetime import date, datetime, time
from decimal import Decimal

from geoalchemy2 import Geography
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import (
    DATERANGE,
    JSONB,
    TSTZRANGE,
    ExcludeConstraint,
    Range,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Dinero, IdMixin, Porcentaje, TiempoMixin, pg_enum
from app.models.enums import (
    EstadoPublicacion,
    EstadoReservaExterna,
    OrigenBloqueo,
    OrigenReservaExterna,
)

publicacion_comodidad = Table(
    "publicacion_comodidad",
    Base.metadata,
    Column("publicacion_id", ForeignKey("publicacion.id", ondelete="CASCADE"), primary_key=True),
    Column("comodidad_id", ForeignKey("comodidad.id"), primary_key=True),
)


class Publicacion(IdMixin, TiempoMixin, Base):
    """Ficha visible. Ej.: 'Complejo Los Álamos'."""

    __tablename__ = "publicacion"
    __table_args__ = (
        Index("ix_publicacion_ubicacion", "ubicacion", postgresql_using="gist"),
        Index("ix_publicacion_es_demo", "es_demo"),
        CheckConstraint(
            "porcentaje_sena IS NULL OR porcentaje_sena BETWEEN 0 AND 100",
            name="porcentaje_sena_rango",
        ),
    )

    prestador_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prestador.id"), index=True)
    tipo_servicio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tipo_servicio.id"))
    subtipo_servicio_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("subtipo_servicio.id"))
    titulo: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(170), unique=True)
    descripcion: Mapped[str]
    reglas_casa: Mapped[str | None]
    estado: Mapped[EstadoPublicacion] = mapped_column(
        pg_enum(EstadoPublicacion, "estado_publicacion"),
        default=EstadoPublicacion.BORRADOR,
        index=True,
    )
    motivo_rechazo: Mapped[str | None]

    localidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("localidad.id"), index=True)
    zona_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("zona.id"))
    direccion: Mapped[str | None] = mapped_column(String(200))
    ubicacion = mapped_column(Geography("POINT", srid=4326, spatial_index=False), nullable=True)

    hora_ingreso: Mapped[time | None]
    hora_salida: Mapped[time | None]
    confirmacion_inmediata: Mapped[bool] = mapped_column(default=True)
    # Seña de esta publicación (porcentaje del total). Nula: la del prestador; si
    # tampoco tiene, se cobra el total. Los salones suelen trabajar con seña.
    porcentaje_sena: Mapped[int | None] = mapped_column(SmallInteger)
    politica_cancelacion_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("politica_cancelacion.id")
    )
    es_demo: Mapped[bool] = mapped_column(default=False)  # datos de ejemplo, nunca reales
    calificacion_promedio: Mapped[float | None]
    cantidad_resenas: Mapped[int] = mapped_column(default=0)

    prestador: Mapped["Prestador"] = relationship(back_populates="publicaciones")  # noqa: F821
    localidad: Mapped["Localidad"] = relationship()  # noqa: F821
    zona: Mapped["Zona | None"] = relationship()  # noqa: F821
    subtipo: Mapped["SubtipoServicio | None"] = relationship()  # noqa: F821
    tipo_servicio: Mapped["TipoServicio"] = relationship()  # noqa: F821
    politica_cancelacion: Mapped["PoliticaCancelacion | None"] = relationship()  # noqa: F821
    unidades: Mapped[list["Unidad"]] = relationship(back_populates="publicacion")
    fotos: Mapped[list["Foto"]] = relationship(order_by="Foto.orden")
    comodidades: Mapped[list["Comodidad"]] = relationship(  # noqa: F821
        secondary=publicacion_comodidad
    )


class Foto(IdMixin, Base):
    __tablename__ = "foto"

    publicacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publicacion.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str]
    orden: Mapped[int] = mapped_column(default=0)
    descripcion: Mapped[str | None] = mapped_column(String(200))


class Unidad(IdMixin, TiempoMixin, Base):
    """Lo que realmente se reserva. Ej.: 'Cabaña 2, 4 personas'."""

    __tablename__ = "unidad"

    publicacion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publicacion.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    capacidad: Mapped[int] = mapped_column(SmallInteger)
    capacidad_base: Mapped[int | None] = mapped_column(SmallInteger)  # sobre esta, persona extra
    # Salones: `capacidad` es el máximo de pie (cóctel); esta, con todos sentados.
    capacidad_sentados: Mapped[int | None] = mapped_column(SmallInteger)
    # Salones: minutos que quedan bloqueados después de cada evento (limpieza).
    preparacion_minutos: Mapped[int] = mapped_column(SmallInteger, default=0)
    activa: Mapped[bool] = mapped_column(default=True)

    cargo_limpieza: Mapped[Dinero] = mapped_column(default=Decimal(0))
    cargo_persona_extra: Mapped[Dinero] = mapped_column(default=Decimal(0))
    cargo_mascota: Mapped[Dinero] = mapped_column(default=Decimal(0))
    descuento_semanal: Mapped[Porcentaje] = mapped_column(default=Decimal(0))
    descuento_mensual: Mapped[Porcentaje] = mapped_column(default=Decimal(0))

    ical_export_token: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, unique=True)

    publicacion: Mapped[Publicacion] = relationship(back_populates="unidades")
    tarifas: Mapped[list["Tarifa"]] = relationship(back_populates="unidad")
    franjas: Mapped[list["FranjaHoraria"]] = relationship(back_populates="unidad")
    tarifa_horaria: Mapped["TarifaHoraria | None"] = relationship(back_populates="unidad")
    adicionales: Mapped[list["Adicional"]] = relationship(back_populates="unidad")
    calendarios_externos: Mapped[list["CalendarioExterno"]] = relationship()


class Tarifa(IdMixin, Base):
    """Tarifa base (sin fechas) o por temporada. Gana la de mayor prioridad que cubra la noche.

    precios_dia_semana: {"4": 55000, "5": 60000}  (0 = lunes) sobrescribe precio_noche.
    """

    __tablename__ = "tarifa"

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    fecha_desde: Mapped[date | None]
    fecha_hasta: Mapped[date | None]
    precio_noche: Mapped[Dinero]
    precios_dia_semana: Mapped[dict | None] = mapped_column(JSONB)
    estadia_minima: Mapped[int] = mapped_column(SmallInteger, default=1)
    estadia_maxima: Mapped[int | None] = mapped_column(SmallInteger)
    anticipacion_minima_dias: Mapped[int] = mapped_column(SmallInteger, default=0)
    prioridad: Mapped[int] = mapped_column(default=0)

    unidad: Mapped[Unidad] = relationship(back_populates="tarifas")


class CalendarioExterno(IdMixin, Base):
    """iCal importado (Booking, Airbnb, etc.)."""

    __tablename__ = "calendario_externo"

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(60))
    # Qué plataforma es: permite mostrar el ícono y las instrucciones correctas.
    plataforma: Mapped[str] = mapped_column(String(30), default="otro")
    url: Mapped[str]
    ultima_sincronizacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Cada intento, salga bien o mal: es lo que mira la sincronización automática.
    ultimo_intento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_error: Mapped[str | None]


class ReservaExterna(IdMixin, TiempoMixin, Base):
    """Una venta que no pasó por nosotros, pero que ocupa la noche igual.

    Existe porque el anfitrión vende en varios lados. Lo que entra por Despegar
    —que no publica iCal— o por WhatsApp tiene que tapar esa fecha en todas las
    otras plataformas, y para eso primero tiene que estar acá.

    No es una `Reserva`: no la vendimos nosotros, así que no lleva comisión, ni
    pago, ni ítems. Es el registro de una venta ajena más el bloqueo que produce.

    `POR_REVISAR` es deliberado. Cuando un mail no se entiende del todo, la
    reserva queda esperando en vez de bloquear fechas por las dudas o —peor—
    de fallar en silencio. Un calendario que se calla cuando no entendió es
    exactamente cómo se vende dos veces la misma noche.
    """

    __tablename__ = "reserva_externa"
    __table_args__ = (
        # Un mail reenviado dos veces, o un webhook reintentado, no puede
        # producir dos reservas. La unicidad va por prestador y no por unidad:
        # cuando el mail todavía no dice a qué cabaña va, `unidad_id` es NULL, y
        # en Postgres dos NULL nunca chocan —la idempotencia se perdería justo
        # en el caso donde más hace falta.
        UniqueConstraint("prestador_id", "huella", name="uq_reserva_externa_huella"),
    )

    #: El dueño. Va siempre, incluso cuando todavía no se sabe la unidad: sin
    #: esto una reserva a medias no pertenece a nadie, y termina apareciendo en
    #: la bandeja de todos los anfitriones.
    prestador_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prestador.id"), index=True)
    #: Opcional a propósito: si el mail no dice a qué cabaña va, la reserva se
    #: guarda igual y espera que el anfitrión lo diga. Perder el mensaje sería
    #: peor que guardarlo incompleto.
    unidad_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("unidad.id"), index=True)
    origen: Mapped[OrigenReservaExterna] = mapped_column(
        pg_enum(OrigenReservaExterna, "origen_reserva_externa")
    )
    estado: Mapped[EstadoReservaExterna] = mapped_column(
        pg_enum(EstadoReservaExterna, "estado_reserva_externa"),
        default=EstadoReservaExterna.CONFIRMADA,
    )
    #: Código de `canales.PLATAFORMAS`, o "particular" si la vendió el anfitrión.
    plataforma: Mapped[str] = mapped_column(String(30), default="particular")
    fecha_inicio: Mapped[date | None]
    fecha_fin: Mapped[date | None]
    huesped: Mapped[str | None] = mapped_column(String(120))
    contacto: Mapped[str | None] = mapped_column(String(120))
    personas: Mapped[int | None] = mapped_column(SmallInteger)
    #: Lo que cobró el anfitrión. Informativo: no genera comisión ni cobro nuestro.
    monto: Mapped[Dinero | None]
    codigo_externo: Mapped[str | None] = mapped_column(String(80))
    nota: Mapped[str | None] = mapped_column(String(400))
    #: Qué no se pudo leer del mail. Vacío cuando se entendió todo.
    faltantes: Mapped[list | None] = mapped_column(JSONB)
    #: Identidad estable del mensaje que la originó (Message-ID, o un hash del
    #: cuerpo cuando no lo hay). Es lo que hace idempotente la importación.
    huella: Mapped[str | None] = mapped_column(String(120))
    #: El mail crudo, para poder rehacer la lectura si mejoramos el análisis.
    mensaje: Mapped[dict | None] = mapped_column(JSONB)

    bloqueos: Mapped[list["BloqueoFecha"]] = relationship(back_populates="reserva_externa")


class BloqueoFecha(IdMixin, TiempoMixin, Base):
    """Noches no disponibles de una unidad (rango [inicio, fin) ).

    La restricción de exclusión garantiza cero dobles reservas a nivel de BD.
    Las retenciones vencidas se desactivan con una tarea en segundo plano.
    Requiere la extensión btree_gist (migración 0001).
    """

    __tablename__ = "bloqueo_fecha"
    __table_args__ = (
        ExcludeConstraint(
            ("unidad_id", "="),
            ("rango", "&&"),
            name="ex_bloqueo_fecha_sin_superposicion",
            using="gist",
            where=text("activo"),
        ),
        Index("ix_bloqueo_fecha_vence", "vence_en", postgresql_where=text("vence_en IS NOT NULL")),
    )

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    rango: Mapped[Range[date]] = mapped_column(DATERANGE)
    origen: Mapped[OrigenBloqueo] = mapped_column(pg_enum(OrigenBloqueo, "origen_bloqueo"))
    activo: Mapped[bool] = mapped_column(default=True)
    vence_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_reserva_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("item_reserva.id"))
    calendario_externo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("calendario_externo.id", ondelete="CASCADE")
    )
    reserva_externa_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reserva_externa.id", ondelete="CASCADE")
    )
    nota: Mapped[str | None] = mapped_column(String(200))

    reserva_externa: Mapped[ReservaExterna | None] = relationship(back_populates="bloqueos")


class BloqueoHorario(IdMixin, TiempoMixin, Base):
    """Horas no disponibles de una unidad que se alquila por horario (salones).

    Es `BloqueoFecha` con hora: rango [inicio, fin) con zona horaria, que puede
    cruzar la medianoche (un evento de 21 a 5 h). La misma restricción de
    exclusión garantiza que dos rangos activos de la misma unidad no se pisen;
    como el rango es semiabierto, uno que termina a las 18 y otro que empieza a
    las 18 conviven.
    """

    __tablename__ = "bloqueo_horario"
    __table_args__ = (
        ExcludeConstraint(
            ("unidad_id", "="),
            ("rango", "&&"),
            name="ex_bloqueo_horario_sin_superposicion",
            using="gist",
            where=text("activo"),
        ),
        Index(
            "ix_bloqueo_horario_vence", "vence_en", postgresql_where=text("vence_en IS NOT NULL")
        ),
    )

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    rango: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    origen: Mapped[OrigenBloqueo] = mapped_column(
        pg_enum(OrigenBloqueo, "origen_bloqueo", crear=False)
    )
    activo: Mapped[bool] = mapped_column(default=True)
    vence_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_reserva_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("item_reserva.id"))
    nota: Mapped[str | None] = mapped_column(String(200))


class FranjaHoraria(IdMixin, Base):
    """Un turno fijo de un salón, con su precio: "Noche, de 21 a 5 h".

    Si `hora_fin` es menor o igual que `hora_inicio`, termina al día siguiente.
    `precios_dia_semana` ({"5": 450000}, lunes = 0) sobrescribe el precio ese día.
    """

    __tablename__ = "franja_horaria"

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    hora_inicio: Mapped[time]
    hora_fin: Mapped[time]
    precio: Mapped[Dinero]
    precios_dia_semana: Mapped[dict | None] = mapped_column(JSONB)
    activa: Mapped[bool] = mapped_column(default=True)

    unidad: Mapped[Unidad] = relationship(back_populates="franjas")


class TarifaHoraria(IdMixin, Base):
    """Alquiler por horas de un salón: precio, mínimo y horario de atención.

    Si `hora_cierre` es menor o igual que `hora_apertura`, cierra al día siguiente
    (atiende de 10 a 2 h). El recargo nocturno se suma a cada hora que empieza
    desde `recargo_nocturno_desde` hasta el cierre.
    """

    __tablename__ = "tarifa_horaria"

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), unique=True)
    precio_hora: Mapped[Dinero]
    precios_dia_semana: Mapped[dict | None] = mapped_column(JSONB)
    horas_minimas: Mapped[int] = mapped_column(SmallInteger, default=1)
    hora_apertura: Mapped[time]
    hora_cierre: Mapped[time]
    recargo_nocturno_desde: Mapped[time | None]
    recargo_nocturno_porcentaje: Mapped[Porcentaje] = mapped_column(default=Decimal(0))
    activa: Mapped[bool] = mapped_column(default=True)

    unidad: Mapped[Unidad] = relationship(back_populates="tarifa_horaria")


class Adicional(IdMixin, Base):
    """Algo que se suma al alquiler con su precio: vajilla, sonido, mozos."""

    __tablename__ = "adicional"

    unidad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unidad.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    descripcion: Mapped[str | None] = mapped_column(String(200))
    precio: Mapped[Dinero]
    #: True: se multiplica por la cantidad de invitados. False: una vez por evento.
    por_persona: Mapped[bool] = mapped_column(default=False)
    activo: Mapped[bool] = mapped_column(default=True)

    unidad: Mapped[Unidad] = relationship(back_populates="adicionales")
