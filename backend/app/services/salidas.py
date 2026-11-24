"""Salidas de excursiones y lugares libres (docs/05, etapa 1).

Un turno ("martes y jueves a las 9, 12 lugares") genera salidas. No se guarda
una fila por cada martes del año: se calculan del turno, y la fila se crea
recién cuando hace falta guardar algo de ese día (alguien toma lugar, el
prestador la suspende o le cambia el cupo). Desde ese momento la salida tiene su
propia hora y su propio cupo: si el prestador cambia el turno, lo vendido no se
mueve.

La sobreventa la cierra la base (CLAUDE.md §6). `ocupados` se suma con un UPDATE
sobre la fila de la salida bloqueada, y una restricción impide que pase de `cupo`
aunque algún código futuro se olvide del bloqueo.

Una retención vencida que la tarea todavía no soltó no cuenta como ocupada: se
muestra libre, y quien pide esos lugares la suelta antes de tomarlos.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CupoTomado, SalidaExcursion, TurnoExcursion, Unidad
from app.models.enums import ModoReserva, OrigenBloqueo
from app.models.excursion import DURACION_MAXIMA_MINUTOS
from app.services.precios import VENTANA_DIAS
from app.services.precios_eventos import ZONA

DURACION_MINIMA_MINUTOS = 15
#: Más que esto es un error de carga (un cero de más), no una excursión.
CUPO_MAXIMO = 500
DIAS = range(7)  # 0 = lunes
AVISO_MAXIMO_HORAS = 720  # 30 días


class SalidaInvalida(ValueError):
    """El pedido no tiene sentido: un día que el turno no sale, una salida pasada."""


class SinCupo(Exception):
    """No quedan lugares suficientes en esa salida."""

    def __init__(self, libres: int) -> None:
        self.libres = libres
        super().__init__(
            "No quedan lugares en esta salida"
            if libres <= 0
            else f"Quedan {libres} {'lugar' if libres == 1 else 'lugares'} en esta salida"
        )


@dataclass(frozen=True)
class Salida:
    """Una salida tal como se muestra: calculada del turno o guardada."""

    turno_id: object | None
    salida_id: object | None  # None mientras nadie tomó lugar ni se cambió nada
    fecha: date
    nombre: str
    inicio: datetime
    fin: datetime
    cupo: int
    libres: int
    suspendida: bool
    minimo_personas: int = 1


def hoy() -> date:
    return datetime.now(ZONA).date()


def _inicio(fecha: date, hora: time) -> datetime:
    return datetime(fecha.year, fecha.month, fecha.day, hora.hour, hora.minute, tzinfo=ZONA)


def _exigir_excursion(unidad: Unidad) -> None:
    if unidad.publicacion.tipo_servicio.modo_reserva is not ModoReserva.TURNO_CUPO:
        raise SalidaInvalida("Esta unidad no se reserva por turno y cupo")


def _validar(duracion_minutos: int, cupo: int) -> None:
    if not DURACION_MINIMA_MINUTOS <= duracion_minutos <= DURACION_MAXIMA_MINUTOS:
        raise SalidaInvalida("La duración tiene que ir de 15 minutos a 14 días")
    if not 1 <= cupo <= CUPO_MAXIMO:
        raise SalidaInvalida(f"El cupo tiene que ir de 1 a {CUPO_MAXIMO} personas")


def _validar_minimo(minimo_personas: int, aviso_minimo_horas: int, cupo: int) -> None:
    if not 1 <= minimo_personas <= cupo:
        raise SalidaInvalida("El mínimo de personas tiene que ir de 1 al cupo")
    if not 0 <= aviso_minimo_horas <= AVISO_MAXIMO_HORAS:
        raise SalidaInvalida("El aviso por el mínimo tiene que ir de 0 a 720 horas")


def cerro_la_venta(
    inicio: datetime, minimo: int, aviso_horas: int, confirmada: bool, ahora: datetime
) -> bool:
    """Pasó la hora de decidir por el mínimo y la salida no se confirmó: no se vende.

    Sin mínimo (1) nunca cierra por esto. Con mínimo, a `aviso_horas` de la
    salida o se confirmó (llegó al mínimo) o se cancela; anotar a alguien
    después le vendería una salida que no va a salir.
    """
    return minimo > 1 and not confirmada and ahora >= inicio - timedelta(hours=aviso_horas)


def _en_ventana(fecha: date) -> None:
    if fecha < hoy():
        raise SalidaInvalida("Esa fecha ya pasó")
    if fecha > hoy() + timedelta(days=VENTANA_DIAS):
        raise SalidaInvalida("Se puede reservar hasta 12 meses antes")


# --- Turnos ---


def crear_turno(
    db: Session,
    unidad: Unidad,
    *,
    nombre: str,
    dias_semana: list[int],
    hora_inicio: time,
    duracion_minutos: int,
    cupo: int,
    desde: date | None = None,
    hasta: date | None = None,
    minimo_personas: int = 1,
    aviso_minimo_horas: int = 24,
) -> TurnoExcursion:
    _exigir_excursion(unidad)
    dias = sorted(set(dias_semana))
    if not dias or any(d not in DIAS for d in dias):
        raise SalidaInvalida("Elegí al menos un día de la semana")
    _validar(duracion_minutos, cupo)
    if desde and hasta and hasta < desde:
        raise SalidaInvalida("La temporada termina antes de empezar")
    _validar_minimo(minimo_personas, aviso_minimo_horas, cupo)
    turno = TurnoExcursion(
        unidad_id=unidad.id,
        nombre=nombre.strip(),
        dias_semana=dias,
        hora_inicio=hora_inicio,
        duracion_minutos=duracion_minutos,
        cupo=cupo,
        desde=desde,
        hasta=hasta,
        minimo_personas=minimo_personas,
        aviso_minimo_horas=aviso_minimo_horas,
    )
    db.add(turno)
    db.flush()
    return turno


def sale_el(turno: TurnoExcursion, fecha: date) -> bool:
    """Si el turno tiene salida ese día, según su regla (sin mirar excepciones)."""
    return (
        turno.activo
        and fecha.weekday() in turno.dias_semana
        and (turno.desde is None or fecha >= turno.desde)
        and (turno.hasta is None or fecha <= turno.hasta)
    )


# --- Consulta ---


def _vencidos_por_salida(db: Session, ids: list, ahora: datetime) -> dict:
    """Personas de retenciones vencidas que todavía figuran en `ocupados`."""
    if not ids:
        return {}
    filas = db.execute(
        select(CupoTomado.salida_id, func.sum(CupoTomado.personas))
        .where(
            CupoTomado.salida_id.in_(ids),
            CupoTomado.activo.is_(True),
            CupoTomado.vence_en.is_not(None),
            CupoTomado.vence_en <= ahora,
        )
        .group_by(CupoTomado.salida_id)
    )
    return {sid: int(n) for sid, n in filas}


def salidas(
    db: Session,
    unidad: Unidad,
    desde: date,
    hasta: date,
    *,
    ahora: datetime | None = None,
    con_suspendidas: bool = False,
) -> list[Salida]:
    """Las salidas de la unidad entre dos días (inclusive), de la más próxima a la última.

    Solo las que todavía no salieron y caen dentro de los 12 meses en que se
    reserva. Las suspendidas solo si se piden (el panel del prestador las muestra;
    la ficha no).
    """
    _exigir_excursion(unidad)
    ahora = ahora or datetime.now(UTC)
    desde = max(desde, ahora.astimezone(ZONA).date())
    hasta = min(hasta, hoy() + timedelta(days=VENTANA_DIAS))
    if hasta < desde:
        return []

    turnos = list(
        db.scalars(
            select(TurnoExcursion).where(
                TurnoExcursion.unidad_id == unidad.id, TurnoExcursion.activo.is_(True)
            )
        )
    )
    guardadas = list(
        db.scalars(
            select(SalidaExcursion).where(
                SalidaExcursion.unidad_id == unidad.id,
                SalidaExcursion.fecha >= desde,
                SalidaExcursion.fecha <= hasta,
            )
        )
    )
    vencidos = _vencidos_por_salida(db, [s.id for s in guardadas], ahora)
    nombres = {t.id: t.nombre for t in turnos}
    por_turno_dia = {(s.turno_id, s.fecha) for s in guardadas if s.turno_id}

    resultado: list[Salida] = []
    # Las guardadas van siempre: son un compromiso concreto (tienen gente, o el
    # prestador las tocó), aunque después el turno haya cambiado.
    for s in guardadas:
        cerrada = cerro_la_venta(
            s.inicio_en, s.minimo_personas, s.aviso_minimo_horas, s.sale_confirmada, ahora
        )
        if (s.suspendida or cerrada) and not con_suspendidas:
            continue
        nombre = nombres.get(s.turno_id) or (s.turno.nombre if s.turno else "Salida especial")
        resultado.append(
            Salida(
                turno_id=s.turno_id,
                salida_id=s.id,
                fecha=s.fecha,
                nombre=nombre,
                inicio=s.inicio_en,
                fin=s.fin_en,
                cupo=s.cupo,
                libres=s.cupo - s.ocupados + vencidos.get(s.id, 0),
                suspendida=s.suspendida,
                minimo_personas=s.minimo_personas,
            )
        )
    dia = desde
    while dia <= hasta:
        for t in turnos:
            if sale_el(t, dia) and (t.id, dia) not in por_turno_dia:
                inicio = _inicio(dia, t.hora_inicio)
                # Nadie anotado y ya pasó la hora de decidir: no llega al mínimo.
                if cerro_la_venta(inicio, t.minimo_personas, t.aviso_minimo_horas, False, ahora):
                    continue
                resultado.append(
                    Salida(
                        turno_id=t.id,
                        salida_id=None,
                        fecha=dia,
                        nombre=t.nombre,
                        inicio=inicio,
                        fin=inicio + timedelta(minutes=t.duracion_minutos),
                        cupo=t.cupo,
                        libres=t.cupo,
                        suspendida=False,
                        minimo_personas=t.minimo_personas,
                    )
                )
        dia += timedelta(days=1)
    return sorted((s for s in resultado if s.inicio > ahora), key=lambda s: (s.inicio, s.nombre))


# --- Salidas guardadas ---


def materializar(db: Session, turno: TurnoExcursion, fecha: date) -> SalidaExcursion:
    """La fila de la salida de ese turno ese día; la crea si todavía no existe.

    Dos pedidos simultáneos por la misma salida no crean dos: la unicidad
    (turno, fecha) hace que el segundo encuentre la del primero.
    """
    existente = db.scalar(
        select(SalidaExcursion).where(
            SalidaExcursion.turno_id == turno.id, SalidaExcursion.fecha == fecha
        )
    )
    if existente is not None:
        return existente
    if not sale_el(turno, fecha):
        raise SalidaInvalida("Ese turno no sale ese día")
    _en_ventana(fecha)
    inicio = _inicio(fecha, turno.hora_inicio)
    db.execute(
        insert(SalidaExcursion)
        .values(
            id=uuid.uuid4(),
            unidad_id=turno.unidad_id,
            turno_id=turno.id,
            fecha=fecha,
            inicio_en=inicio,
            fin_en=inicio + timedelta(minutes=turno.duracion_minutos),
            cupo=turno.cupo,
            ocupados=0,
            suspendida=False,
            minimo_personas=turno.minimo_personas,
            aviso_minimo_horas=turno.aviso_minimo_horas,
            sale_confirmada=False,
        )
        .on_conflict_do_nothing(constraint="uq_salida_excursion_turno_fecha")
    )
    return db.scalars(
        select(SalidaExcursion)
        .where(SalidaExcursion.turno_id == turno.id, SalidaExcursion.fecha == fecha)
        .execution_options(populate_existing=True)
    ).one()


def agregar_salida(
    db: Session,
    unidad: Unidad,
    *,
    fecha: date,
    hora_inicio: time,
    duracion_minutos: int,
    cupo: int,
    nombre: str | None = None,
    minimo_personas: int = 1,
    aviso_minimo_horas: int = 24,
) -> SalidaExcursion:
    """Una salida extra, fuera de los turnos: un feriado largo, un grupo armado."""
    _exigir_excursion(unidad)
    _validar(duracion_minutos, cupo)
    _validar_minimo(minimo_personas, aviso_minimo_horas, cupo)
    _en_ventana(fecha)
    inicio = _inicio(fecha, hora_inicio)
    if inicio <= datetime.now(UTC):
        raise SalidaInvalida("Esa hora ya pasó")
    salida = SalidaExcursion(
        unidad_id=unidad.id,
        fecha=fecha,
        inicio_en=inicio,
        fin_en=inicio + timedelta(minutes=duracion_minutos),
        cupo=cupo,
        ocupados=0,
        motivo=(nombre or "").strip() or None,
        minimo_personas=minimo_personas,
        aviso_minimo_horas=aviso_minimo_horas,
    )
    db.add(salida)
    db.flush()
    return salida


def bloquear(db: Session, salida: SalidaExcursion) -> SalidaExcursion:
    """Bloquea la fila hasta el fin de la transacción y la trae al día."""
    return db.scalars(
        select(SalidaExcursion)
        .where(SalidaExcursion.id == salida.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def _soltar_vencidos_de(db: Session, salida: SalidaExcursion, ahora: datetime) -> int:
    """Suelta las retenciones vencidas de una salida ya bloqueada. Devuelve personas."""
    personas = list(
        db.scalars(
            update(CupoTomado)
            .where(
                CupoTomado.salida_id == salida.id,
                CupoTomado.activo.is_(True),
                CupoTomado.vence_en.is_not(None),
                CupoTomado.vence_en <= ahora,
            )
            .values(activo=False)
            .returning(CupoTomado.personas)
            .execution_options(synchronize_session=False)
        )
    )
    total = sum(personas)
    if total:
        db.execute(
            update(SalidaExcursion)
            .where(SalidaExcursion.id == salida.id)
            .values(ocupados=SalidaExcursion.ocupados - total)
        )
        db.refresh(salida)
    return total


def tomar(
    db: Session,
    salida: SalidaExcursion,
    personas: int,
    origen: OrigenBloqueo,
    *,
    vence_en: datetime | None = None,
    item_reserva_id=None,
    nota: str | None = None,
    ahora: datetime | None = None,
) -> CupoTomado:
    """Ocupa `personas` lugares de la salida. Levanta SinCupo o SalidaInvalida."""
    ahora = ahora or datetime.now(UTC)
    if personas < 1:
        raise SalidaInvalida("Tiene que ir al menos una persona")
    salida = bloquear(db, salida)
    if salida.suspendida:
        raise SalidaInvalida("Esa salida está suspendida")
    if salida.inicio_en <= ahora:
        raise SalidaInvalida("Esa salida ya salió")
    if cerro_la_venta(
        salida.inicio_en, salida.minimo_personas, salida.aviso_minimo_horas,
        salida.sale_confirmada, ahora,
    ):
        raise SalidaInvalida("Esa salida ya no recibe reservas")
    _soltar_vencidos_de(db, salida, ahora)
    libres = salida.cupo - salida.ocupados
    if personas > libres:
        raise SinCupo(libres)
    try:
        with db.begin_nested():
            db.execute(
                update(SalidaExcursion)
                .where(SalidaExcursion.id == salida.id)
                .values(ocupados=SalidaExcursion.ocupados + personas)
            )
    except IntegrityError:
        # Solo si alguien sumó sin bloquear la fila: la base no lo deja pasar igual.
        db.refresh(salida)
        raise SinCupo(salida.cupo - salida.ocupados) from None
    tomado = CupoTomado(
        salida_id=salida.id,
        personas=personas,
        origen=origen,
        vence_en=vence_en,
        item_reserva_id=item_reserva_id,
        nota=nota,
    )
    db.add(tomado)
    db.flush()
    db.refresh(salida)
    return tomado


def soltar(db: Session, tomado: CupoTomado) -> None:
    """Devuelve los lugares a la salida. Soltar dos veces no devuelve dos veces."""
    salida = bloquear(db, tomado.salida)
    db.refresh(tomado)
    if not tomado.activo:
        return
    tomado.activo = False
    db.execute(
        update(SalidaExcursion)
        .where(SalidaExcursion.id == salida.id)
        .values(ocupados=SalidaExcursion.ocupados - tomado.personas)
    )
    db.flush()
    db.refresh(salida)


def soltar_vencidos(db: Session, ahora: datetime | None = None) -> int:
    """Suelta las retenciones vencidas de todas las salidas. Para la tarea periódica.

    Saltea las salidas que otra transacción tiene bloqueadas: esa, si está
    tomando lugares, suelta sus vencidas ella misma.
    """
    ahora = ahora or datetime.now(UTC)
    con_vencidos = (
        select(CupoTomado.salida_id)
        .where(
            CupoTomado.activo.is_(True),
            CupoTomado.vence_en.is_not(None),
            CupoTomado.vence_en <= ahora,
        )
        .distinct()
    )
    bloqueadas = db.scalars(
        select(SalidaExcursion)
        .where(SalidaExcursion.id.in_(con_vencidos))
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).all()
    return sum(_soltar_vencidos_de(db, s, ahora) for s in bloqueadas)


def _tomados(db: Session, salida: SalidaExcursion, ahora: datetime) -> int:
    _soltar_vencidos_de(db, salida, ahora)
    return salida.ocupados


def suspender(
    db: Session, salida: SalidaExcursion, motivo: str | None = None, ahora: datetime | None = None
) -> SalidaExcursion:
    """Marca la salida como suspendida. Solo vacía: con gente anotada se usa
    `reservas_excursion.no_sale`, que antes cancela las reservas con su reintegro."""
    salida = bloquear(db, salida)
    ocupados = _tomados(db, salida, ahora or datetime.now(UTC))
    if ocupados:
        raise SalidaInvalida(
            f"Esa salida tiene {ocupados} {'lugar tomado' if ocupados == 1 else 'lugares tomados'}"
        )
    salida.suspendida = True
    salida.motivo = (motivo or "").strip() or None
    db.flush()
    return salida


def reanudar(db: Session, salida: SalidaExcursion) -> SalidaExcursion:
    salida = bloquear(db, salida)
    salida.suspendida = False
    db.flush()
    return salida


def cambiar_cupo(
    db: Session, salida: SalidaExcursion, cupo: int, ahora: datetime | None = None
) -> SalidaExcursion:
    """Más o menos lugares para esa salida; nunca menos que los ya tomados."""
    if not 1 <= cupo <= CUPO_MAXIMO:
        raise SalidaInvalida(f"El cupo tiene que ir de 1 a {CUPO_MAXIMO} personas")
    salida = bloquear(db, salida)
    ocupados = _tomados(db, salida, ahora or datetime.now(UTC))
    if cupo < ocupados:
        raise SalidaInvalida(f"Ya hay {ocupados} lugares tomados: el cupo no puede ser menor")
    salida.cupo = cupo
    db.flush()
    return salida



def personas_firmes(db: Session, salida: SalidaExcursion) -> int:
    """Personas con lugar firme: reservas pagadas y ventas del prestador, no las
    retenciones de quien todavía está pagando."""
    return int(
        db.scalar(
            select(func.coalesce(func.sum(CupoTomado.personas), 0)).where(
                CupoTomado.salida_id == salida.id,
                CupoTomado.activo.is_(True),
                CupoTomado.origen != OrigenBloqueo.RETENCION,
            )
        )
    )
