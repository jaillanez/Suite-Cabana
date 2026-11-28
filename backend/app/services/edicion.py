"""Ciclo de vida de una publicación (docs/01 §5 R2).

Estados y quién los mueve:

    borrador ──(prestador, si está completa)──> en_revision
    en_revision ──(operador)──> aprobada | rechazada
    rechazada ──(prestador)──> borrador
    aprobada ⇄ pausada (prestador)

Una publicación aprobada que se edita sigue aprobada: la moderación es para el
alta, no para cada corrección de una coma. Si eso cambia, cambia acá.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.config import get_settings
from app.models import (
    Foto,
    FranjaHoraria,
    LugarTraslado,
    PrecioPasajero,
    Publicacion,
    SalidaExcursion,
    Tarifa,
    TarifaHoraria,
    TarifaTraslado,
    TramoTraslado,
    TurnoExcursion,
    Unidad,
)
from app.models.enums import EstadoPublicacion, ModoReserva

TRANSICIONES: dict[EstadoPublicacion, set[EstadoPublicacion]] = {
    EstadoPublicacion.BORRADOR: {EstadoPublicacion.EN_REVISION},
    EstadoPublicacion.EN_REVISION: {EstadoPublicacion.APROBADA, EstadoPublicacion.RECHAZADA},
    EstadoPublicacion.RECHAZADA: {EstadoPublicacion.BORRADOR},
    EstadoPublicacion.APROBADA: {EstadoPublicacion.PAUSADA},
    EstadoPublicacion.PAUSADA: {EstadoPublicacion.APROBADA},
}


class TransicionInvalida(Exception):
    """Ese cambio de estado no existe."""


class PublicacionIncompleta(Exception):
    """Falta información para que pueda revisarse."""

    def __init__(self, faltantes: list[str]):
        self.faltantes = faltantes
        super().__init__("; ".join(faltantes))


#: Los grupos en que se ordena lo que falta: cada uno es un paso de "Primeros
#: pasos" y un bloque del editor.
GRUPOS = ("datos", "ubicacion", "whatsapp", "fotos", "unidades")


def faltantes(db: Session, publicacion: Publicacion) -> list[str]:
    """Qué le falta a la publicación para poder mandarse a revisión.

    Se devuelve la lista completa, no el primer problema: el prestador tiene que
    poder resolver todo de una vez y no descubrir un faltante por intento.
    """
    return [mensaje for _, mensaje in faltantes_por_grupo(db, publicacion)]


def faltantes_por_grupo(db: Session, publicacion: Publicacion) -> list[tuple[str, str]]:
    """Lo mismo que `faltantes`, con el grupo de cada cosa (ver `GRUPOS`)."""
    s = get_settings()
    problemas: list[tuple[str, str]] = []

    if not publicacion.titulo or len(publicacion.titulo.strip()) < 6:
        problemas.append(("datos", "El título necesita al menos 6 caracteres"))
    if not publicacion.descripcion or len(publicacion.descripcion.strip()) < 40:
        problemas.append(("datos", "La descripción necesita al menos 40 caracteres"))
    if publicacion.ubicacion is None:
        problemas.append(("ubicacion", "Falta marcar la ubicación en el mapa"))
    modo = publicacion.tipo_servicio.modo_reserva
    salon = modo is ModoReserva.HORAS
    excursion = modo is ModoReserva.TURNO_CUPO
    traslado = modo is ModoReserva.TRAMO
    if publicacion.subtipo_servicio_id is None:
        problemas.append((
            "datos",
            "Falta elegir el tipo de espacio"
            if salon
            else "Falta elegir el tipo de actividad"
            if excursion
            else "Falta elegir el tipo de traslado"
            if traslado
            else "Falta elegir el tipo de alojamiento",
        ))
    # Una plantilla o tramos propios del prestador: cualquiera de las dos vale.
    if publicacion.politica_cancelacion_id is None and not publicacion.tramos_cancelacion:
        problemas.append(("datos", "Falta elegir una política de cancelación"))
    # Con la reserva confirmada, el viajero le escribe por WhatsApp desde la reserva.
    if not publicacion.prestador.usuario.telefono:
        problemas.append(("whatsapp", "Falta tu WhatsApp: cargalo en Mi cuenta"))
    # Un salón no tiene ingreso y salida: sus horarios son los turnos o el
    # horario de atención de cada unidad.
    if modo is ModoReserva.NOCHES and (
        publicacion.hora_ingreso is None or publicacion.hora_salida is None
    ):
        problemas.append(("datos", "Faltan los horarios de ingreso y salida"))

    fotos = db.scalar(
        select(func.count(Foto.id)).where(Foto.publicacion_id == publicacion.id)
    ) or 0
    if fotos < s.fotos_minimas:
        problemas.append(("fotos", f"Faltan fotos: se necesitan {s.fotos_minimas} y hay {fotos}"))

    unidades = list(
        db.scalars(
            select(Unidad).where(Unidad.publicacion_id == publicacion.id, Unidad.activa.is_(True))
        )
    )
    if not unidades:
        problemas.append((
            "unidades",
            "Falta cargar al menos un espacio"
            if salon
            else "Falta cargar al menos una actividad"
            if excursion
            else "Falta cargar al menos un vehículo"
            if traslado
            else "Falta cargar al menos una unidad",
        ))
    elif excursion:
        problemas.extend(("unidades", m) for m in _faltantes_excursion(db, unidades))
    elif traslado:
        problemas.extend(("unidades", m) for m in _faltantes_traslado(db, unidades))
    elif salon:
        # Un salón se puede reservar si tiene al menos un turno o precio por hora.
        sin_precio = [
            u.nombre
            for u in unidades
            if not db.scalar(
                select(FranjaHoraria.id).where(
                    FranjaHoraria.unidad_id == u.id, FranjaHoraria.activa.is_(True)
                )
            )
            and not db.scalar(
                select(TarifaHoraria.id).where(
                    TarifaHoraria.unidad_id == u.id, TarifaHoraria.activa.is_(True)
                )
            )
        ]
        if sin_precio:
            problemas.append(
                ("unidades", f"Sin turnos ni precio por hora: {', '.join(sin_precio)}")
            )
    else:
        sin_tarifa = [
            u.nombre
            for u in unidades
            if not db.scalar(select(Tarifa.id).where(Tarifa.unidad_id == u.id))
        ]
        if sin_tarifa:
            problemas.append(("unidades", f"Sin tarifa cargada: {', '.join(sin_tarifa)}"))

    return problemas


def _mover(publicacion: Publicacion, destino: EstadoPublicacion) -> None:
    if destino not in TRANSICIONES.get(publicacion.estado, set()):
        raise TransicionInvalida(
            f"No se puede pasar de {publicacion.estado.value} a {destino.value}"
        )
    publicacion.estado = destino


def enviar_a_revision(db: Session, publicacion: Publicacion) -> None:
    problemas = faltantes(db, publicacion)
    if problemas:
        raise PublicacionIncompleta(problemas)
    _mover(publicacion, EstadoPublicacion.EN_REVISION)
    publicacion.motivo_rechazo = None


def aprobar(publicacion: Publicacion) -> None:
    _mover(publicacion, EstadoPublicacion.APROBADA)
    publicacion.motivo_rechazo = None


def rechazar(publicacion: Publicacion, motivo: str) -> None:
    if not motivo.strip():
        raise ValueError("El rechazo necesita un motivo: el prestador tiene que saber qué corregir")
    _mover(publicacion, EstadoPublicacion.RECHAZADA)
    publicacion.motivo_rechazo = motivo.strip()


def volver_a_borrador(publicacion: Publicacion) -> None:
    _mover(publicacion, EstadoPublicacion.BORRADOR)


def pausar(publicacion: Publicacion) -> None:
    _mover(publicacion, EstadoPublicacion.PAUSADA)


def reactivar(publicacion: Publicacion) -> None:
    _mover(publicacion, EstadoPublicacion.APROBADA)


def slug_libre(db: Session, titulo: str, localidad_slug: str) -> str:
    """Slug legible y único. Entra en la URL pública de la ficha."""
    base = (
        titulo.lower()
        .strip()
        .translate(str.maketrans("áéíóúüñ", "aeiouun"))
    )
    base = "".join(c if c.isalnum() else "-" for c in base)
    base = "-".join(p for p in base.split("-") if p)[:120] or "alojamiento"
    candidato = f"{base}-{localidad_slug}"
    if not db.scalar(select(Publicacion.id).where(Publicacion.slug == candidato)):
        return candidato
    sufijo = 2
    while db.scalar(select(Publicacion.id).where(Publicacion.slug == f"{candidato}-{sufijo}")):
        sufijo += 1
    return f"{candidato}-{sufijo}"


def tarifa_se_superpone(db: Session, unidad_id, desde: date | None, hasta: date | None,
                        excluir=None) -> bool:
    """Dos tarifas de temporada que se pisan hacen impredecible el precio."""
    if desde is None and hasta is None:
        return False
    consulta = select(Tarifa).where(Tarifa.unidad_id == unidad_id)
    if excluir is not None:
        consulta = consulta.where(Tarifa.id != excluir)
    for t in db.scalars(consulta):
        if t.fecha_desde is None and t.fecha_hasta is None:
            continue  # la tarifa base convive con las de temporada
        inicio_a = desde or date.min
        fin_a = hasta or date.max
        inicio_b = t.fecha_desde or date.min
        fin_b = t.fecha_hasta or date.max
        if inicio_a <= fin_b and inicio_b <= fin_a:
            return True
    return False


def _faltantes_excursion(db: Session, unidades: list[Unidad]) -> list[str]:
    """Cada actividad necesita precios y algo que salga: un turno o una salida especial."""
    sin_salidas, sin_precios = [], []
    for u in unidades:
        tiene_turno = db.scalar(
            select(TurnoExcursion.id).where(
                TurnoExcursion.unidad_id == u.id, TurnoExcursion.activo.is_(True)
            )
        )
        tiene_especial = db.scalar(
            select(SalidaExcursion.id).where(
                SalidaExcursion.unidad_id == u.id,
                SalidaExcursion.turno_id.is_(None),
                SalidaExcursion.fecha >= date.today(),
            )
        )
        if not tiene_turno and not tiene_especial:
            sin_salidas.append(u.nombre)
        if not db.scalar(
            select(PrecioPasajero.id).where(
                PrecioPasajero.unidad_id == u.id, PrecioPasajero.activo.is_(True)
            )
        ):
            sin_precios.append(u.nombre)
    problemas = []
    if sin_salidas:
        problemas.append(f"Sin turnos ni salidas: {', '.join(sin_salidas)}")
    if sin_precios:
        problemas.append(f"Sin precios por pasajero: {', '.join(sin_precios)}")
    return problemas


def _faltantes_traslado(db: Session, unidades: list[Unidad]) -> list[str]:
    """Cada vehículo necesita una forma de cobrar: un tramo fijo (con sus dos
    lugares activos) o una tarifa por kilómetro."""
    sin_precio = []
    for u in unidades:
        origen, destino = aliased(LugarTraslado), aliased(LugarTraslado)
        tiene_tramo = db.scalar(
            select(TramoTraslado.id)
            .join(origen, TramoTraslado.origen_id == origen.id)
            .join(destino, TramoTraslado.destino_id == destino.id)
            .where(
                TramoTraslado.unidad_id == u.id,
                TramoTraslado.activo.is_(True),
                origen.activo.is_(True),
                destino.activo.is_(True),
            )
            .limit(1)
        )
        por_km = db.scalar(
            select(TarifaTraslado.id).where(
                TarifaTraslado.unidad_id == u.id, TarifaTraslado.precio_km.is_not(None)
            )
        )
        if not tiene_tramo and not por_km:
            sin_precio.append(u.nombre)
    if sin_precio:
        return [f"Sin tramos ni precio por km: {', '.join(sin_precio)}"]
    return []
