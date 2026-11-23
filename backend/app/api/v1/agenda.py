"""Calendario integrado del prestador (docs/01 §5 R3, R10).

Una vista de todo: todas las unidades, todas las fechas tomadas, venga la ocupación
de una reserva nuestra, de un bloqueo propio o de otro portal. El editor muestra el
calendario de una unidad; acá se ve el negocio entero.

Sobre los portales: Airbnb, Booking y Vrbo publican un iCal por alojamiento y se
conectan pegando dos direcciones. Despegar no lo ofrece al anfitrión, así que
figura en el catálogo con el motivo en vez de fingir que alcanza con una URL.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import prestador_actual
from app.api.v1 import correo
from app.core.config import get_settings
from app.core.database import get_db
from app.models import CalendarioExterno, Prestador, Publicacion, ReservaExterna, Unidad
from app.models.enums import EstadoPublicacion, EstadoReservaExterna, OrigenReservaExterna
from app.services import calendario as agenda
from app.services import canales, tipos
from app.services import reservas_externas as externas
from app.services.correo import analisis

router = APIRouter(tags=["calendario"])

DIAS_POR_DEFECTO = 60
DIAS_MAXIMO = 370


class PlataformaOut(BaseModel):
    codigo: str
    nombre: str
    tiene_ical: bool
    donde_esta: str
    ejemplo_url: str
    nota: str
    pasos: list[str]


class TramoOut(BaseModel):
    desde: date
    hasta: date
    noches: int
    origen: str
    etiqueta: str
    nota: str | None
    calendario: str | None
    plataforma: str | None
    editable: bool


class ConexionOut(BaseModel):
    id: uuid.UUID
    unidad_id: uuid.UUID
    unidad: str
    publicacion_id: uuid.UUID
    publicacion: str
    nombre: str
    plataforma: str
    plataforma_nombre: str
    url: str
    ultima_sincronizacion: datetime | None
    ultimo_error: str | None


class UnidadAgendaOut(BaseModel):
    unidad_id: uuid.UUID
    unidad: str
    capacidad: int
    publicacion_id: uuid.UUID
    publicacion: str
    slug: str
    estado: EstadoPublicacion
    url_exportacion: str
    tramos: list[TramoOut]
    noches_ocupadas: int


class ResumenAgenda(BaseModel):
    unidades: int
    conexiones: int
    con_error: int
    noches_ocupadas: int
    sin_conectar: int = Field(description="Unidades sin ningún calendario externo")


class AgendaGeneral(BaseModel):
    desde: date
    hasta: date
    resumen: ResumenAgenda
    unidades: list[UnidadAgendaOut]
    conexiones: list[ConexionOut]


def _mis_unidades(db: Session, prestador: Prestador) -> list[Unidad]:
    return list(
        db.scalars(
            select(Unidad)
            .join(Publicacion, Unidad.publicacion_id == Publicacion.id)
            .where(
                Publicacion.prestador_id == prestador.id,
                Unidad.activa.is_(True),
                # Por días: un salón tiene su agenda por horas (docs/04, etapa 5).
                # Acá saldría siempre libre y cargarle una reserva por fechas no
                # lo ocuparía para la reserva por horario.
                tipos.por_noches(),
            )
            .options(selectinload(Unidad.publicacion))
            .order_by(Publicacion.titulo, Unidad.nombre)
        ).unique()
    )


@router.get("/canales", response_model=list[PlataformaOut])
def catalogo_de_canales() -> list[PlataformaOut]:
    """Con qué portales se puede sincronizar, y cómo sacar la dirección de cada uno."""
    return [
        PlataformaOut(
            codigo=p.codigo,
            nombre=p.nombre,
            tiene_ical=p.tiene_ical,
            donde_esta=p.donde_esta,
            ejemplo_url=p.ejemplo_url,
            nota=p.nota,
            pasos=p.pasos,
        )
        for p in canales.PLATAFORMAS
    ]


@router.get("/mi-calendario", response_model=AgendaGeneral)
def calendario_integrado(
    desde: date | None = None,
    dias: int = Query(default=DIAS_POR_DEFECTO, ge=1, le=DIAS_MAXIMO),
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> AgendaGeneral:
    """Todo lo que tenés tomado, en una sola vista."""
    inicio = desde or date.today()
    fin = inicio + timedelta(days=dias)
    base = get_settings().url_publica_api.rstrip("/")

    unidades = _mis_unidades(db, prestador)
    nombres_plataforma = {p.codigo: p.nombre for p in canales.PLATAFORMAS}

    externos: dict[uuid.UUID, list[CalendarioExterno]] = {}
    if unidades:
        for c in db.scalars(
            select(CalendarioExterno)
            .where(CalendarioExterno.unidad_id.in_([u.id for u in unidades]))
            .order_by(CalendarioExterno.nombre)
        ):
            externos.setdefault(c.unidad_id, []).append(c)

    salida: list[UnidadAgendaOut] = []
    total_noches = 0
    for u in unidades:
        por_nombre = {c.nombre: c.plataforma for c in externos.get(u.id, [])}
        tramos = []
        noches = 0
        for t in agenda.ocupacion(db, u.id):
            # Solo lo que cae dentro de la ventana pedida.
            if t.hasta <= inicio or t.desde >= fin:
                continue
            visible_desde = max(t.desde, inicio)
            visible_hasta = min(t.hasta, fin)
            cantidad = (visible_hasta - visible_desde).days
            noches += cantidad
            tramos.append(
                TramoOut(
                    desde=t.desde,
                    hasta=t.hasta,
                    noches=(t.hasta - t.desde).days,
                    origen=t.origen.value,
                    etiqueta=t.etiqueta,
                    nota=t.nota,
                    calendario=t.calendario,
                    plataforma=por_nombre.get(t.calendario) if t.calendario else None,
                    editable=t.origen.value == "manual",
                )
            )
        total_noches += noches
        salida.append(
            UnidadAgendaOut(
                unidad_id=u.id,
                unidad=u.nombre,
                capacidad=u.capacidad,
                publicacion_id=u.publicacion_id,
                publicacion=u.publicacion.titulo,
                slug=u.publicacion.slug,
                estado=u.publicacion.estado,
                url_exportacion=f"{base}/api/v1/ical/{u.ical_export_token}.ics",
                tramos=tramos,
                noches_ocupadas=noches,
            )
        )

    por_id = {u.id: u for u in unidades}
    conexiones = [
        ConexionOut(
            id=c.id,
            unidad_id=c.unidad_id,
            unidad=por_id[c.unidad_id].nombre,
            publicacion_id=por_id[c.unidad_id].publicacion_id,
            publicacion=por_id[c.unidad_id].publicacion.titulo,
            nombre=c.nombre,
            plataforma=c.plataforma,
            plataforma_nombre=nombres_plataforma.get(c.plataforma, c.plataforma),
            url=c.url,
            ultima_sincronizacion=c.ultima_sincronizacion,
            ultimo_error=c.ultimo_error,
        )
        for lista in externos.values()
        for c in lista
    ]

    return AgendaGeneral(
        desde=inicio,
        hasta=fin,
        resumen=ResumenAgenda(
            unidades=len(unidades),
            conexiones=len(conexiones),
            con_error=sum(1 for c in conexiones if c.ultimo_error),
            noches_ocupadas=total_noches,
            sin_conectar=sum(1 for u in unidades if not externos.get(u.id)),
        ),
        unidades=salida,
        conexiones=conexiones,
        direccion_buzon=correo.direccion_de(prestador),
    )


class ResultadoUno(BaseModel):
    calendario_id: uuid.UUID
    nombre: str
    unidad: str
    plataforma: str
    ok: bool
    detalle: str


class ResultadoTodos(BaseModel):
    sincronizados: int
    con_error: int
    resultados: list[ResultadoUno]


@router.post("/mi-calendario/sincronizar", response_model=ResultadoTodos)
def sincronizar_todo(
    prestador: Prestador = Depends(prestador_actual), db: Session = Depends(get_db)
) -> ResultadoTodos:
    """Trae de nuevo todos los calendarios conectados, de todas las unidades.

    Un portal caído no frena a los demás: cada uno informa lo suyo.
    """
    unidades = {u.id: u for u in _mis_unidades(db, prestador)}
    if not unidades:
        return ResultadoTodos(sincronizados=0, con_error=0, resultados=[])

    externos = list(
        db.scalars(
            select(CalendarioExterno).where(CalendarioExterno.unidad_id.in_(unidades))
        )
    )
    resultados: list[ResultadoUno] = []
    for c in externos:
        try:
            r = agenda.sincronizar(db, c)
            resultados.append(
                ResultadoUno(
                    calendario_id=c.id,
                    nombre=c.nombre,
                    unidad=unidades[c.unidad_id].nombre,
                    plataforma=c.plataforma,
                    ok=True,
                    detalle=r.detalle,
                )
            )
        except Exception as e:  # noqa: BLE001 - descarga o parseo de cada portal
            resultados.append(
                ResultadoUno(
                    calendario_id=c.id,
                    nombre=c.nombre,
                    unidad=unidades[c.unidad_id].nombre,
                    plataforma=c.plataforma,
                    ok=False,
                    detalle=c.ultimo_error or agenda.motivo(e),
                )
            )
    db.commit()
    return ResultadoTodos(
        sincronizados=sum(1 for r in resultados if r.ok),
        con_error=sum(1 for r in resultados if not r.ok),
        resultados=resultados,
    )


# --- Reservas que entraron por fuera (docs/01 §5 R3) ---
#
# Dos puertas a la misma mesa: un mail de la plataforma que no publica iCal
# —Despegar, sobre todo— y la venta que el anfitrión cerró por WhatsApp. Las dos
# terminan en `reserva_externa`, y al terminar ahí tapan esa noche en todos los
# otros portales, porque el bloqueo que crean sale por el iCal que exportamos.


class ReservaExternaOut(BaseModel):
    id: uuid.UUID
    unidad_id: uuid.UUID | None
    unidad: str | None
    publicacion: str | None
    origen: str
    estado: str
    plataforma: str
    plataforma_nombre: str
    fecha_inicio: date | None
    fecha_fin: date | None
    huesped: str | None
    contacto: str | None
    personas: int | None
    monto: Decimal | None
    codigo_externo: str | None
    nota: str | None
    faltantes: list[str]
    creado_en: datetime


def _reserva_out(db: Session, r: ReservaExterna) -> ReservaExternaOut:
    unidad = db.get(Unidad, r.unidad_id) if r.unidad_id else None
    plataforma = canales.POR_CODIGO.get(r.plataforma)
    return ReservaExternaOut(
        id=r.id,
        unidad_id=r.unidad_id,
        unidad=unidad.nombre if unidad else None,
        publicacion=unidad.publicacion.titulo if unidad else None,
        origen=r.origen.value,
        estado=r.estado.value,
        plataforma=r.plataforma,
        plataforma_nombre=(
            plataforma.nombre if plataforma else "Venta propia"
        ),
        fecha_inicio=r.fecha_inicio,
        fecha_fin=r.fecha_fin,
        huesped=r.huesped,
        contacto=r.contacto,
        personas=r.personas,
        monto=r.monto,
        codigo_externo=r.codigo_externo,
        nota=r.nota,
        faltantes=list(r.faltantes or []),
        creado_en=r.creado_en,
    )


def _mia(db: Session, prestador: Prestador, reserva_id: uuid.UUID) -> ReservaExterna:
    """La dueña es el prestador, no la unidad: una reserva a medias no tiene unidad."""
    reserva = db.get(ReservaExterna, reserva_id)
    if reserva is None or reserva.prestador_id != prestador.id:
        raise HTTPException(404, "No encontramos esa reserva.")
    return reserva


def _mi_unidad(db: Session, prestador: Prestador, unidad_id: uuid.UUID) -> Unidad:
    unidad = next((u for u in _mis_unidades(db, prestador) if u.id == unidad_id), None)
    if unidad is None:
        raise HTTPException(404, "Esa unidad no es tuya.")
    return unidad


class ReservaParticularIn(BaseModel):
    unidad_id: uuid.UUID
    fecha_inicio: date
    fecha_fin: date
    huesped: str | None = Field(default=None, max_length=120)
    contacto: str | None = Field(default=None, max_length=120)
    personas: int | None = Field(default=None, ge=1, le=99)
    monto: Decimal | None = Field(default=None, ge=0)
    #: Dónde se vendió. "particular" es el default: la cerró el anfitrión.
    plataforma: str = "particular"
    nota: str | None = Field(default=None, max_length=400)


@router.post("/mi-calendario/reservas-externas", response_model=ReservaExternaOut, status_code=201)
def cargar_reserva_particular(
    datos: ReservaParticularIn,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> ReservaExternaOut:
    """Una venta cerrada fuera de la plataforma. No lleva comisión: no la vendimos."""
    unidad = _mi_unidad(db, prestador, datos.unidad_id)
    try:
        reserva = externas.cargar_a_mano(
            db,
            prestador.id,
            unidad,
            fecha_inicio=datos.fecha_inicio,
            fecha_fin=datos.fecha_fin,
            huesped=datos.huesped,
            contacto=datos.contacto,
            personas=datos.personas,
            monto=datos.monto,
            plataforma=datos.plataforma,
            nota=datos.nota,
        )
    except externas.FechasOcupadas as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    db.commit()
    return _reserva_out(db, reserva)


class CorreoIn(BaseModel):
    """Un mail pegado a mano. Es el camino que funciona sin infraestructura."""

    cuerpo: str = Field(min_length=10, max_length=200_000)
    asunto: str = Field(default="", max_length=500)
    remitente: str = Field(default="", max_length=300)
    #: Si el anfitrión ya sabe de qué unidad es, se ahorra la adivinanza.
    unidad_id: uuid.UUID | None = None


class LecturaOut(BaseModel):
    reserva: ReservaExternaOut
    nueva: bool
    detalle: str
    #: Qué entendimos de la unidad, para poder explicarlo.
    unidad_leida: str | None


@router.post("/mi-calendario/correo", response_model=LecturaOut, status_code=201)
def cargar_desde_correo(
    datos: CorreoIn,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> LecturaOut:
    """Lee un mail de confirmación y lo convierte en reserva.

    Si se entendió todo, bloquea las fechas. Si falta algo, queda esperando
    revisión y lo dice: no inventa lo que no leyó.
    """
    lectura = analisis.analizar(
        asunto=datos.asunto, cuerpo=datos.cuerpo, remitente=datos.remitente
    )
    unidades = externas.unidades_de(db, prestador.id)
    unidad = (
        _mi_unidad(db, prestador, datos.unidad_id)
        if datos.unidad_id
        else externas.adivinar_unidad(lectura.unidad_nombre, unidades)
    )
    try:
        resultado = externas.registrar(
            db,
            prestador.id,
            unidad,
            lectura,
            origen=OrigenReservaExterna.CORREO,
            mensaje={"asunto": datos.asunto, "remitente": datos.remitente, "cuerpo": datos.cuerpo},
        )
    except externas.FechasOcupadas as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return LecturaOut(
        reserva=_reserva_out(db, resultado.reserva),
        nueva=resultado.nueva,
        detalle=resultado.detalle,
        unidad_leida=lectura.unidad_nombre,
    )


@router.get("/mi-calendario/por-revisar", response_model=list[ReservaExternaOut])
def pendientes_de_revisar(
    prestador: Prestador = Depends(prestador_actual), db: Session = Depends(get_db)
) -> list[ReservaExternaOut]:
    """Lo que llegó por mail y no se entendió del todo. Nada de esto bloquea fechas."""
    filas = externas.de(db, prestador.id, EstadoReservaExterna.POR_REVISAR)
    return [_reserva_out(db, r) for r in filas]


class CompletarIn(BaseModel):
    unidad_id: uuid.UUID | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    huesped: str | None = Field(default=None, max_length=120)


@router.patch("/mi-calendario/reservas-externas/{reserva_id}", response_model=ReservaExternaOut)
def completar_reserva(
    reserva_id: uuid.UUID,
    datos: CompletarIn,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> ReservaExternaOut:
    """El anfitrión llena lo que el análisis no pudo leer, y recién ahí bloquea."""
    reserva = _mia(db, prestador, reserva_id)
    unidad = _mi_unidad(db, prestador, datos.unidad_id) if datos.unidad_id else None
    try:
        externas.completar(
            db,
            reserva,
            unidad=unidad,
            fecha_inicio=datos.fecha_inicio,
            fecha_fin=datos.fecha_fin,
            huesped=datos.huesped,
        )
    except externas.FechasOcupadas as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    db.commit()
    return _reserva_out(db, reserva)


@router.delete("/mi-calendario/reservas-externas/{reserva_id}", status_code=204)
def descartar_reserva(
    reserva_id: uuid.UUID,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> None:
    """La venta se cayó, o el mail no era una reserva. Libera las fechas."""
    externas.descartar(db, _mia(db, prestador, reserva_id))
    db.commit()
