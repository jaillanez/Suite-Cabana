"""Primeros pasos de un prestador (mejora 3): una sola lista, con avance, que lo
lleva de sus datos hasta mandar la primera publicación a revisión.

Cada paso dice si está hecho, qué falta en palabras simples y adónde ir. Se
calcula con las mismas reglas que deciden si se puede publicar
(`edicion.faltantes_por_grupo`): la lista y el botón "Mandar a revisión" nunca
se contradicen.

Se sigue la publicación más avanzada que todavía no está aprobada. Con una ya
aprobada, los primeros pasos están terminados aunque arme otra.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import CalendarioExterno, LecturaCalendario, Prestador, Publicacion, Unidad
from app.models.enums import EstadoPublicacion, ModoReserva
from app.services import edicion, mp_oauth

#: Qué publicación se sigue: la que está más cerca de publicarse.
ORDEN_ESTADO = {
    EstadoPublicacion.EN_REVISION: 0,
    EstadoPublicacion.RECHAZADA: 1,
    EstadoPublicacion.BORRADOR: 2,
    EstadoPublicacion.PAUSADA: 3,
}

UNIDADES = {
    ModoReserva.NOCHES: ("Unidades y precios", "cada cabaña con su capacidad y tarifa"),
    ModoReserva.HORAS: ("Espacios y precios", "cada espacio con sus turnos o su precio por hora"),
    ModoReserva.TURNO_CUPO: ("Actividades, turnos y precios", "qué sale, cuándo y cuánto cuesta"),
    ModoReserva.TRAMO: ("Vehículos y precios", "cada vehículo con sus recorridos o precio por km"),
}


@dataclass(frozen=True)
class Paso:
    codigo: str
    titulo: str
    detalle: str
    hecho: bool
    enlace: str
    accion: str
    opcional: bool = False
    #: False: todavía no se puede hacer (espera a un paso anterior). Sin botón.
    disponible: bool = True


@dataclass
class PrimerosPasos:
    pasos: list[Paso] = field(default_factory=list)
    publicacion_id: uuid.UUID | None = None
    titulo: str | None = None
    #: Ya tiene una publicación aprobada: el panel no hace falta.
    terminado: bool = False

    @property
    def hechos(self) -> int:
        return sum(1 for p in self.pasos if p.hecho and not p.opcional)

    @property
    def total(self) -> int:
        return sum(1 for p in self.pasos if not p.opcional)


def _seguida(db: Session, prestador: Prestador) -> tuple[Publicacion | None, bool]:
    publicaciones = list(
        db.scalars(
            select(Publicacion)
            .where(Publicacion.prestador_id == prestador.id)
            .options(
                selectinload(Publicacion.tipo_servicio),
                selectinload(Publicacion.prestador).selectinload(Prestador.usuario),
            )
            .order_by(Publicacion.creado_en.desc())
        )
    )
    aprobada = any(p.estado is EstadoPublicacion.APROBADA for p in publicaciones)
    pendientes = [p for p in publicaciones if p.estado in ORDEN_ESTADO]
    if not pendientes:
        return None, aprobada
    # La más avanzada; a igualdad de estado, la más nueva (el orden ya es por fecha).
    return min(pendientes, key=lambda p: ORDEN_ESTADO[p.estado]), aprobada


def _texto(mensajes: list[str], si_listo: str) -> str:
    return " · ".join(mensajes) if mensajes else si_listo


def calcular(db: Session, prestador: Prestador) -> PrimerosPasos:
    usuario = prestador.usuario
    p, aprobada = _seguida(db, prestador)
    # Con una ya publicada no es un primer paso: el panel se guarda.
    r = PrimerosPasos(terminado=aprobada)

    r.pasos.append(Paso(
        "datos_fiscales", "Tus datos de prestador",
        "CUIT y condición frente al IVA, para las facturas.",
        bool(prestador.cuit and prestador.condicion_iva), "/cuenta#prestador", "Completar",
    ))
    r.pasos.append(Paso(
        "whatsapp", "Tu WhatsApp",
        "Por ahí te escriben los viajeros con la reserva confirmada.",
        bool(usuario.telefono), "/cuenta#datos", "Cargarlo",
    ))
    boton = mp_oauth.disponible()
    r.pasos.append(Paso(
        "mercado_pago", "Conectar Mercado Pago",
        (
            f"Conectada: cobrás en {prestador.mp_cuenta}." if prestador.mp_user_id
            else "Tocás un botón y autorizás: lo que te reserven entra en tu cuenta."
            if boton
            else "Para que lo que te reserven entre en tu cuenta."
        ),
        bool(prestador.mp_user_id), "/cuenta#cobros", "Conectar",
    ))

    if p is None:
        nueva = "/mis-publicaciones/nueva"
        r.pasos.append(Paso(
            "publicacion", "Crear tu publicación",
            "El nombre, el tipo y dónde queda. El resto lo completás después.",
            False, nueva, "Crear",
        ))
        # La lista entera desde el principio: si apareciera de a partes, al crear
        # la publicación la barra de avance retrocedería (de 2 de 4 a 3 de 9).
        despues = "Después de crear la publicación."
        for codigo, titulo in (
            ("datos", "Descripción, tipo y reglas"), ("ubicacion", "Ubicación en el mapa"),
            ("fotos", "Fotos"), ("unidades", "Unidades y precios"),
            ("revision", "Mandar a revisión"),
        ):
            r.pasos.append(Paso(codigo, titulo, despues, False, nueva, "", disponible=False))
        return r

    r.publicacion_id, r.titulo = p.id, p.titulo
    editor = f"/mis-publicaciones/{p.id}"
    por_grupo: dict[str, list[str]] = {g: [] for g in edicion.GRUPOS}
    for grupo, mensaje in edicion.faltantes_por_grupo(db, p):
        por_grupo[grupo].append(mensaje)
    modo = p.tipo_servicio.modo_reserva

    r.pasos.append(Paso(
        "publicacion", "Crear tu publicación", f"«{p.titulo}».", True, editor, "Abrir",
    ))
    r.pasos.append(Paso(
        "datos", "Descripción, tipo y reglas",
        _texto(por_grupo["datos"], "Listo."), not por_grupo["datos"], f"{editor}#datos",
        "Completar",
    ))
    r.pasos.append(Paso(
        "ubicacion", "Ubicación en el mapa",
        _texto(por_grupo["ubicacion"], "Listo.") if por_grupo["ubicacion"]
        else "Listo. En público se muestra aproximada.",
        not por_grupo["ubicacion"], f"{editor}#ubicacion", "Marcar",
    ))
    r.pasos.append(Paso(
        "fotos", "Fotos", _texto(por_grupo["fotos"], "Listo."), not por_grupo["fotos"],
        f"{editor}#fotos", "Subir",
    ))
    titulo, ayuda = UNIDADES.get(modo, UNIDADES[ModoReserva.NOCHES])
    r.pasos.append(Paso(
        "unidades", titulo, _texto(por_grupo["unidades"], f"Listo: {ayuda}."),
        not por_grupo["unidades"], f"{editor}#unidades", "Cargar",
    ))
    if modo is ModoReserva.NOCHES:
        ids = list(
            db.scalars(select(Unidad.id).where(Unidad.publicacion_id == p.id, Unidad.activa))
        )
        conectado = bool(ids) and bool(
            db.scalar(select(CalendarioExterno.id).where(CalendarioExterno.unidad_id.in_(ids)))
            or db.scalar(
                select(LecturaCalendario.id).where(LecturaCalendario.unidad_id.in_(ids))
            )
        )
        r.pasos.append(Paso(
            "calendarios", "Conectar Airbnb y Booking",
            "Si también publicás ahí, para que no haya dobles reservas.",
            conectado, f"{editor}/calendarios", "Conectar", opcional=True,
        ))

    if p.estado is EstadoPublicacion.EN_REVISION:
        detalle = "La estamos revisando. Te avisamos por correo apenas esté publicada."
    elif p.estado is EstadoPublicacion.RECHAZADA:
        detalle = f"Hay que corregir algo: {p.motivo_rechazo or 'mirá el detalle en el editor'}."
    else:
        detalle = "Cuando esté todo, la revisamos y la publicamos."
    r.pasos.append(Paso(
        "revision", "Mandar a revisión", detalle,
        p.estado is EstadoPublicacion.EN_REVISION, editor, "Ir",
    ))
    return r
