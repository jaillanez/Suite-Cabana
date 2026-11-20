"""Reservas, pagos y cancelaciones (docs/01 §5 R5, R6, R8).

El viajero reserva, paga con la billetera que elija, y puede cancelar según la
política que aceptó. El prestador ve sus reservas y, si publica "a solicitud",
acepta o rechaza.

Las notificaciones de las pasarelas entran por `/webhooks/{pasarela}` y se
procesan **una sola vez**: se registran por (pasarela, id del pago, estado)
antes de aplicarlas. El estado entra en la clave porque un mismo pago avisa más
de una vez —pendiente y después aprobado— y el segundo aviso no puede perderse.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session, selectinload

from app.api.deps import con_email_verificado, prestador_actual, usuario_actual
from app.api.v1.publicaciones import Dinero, FotoOut
from app.core.config import get_settings
from app.core.database import get_db
from app.models import (
    ItemReserva,
    Localidad,
    NotificacionPago,
    Prestador,
    Publicacion,
    Reserva,
    Unidad,
    Usuario,
)
from app.models.enums import EstadoReserva
from app.services import cifrado, cuenta_cobro, pagos, privacidad, reservas
from app.services.pagos.base import Cobro

router = APIRouter(tags=["reservas"])


# --- Formas ---


class NuevaReserva(BaseModel):
    unidad_id: uuid.UUID
    desde: date
    hasta: date
    adultos: Annotated[int, Field(ge=1, le=30)] = 2
    menores: Annotated[int, Field(ge=0, le=20)] = 0
    mascotas: Annotated[int, Field(ge=0, le=5)] = 0
    acepta_terminos: bool = Field(
        default=False, description="docs/01 §5 R11: también se aceptan al reservar"
    )


class PedidoPago(BaseModel):
    pasarela: str | None = Field(default=None, description="Vacío: la predeterminada")


class Cancelacion(BaseModel):
    motivo: Annotated[str, Field(default="", max_length=300)] = ""


class RespuestaPrestador(BaseModel):
    motivo: Annotated[str, Field(default="", max_length=300)] = ""


class PasarelaOut(BaseModel):
    codigo: str
    nombre: str
    disponible: bool
    reparte_automaticamente: bool
    motivo: str | None = Field(default=None, description="Por qué no se puede usar")


class ComisionOut(BaseModel):
    base: Dinero
    comision_neta: Dinero
    iva: Dinero
    comision_total: Dinero
    cargo_viajero: Dinero
    descuento_prestador: Dinero
    regla: str


class ItemOut(BaseModel):
    unidad_id: uuid.UUID
    unidad: str
    publicacion: str
    slug: str
    localidad: str
    provincia: str
    fecha_inicio: date
    fecha_fin: date
    noches: int
    adultos: int
    menores: int
    mascotas: int
    subtotal: Dinero
    desglose: dict
    comision: ComisionOut | None
    fotos: list[FotoOut]
    # Solo con la reserva confirmada: antes es la casa de un desconocido.
    direccion: str | None = None
    lat: float | None = None
    lon: float | None = None


class PagoOut(BaseModel):
    pasarela: str
    estado: str
    monto: Dinero
    id_externo: str | None


class ReintegroOut(BaseModel):
    porcentaje: int
    monto: Dinero
    motivo: str


class ReservaOut(BaseModel):
    codigo: str
    estado: EstadoReserva
    total: Dinero
    monto_sena: Dinero | None
    moneda: str
    vence_pago_en: datetime | None
    vence_aprobacion_en: datetime | None
    cancelada_en: datetime | None
    motivo_cancelacion: str | None
    politica_cancelacion: dict | None
    creada_en: datetime
    items: list[ItemOut]
    pagos: list[PagoOut]
    reintegro_si_cancela: ReintegroOut | None


class PreferenciaOut(BaseModel):
    pasarela: str
    url_pago: str
    id_externo: str
    total: Dinero


# --- Salidas ---


def _item_out(item: ItemReserva, con_direccion: bool = False) -> ItemOut:
    p = item.unidad.publicacion
    c = item.comision
    direccion, lat, lon = None, None, None
    sesion = object_session(item)
    if con_direccion and sesion is not None:
        from app.services.publicaciones import _coordenadas

        direccion = p.direccion
        lat, lon = _coordenadas(sesion, p.id)
    return ItemOut(
        direccion=direccion,
        lat=lat,
        lon=lon,
        unidad_id=item.unidad_id,
        unidad=item.unidad.nombre,
        publicacion=p.titulo,
        slug=p.slug,
        localidad=p.localidad.nombre,
        provincia=p.localidad.provincia.nombre,
        fecha_inicio=item.fecha_inicio,
        fecha_fin=item.fecha_fin,
        noches=(item.fecha_fin - item.fecha_inicio).days,
        adultos=item.adultos,
        menores=item.menores,
        mascotas=item.mascotas,
        subtotal=item.subtotal,
        desglose=item.desglose,
        comision=(
            ComisionOut(
                base=c.base,
                comision_neta=c.comision_neta,
                iva=c.iva,
                comision_total=c.comision_total,
                cargo_viajero=c.cargo_viajero,
                descuento_prestador=c.descuento_prestador,
                regla=str(c.regla_snapshot.get("nombre", "")),
            )
            if c
            else None
        ),
        fotos=[FotoOut(url=f.url, descripcion=f.descripcion) for f in p.fotos[:3]],
    )


def _reserva_out(reserva: Reserva) -> ReservaOut:
    cancelable = reserva.estado in (
        EstadoReserva.PENDIENTE_PAGO,
        EstadoReserva.PENDIENTE_APROBACION,
        EstadoReserva.CONFIRMADA,
    )
    reintegro = reservas.calcular_reintegro(reserva) if cancelable else None
    return ReservaOut(
        codigo=reserva.codigo,
        estado=reserva.estado,
        total=reserva.total,
        monto_sena=reserva.monto_sena,
        moneda=reserva.moneda,
        vence_pago_en=reserva.vence_pago_en,
        vence_aprobacion_en=reserva.vence_aprobacion_en,
        cancelada_en=reserva.cancelada_en,
        motivo_cancelacion=reserva.motivo_cancelacion,
        politica_cancelacion=reserva.politica_cancelacion,
        creada_en=reserva.creado_en,
        items=[
            _item_out(i, con_direccion=reserva.estado in privacidad.ESTADOS_CON_DIRECCION)
            for i in reserva.items
        ],
        pagos=[
            PagoOut(
                pasarela=p.pasarela, estado=p.estado, monto=p.monto, id_externo=p.id_externo
            )
            for p in reserva.pagos
        ],
        reintegro_si_cancela=(
            ReintegroOut(
                porcentaje=reintegro.porcentaje, monto=reintegro.monto, motivo=reintegro.motivo
            )
            if reintegro
            else None
        ),
    )


def _mia(codigo: str, usuario: Usuario, db: Session) -> Reserva:
    reserva = reservas.traer(db, codigo)
    if reserva is None or reserva.usuario_id != usuario.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa reserva")
    return reserva


# --- Pasarelas ---


@router.get("/pasarelas", response_model=list[PasarelaOut])
def listar_pasarelas() -> list[PasarelaOut]:
    """Con qué se puede pagar, y por qué no se puede con el resto."""
    return [
        PasarelaOut(
            codigo=p.codigo,
            nombre=p.nombre,
            disponible=p.disponible,
            reparte_automaticamente=p.reparte_automaticamente,
            motivo=None if p.disponible else p.motivo_no_disponible,
        )
        for p in pagos.todas().values()
    ]


# --- Viajero ---


@router.post("/reservas", response_model=ReservaOut, status_code=status.HTTP_201_CREATED)
def crear(
    datos: NuevaReserva,
    usuario: Usuario = Depends(con_email_verificado),
    db: Session = Depends(get_db),
) -> ReservaOut:
    unidad = db.scalar(
        select(Unidad)
        .where(Unidad.id == datos.unidad_id)
        .options(
            selectinload(Unidad.tarifas),
            selectinload(Unidad.publicacion).selectinload(Publicacion.prestador),
            selectinload(Unidad.publicacion).selectinload(Publicacion.politica_cancelacion),
            selectinload(Unidad.publicacion)
            .selectinload(Publicacion.localidad)
            .selectinload(Localidad.provincia),
        )
    )
    if unidad is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa unidad")
    if not datos.acepta_terminos:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Hay que aceptar los términos y la política de cancelación para reservar",
        )

    try:
        reserva = reservas.crear(
            db,
            usuario,
            unidad,
            datos.desde,
            datos.hasta,
            personas=datos.adultos,
            menores=datos.menores,
            mascotas=datos.mascotas,
        )
    except reservas.FechasTomadas as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except reservas.NoSePuedeReservar as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    reserva.acepto_terminos_en = datetime.now(UTC)
    reserva.version_terminos = get_settings().version_terminos
    db.commit()
    return _reserva_out(reservas.traer(db, reserva.codigo))


@router.get("/reservas", response_model=list[ReservaOut])
def mis_reservas(
    usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)
) -> list[ReservaOut]:
    codigos = list(
        db.scalars(
            select(Reserva.codigo)
            .where(Reserva.usuario_id == usuario.id)
            .order_by(Reserva.creado_en.desc())
        )
    )
    return [_reserva_out(reservas.traer(db, c)) for c in codigos]


@router.get("/reservas/{codigo}", response_model=ReservaOut)
def ver_reserva(
    codigo: str, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)
) -> ReservaOut:
    return _reserva_out(_mia(codigo, usuario, db))


@router.post("/reservas/{codigo}/pagar", response_model=PreferenciaOut)
def pagar(
    codigo: str,
    pedido: PedidoPago,
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
) -> PreferenciaOut:
    """Arma el cobro con la billetera elegida y devuelve a dónde ir a pagar."""
    reserva = _mia(codigo, usuario, db)
    if reserva.estado is not EstadoReserva.PENDIENTE_PAGO:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta reserva no está esperando el pago")
    if reserva.vence_pago_en and reserva.vence_pago_en < datetime.now(reserva.vence_pago_en.tzinfo):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Se venció el tiempo para pagar. Volvé a reservar."
        )

    try:
        pasarela = pagos.obtener(pedido.pasarela) if pedido.pasarela else pagos.predeterminada()
        pasarela.exigir_disponible()
    except pagos.PasarelaNoDisponible as e:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(e)) from e

    s = get_settings()
    item = reserva.items[0]
    comision = item.comision
    web = s.url_publica_web.rstrip("/")
    prestador = item.unidad.publicacion.prestador

    # Cobro directo: el pago se crea con la credencial del anfitrión y entra en
    # su cuenta; Mercado Pago avisa a una URL que dice de quién es la cuenta,
    # para poder consultar el pago con esa misma credencial.
    # Fuera de cobro directo la credencial del anfitrión no se usa: el pago se
    # consultaría con la de la plataforma y la reserva no se confirmaría nunca.
    credencial = cuenta_cobro.credencial(prestador) if s.mp_cobro_directo else None
    retener_comision = True
    url_notificacion = None
    if pasarela.codigo == pagos.MercadoPago.codigo and s.mp_cobro_directo:
        if not credencial:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Este alojamiento todavía no puede cobrar con Mercado Pago: el anfitrión "
                "no vinculó su cuenta.",
            )
        pasarela = pagos.MercadoPago(token=credencial)
        retener_comision = False
        api = s.url_publica_api.rstrip("/")
        # Firmada: solo Mercado Pago (que la recibió de nosotros) la conoce.
        url_notificacion = (
            f"{api}/api/v1/webhooks/mercadopago?prestador={prestador.id}"
            f"&firma={cifrado.firmar(str(prestador.id))}"
        )

    cobro = Cobro(
        codigo_reserva=reserva.codigo,
        descripcion=f"{item.unidad.publicacion.titulo} · {item.unidad.nombre}",
        total=reserva.total,
        comision_plataforma=comision.comision_total if comision else Decimal(0),
        moneda=reserva.moneda,
        email_pagador=usuario.email,
        cuenta_prestador=credencial,
        retener_comision=retener_comision,
        url_notificacion=url_notificacion,
        url_exito=f"{web}/reservas/{reserva.codigo}",
        url_fallo=f"{web}/reservas/{reserva.codigo}",
        url_pendiente=f"{web}/reservas/{reserva.codigo}",
        metadatos={"unidad": str(item.unidad_id)},
    )
    try:
        preferencia = pasarela.crear_preferencia(cobro)
    except pagos.PasarelaNoDisponible as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except pagos.ErrorDePasarela as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e

    from app.models import Pago
    from app.models.enums import TipoPago

    db.add(
        Pago(
            reserva_id=reserva.id,
            tipo=TipoPago.TOTAL,
            pasarela=pasarela.codigo,
            id_preferencia=preferencia.id_externo,
            estado="pendiente",
            monto=reserva.total,
            monto_prestador=item.subtotal - (comision.descuento_prestador if comision else 0),
            monto_comision=comision.comision_neta if comision else Decimal(0),
            iva_comision=comision.iva if comision else Decimal(0),
        )
    )
    db.commit()

    return PreferenciaOut(
        pasarela=pasarela.codigo,
        url_pago=preferencia.url_pago,
        id_externo=preferencia.id_externo,
        total=reserva.total,
    )


@router.post("/reservas/{codigo}/cancelar", response_model=ReservaOut)
def cancelar(
    codigo: str,
    datos: Cancelacion,
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
) -> ReservaOut:
    reserva = _mia(codigo, usuario, db)
    try:
        reservas.cancelar(db, reserva, datos.motivo or "Cancelada por el viajero")
    except reservas.TransicionInvalida as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    db.commit()
    return _reserva_out(reservas.traer(db, codigo))


# --- Prestador ---


def _del_prestador(codigo: str, prestador: Prestador, db: Session) -> Reserva:
    reserva = reservas.traer(db, codigo)
    if reserva is None or all(i.prestador_id != prestador.id for i in reserva.items):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa reserva")
    return reserva


@router.get("/mis-reservas", response_model=list[ReservaOut])
def reservas_del_prestador(
    prestador: Prestador = Depends(prestador_actual), db: Session = Depends(get_db)
) -> list[ReservaOut]:
    codigos = list(
        db.scalars(
            select(Reserva.codigo)
            .join(ItemReserva, ItemReserva.reserva_id == Reserva.id)
            .where(ItemReserva.prestador_id == prestador.id)
            .order_by(Reserva.creado_en.desc())
            .distinct()
        )
    )
    return [_reserva_out(reservas.traer(db, c)) for c in codigos]


@router.post("/mis-reservas/{codigo}/aprobar", response_model=ReservaOut)
def aprobar_solicitud(
    codigo: str,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> ReservaOut:
    reserva = _del_prestador(codigo, prestador, db)
    try:
        reservas.aprobar(db, reserva)
    except reservas.TransicionInvalida as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    db.commit()
    return _reserva_out(reservas.traer(db, codigo))


@router.post("/mis-reservas/{codigo}/rechazar", response_model=ReservaOut)
def rechazar_solicitud(
    codigo: str,
    datos: RespuestaPrestador,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> ReservaOut:
    reserva = _del_prestador(codigo, prestador, db)
    try:
        reservas.rechazar(db, reserva, datos.motivo)
    except reservas.TransicionInvalida as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    db.commit()
    return _reserva_out(reservas.traer(db, codigo))


# --- Webhooks ---


def _aviso_mercadopago(cuerpo: bytes, consulta: dict[str, str]) -> tuple[str, str]:
    """(tipo, id) de un aviso de Mercado Pago, venga en el cuerpo o en la URL.

    Manda los dos formatos: el de webhooks (`{"type": "payment", "data": {"id"}}`)
    y el viejo IPN (`?topic=payment&id=...`).
    """
    try:
        datos = json.loads(cuerpo or b"{}")
    except json.JSONDecodeError:
        datos = {}
    if not isinstance(datos, dict):
        datos = {}
    tipo = (
        datos.get("type") or datos.get("topic") or consulta.get("type")
        or consulta.get("topic") or ""
    )
    id_pago = (
        (datos.get("data") or {}).get("id") or consulta.get("data.id")
        or consulta.get("id") or ""
    )
    return str(tipo), str(id_pago)


@router.post("/webhooks/{codigo_pasarela}", status_code=status.HTTP_200_OK)
async def webhook(
    codigo_pasarela: str,
    peticion: Request,
    prestador: uuid.UUID | None = None,
    firma: str = "",
    db: Session = Depends(get_db),
) -> dict:
    """Notificación de una pasarela.

    Se registra antes de aplicarse: si la misma llega dos veces, la segunda no
    hace nada (docs/01 §5 R6). Siempre se responde 200 salvo que la firma sea
    inválida o la pasarela no conteste: si no, reintenta para siempre.

    Con `?prestador=` es un aviso de cobro directo: la URL va firmada (la armamos
    nosotros al crear el pago), el pago se consulta con la credencial de ese
    anfitrión, y tiene que ser de una reserva suya.
    """
    try:
        pasarela = pagos.obtener(codigo_pasarela)
    except pagos.PasarelaNoDisponible as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    cuerpo = await peticion.body()
    cabeceras = {k.lower(): v for k, v in peticion.headers.items()}
    duenio: Prestador | None = None

    try:
        if prestador is not None and pasarela.codigo == pagos.MercadoPago.codigo:
            if not cifrado.firma_valida(str(prestador), firma):
                raise pagos.NotificacionInvalida("La dirección del aviso no es nuestra")
            duenio = db.get(Prestador, prestador)
            credencial = cuenta_cobro.credencial(duenio) if duenio else None
            if not credencial:
                return {"estado": "sin cuenta de cobro"}
            tipo, id_pago = _aviso_mercadopago(cuerpo, dict(peticion.query_params))
            if tipo != "payment":
                # Órdenes, contracargos y demás: el pago avisa por su lado.
                return {"estado": "ignorada"}
            notificacion = pagos.MercadoPago(token=credencial).leer_notificacion_sin_firma(
                id_pago
            )
        else:
            notificacion = pasarela.leer_notificacion(cuerpo, cabeceras)
    except pagos.NotificacionInvalida as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    except pagos.PasarelaNoDisponible as e:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(e)) from e
    except pagos.ErrorDePasarela as e:
        # Sin respuesta de la pasarela no sabemos el estado: que reintente.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e

    registro = NotificacionPago(
        pasarela=pasarela.codigo,
        id_externo=f"{notificacion.id_externo}:{notificacion.estado.value}",
        topico="pago",
        payload=notificacion.datos or {},
    )
    db.add(registro)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"estado": "ya procesada"}

    if not notificacion.codigo_reserva:
        registro.error = "La notificación no trae el código de reserva"
        db.commit()
        return {"estado": "sin reserva"}

    reserva = reservas.traer(db, notificacion.codigo_reserva)
    if reserva is None:
        registro.error = f"No existe la reserva {notificacion.codigo_reserva}"
        db.commit()
        return {"estado": "reserva inexistente"}
    if duenio is not None and reserva.items[0].unidad.publicacion.prestador_id != duenio.id:
        registro.error = f"El pago no es de una reserva de {duenio.id}"
        db.commit()
        return {"estado": "reserva ajena"}

    reservas.registrar_pago(
        db,
        reserva,
        notificacion.id_externo,
        pasarela.codigo,
        notificacion.estado,
        notificacion.monto,
        notificacion.datos,
    )
    registro.procesada_en = datetime.now()
    db.commit()
    return {"estado": "procesada", "reserva": reserva.codigo, "resultado": reserva.estado.value}


# --- Simulador de pago (solo desarrollo) ---


class PagoSimulado(BaseModel):
    pago: str
    reserva: str
    estado: str = "aprobado"


@router.post("/simulador/pagar")
def simular_pago(datos: PagoSimulado, db: Session = Depends(get_db)) -> dict:
    """Dispara la notificación que mandaría una billetera real.

    Existe para poder recorrer el circuito completo sin credenciales. Solo
    funciona en entorno local; en cualquier otro responde que no está.
    """
    from app.services.pagos import Simulada

    simulada = Simulada()
    if not simulada.disponible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos eso")

    reserva = reservas.traer(db, datos.reserva)
    if reserva is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa reserva")

    cuerpo = json.dumps(
        {
            "pago": datos.pago,
            "reserva": reserva.codigo,
            "estado": datos.estado,
            "total": str(reserva.total),
        }
    ).encode()
    notificacion = simulada.leer_notificacion(
        cuerpo, {"x-firma-simulada": simulada.firmar(cuerpo)}
    )

    registro = NotificacionPago(
        pasarela=simulada.codigo,
        id_externo=f"{notificacion.id_externo}:{notificacion.estado.value}",
        topico="pago",
        payload=notificacion.datos or {},
    )
    db.add(registro)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"estado": "ya procesada", "reserva": reserva.codigo}

    reservas.registrar_pago(
        db,
        reserva,
        notificacion.id_externo,
        simulada.codigo,
        notificacion.estado,
        notificacion.monto,
        notificacion.datos,
    )
    registro.procesada_en = datetime.now()
    db.commit()
    return {"estado": "procesada", "reserva": reserva.codigo, "resultado": reserva.estado.value}
