"""Registro, ingreso, verificación de correo y roles (docs/01 §5 R1).

Decisiones que conviene tener a la vista:

- El token de sesión es un JWT firmado con `tipo: "acceso"`. Los de verificación de
  correo llevan otro tipo, así que un enlace de verificación no sirve para entrar.
- El correo de verificación se envía por SMTP al registrarse y cada vez que se
  pide. En local sin SMTP el endpoint devuelve el enlace para poder probar el
  circuito; en cualquier otro entorno no lo devuelve nunca.
- El teléfono no se verifica: sirve para que viajero y anfitrión se escriban por
  WhatsApp con la reserva confirmada (`app.services.contacto`). Se guarda
  normalizado.
- Un usuario puede ser viajero y prestador a la vez; `es_operador` no se
  auto-asigna nunca desde acá.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import prestador_actual, usuario_actual
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    TokenInvalido,
    crear_token,
    hashear_password,
    leer_token,
    verificar_password,
)
from app.models import Notificacion, Prestador, Usuario
from app.models.enums import CanalNotificacion, EstadoNotificacion
from app.services import contacto, cuenta_cobro, google
from app.services.notificaciones.base import ErrorDeEnvio, Mensaje
from app.services.notificaciones.correo import CorreoSMTP
from app.services.pagos import ErrorDePasarela
from app.services.pagos.mercadopago import CredencialInvalida

router = APIRouter(prefix="/auth", tags=["auth"])

TIPO_VERIFICACION = "verificacion_email"


class Registro(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]
    nombre: Annotated[str, Field(min_length=1, max_length=120)]
    apellido: Annotated[str, Field(min_length=1, max_length=120)]
    telefono: Annotated[str | None, Field(default=None, max_length=30)] = None
    acepta_terminos: bool = Field(
        default=False, description="docs/01 §5 R11: se aceptan al registrarse"
    )


class Ingreso(BaseModel):
    email: EmailStr
    password: str


class Sesion(BaseModel):
    token: str
    tipo_token: str = "bearer"
    expira_en_minutos: int


class PrestadorOut(BaseModel):
    id: UUID
    razon_social: str
    cuit: str | None
    condicion_iva: str | None
    verificado: bool
    puede_publicar: bool
    cuenta_cobro_vinculada: bool
    cuenta_cobro: str | None = Field(
        default=None, description="Nombre de la cuenta de Mercado Pago vinculada"
    )
    porcentaje_sena: int | None


class UsuarioOut(BaseModel):
    id: UUID
    email: EmailStr
    nombre: str
    apellido: str
    telefono: str | None
    email_verificado: bool
    telefono_verificado: bool
    acepto_terminos_en: datetime | None
    es_viajero: bool
    es_prestador: bool
    es_operador: bool
    prestador: PrestadorOut | None = None


class AltaPrestador(BaseModel):
    razon_social: Annotated[str, Field(min_length=2, max_length=200)]
    cuit: Annotated[str, Field(min_length=11, max_length=13)]
    condicion_iva: Annotated[str, Field(min_length=2, max_length=40)]
    porcentaje_sena: Annotated[int | None, Field(default=None, ge=0, le=100)] = None


class VerificacionPedida(BaseModel):
    enviado: bool
    detalle: str
    enlace: str | None = Field(
        default=None, description="Solo en entorno local, mientras no haya envío de correo"
    )


def _prestador_out(p: Prestador | None) -> PrestadorOut | None:
    if p is None:
        return None
    return PrestadorOut(
        id=p.id,
        razon_social=p.razon_social,
        cuit=p.cuit,
        condicion_iva=p.condicion_iva,
        verificado=p.verificado,
        puede_publicar=p.puede_publicar,
        cuenta_cobro_vinculada=bool(p.mp_user_id),
        cuenta_cobro=p.mp_cuenta,
        porcentaje_sena=p.porcentaje_sena,
    )


def _usuario_out(u: Usuario, db: Session) -> UsuarioOut:
    prestador = db.scalar(select(Prestador).where(Prestador.usuario_id == u.id))
    return UsuarioOut(
        id=u.id,
        email=u.email,
        nombre=u.nombre,
        apellido=u.apellido,
        telefono=u.telefono,
        email_verificado=u.email_verificado,
        telefono_verificado=u.telefono_verificado,
        acepto_terminos_en=u.acepto_terminos_en,
        es_viajero=u.es_viajero,
        es_prestador=u.es_prestador,
        es_operador=u.es_operador,
        prestador=_prestador_out(prestador),
    )


def _sesion(usuario: Usuario) -> Sesion:
    s = get_settings()
    return Sesion(
        token=crear_token(str(usuario.id)),
        expira_en_minutos=s.access_token_minutes,
    )


#: Entre un correo de verificación y el siguiente a la misma cuenta.
ESPERA_VERIFICACION = timedelta(minutes=2)
EVENTO_VERIFICACION = "verificacion_email"


def _enlace_verificacion(usuario: Usuario, db: Session) -> VerificacionPedida:
    """Manda el enlace de verificación por correo.

    Va directo y no por el buzón: quien lo pide está esperando en la pantalla, y
    sin el correo verificado no puede reservar. Cada envío queda registrado en
    el buzón, y entre dos envíos a la misma cuenta tiene que pasar un rato: si
    no, el endpoint serviría para inundar una casilla.
    """
    s = get_settings()
    token = crear_token(
        str(usuario.id), tipo=TIPO_VERIFICACION, minutos=s.minutos_token_verificacion
    )
    ruta = f"/verificar-email?token={token}"
    if s.environment == "local" and not s.smtp_host:
        return VerificacionPedida(
            enviado=False,
            detalle="En local no se mandan correos: usá el enlace de abajo para verificar.",
            enlace=ruta,
        )

    canal = CorreoSMTP()
    if not canal.disponible:
        return VerificacionPedida(
            enviado=False,
            detalle="Todavía no podemos mandar correos. Probá de nuevo más tarde.",
        )
    ultimo = db.scalar(
        select(func.max(Notificacion.creado_en)).where(
            Notificacion.usuario_id == usuario.id,
            Notificacion.evento == EVENTO_VERIFICACION,
        )
    )
    if ultimo is not None and datetime.now(ultimo.tzinfo) - ultimo < ESPERA_VERIFICACION:
        return VerificacionPedida(
            enviado=False,
            detalle="Ya te mandamos un enlace hace un momento. Esperá un par de minutos.",
        )

    enlace = f"{s.url_publica_web.rstrip('/')}{ruta}"
    horas = s.minutos_token_verificacion // 60
    mensaje = Mensaje(
        destino=usuario.email,
        asunto="Confirmá tu correo",
        cuerpo=(
                    f"Hola, {usuario.nombre}:\n\n"
                    "Para terminar de crear tu cuenta y poder reservar, confirmá tu "
                    f"correo con este enlace:\n\n{enlace}\n\n"
                    f"Vale por {horas} horas. Si no creaste una cuenta, ignorá este "
                    "mensaje.\n"
        ),
    )
    # El registro no guarda el enlace: es una credencial para entrar a verificar.
    registro = Notificacion(
        usuario_id=usuario.id,
        canal=CanalNotificacion.EMAIL,
        evento=EVENTO_VERIFICACION,
        destino=usuario.email,
        asunto=mensaje.asunto,
        cuerpo="(enlace de verificación, no se guarda)",
        estado=EstadoNotificacion.PENDIENTE,
        datos={},
    )
    db.add(registro)
    try:
        canal.enviar(mensaje)
    except ErrorDeEnvio as e:
        registro.estado = EstadoNotificacion.FALLIDA
        registro.error = str(e)
        db.commit()
        return VerificacionPedida(
            enviado=False,
            detalle="No pudimos mandarte el correo. Probá de nuevo en un rato.",
        )
    registro.estado = EstadoNotificacion.ENVIADA
    registro.enviada_en = datetime.now(UTC)
    db.commit()
    return VerificacionPedida(
        enviado=True,
        detalle=f"Te mandamos un enlace a {usuario.email}. Revisá también el spam.",
    )


@router.post("/registro", response_model=Sesion, status_code=status.HTTP_201_CREATED)
def registro(datos: Registro, db: Session = Depends(get_db)) -> Sesion:
    email = datos.email.lower().strip()
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay una cuenta con ese correo")

    if not datos.acepta_terminos:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Hay que aceptar los términos y la política de privacidad para crear la cuenta",
        )

    usuario = Usuario(
        email=email,
        hash_password=hashear_password(datos.password),
        nombre=datos.nombre.strip(),
        apellido=datos.apellido.strip(),
        telefono=_telefono(datos.telefono),
        acepto_terminos_en=datetime.now(UTC),
        version_terminos=get_settings().version_terminos,
    )
    db.add(usuario)
    db.commit()
    # Si el correo no sale, la cuenta igual queda creada: se puede pedir de nuevo
    # desde Mi cuenta.
    _enlace_verificacion(usuario, db)
    return _sesion(usuario)


@router.post("/ingreso", response_model=Sesion)
def ingreso(datos: Ingreso, db: Session = Depends(get_db)) -> Sesion:
    usuario = db.scalar(select(Usuario).where(Usuario.email == datos.email.lower().strip()))
    # El mismo mensaje para correo inexistente y contraseña errada: si no, el
    # formulario dice qué correos están registrados.
    generico = "El correo o la contraseña no coinciden"
    if usuario is None or not usuario.hash_password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, generico)
    if not verificar_password(datos.password, usuario.hash_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, generico)
    if not usuario.activo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "La cuenta está dada de baja")
    return _sesion(usuario)


class CredencialGoogle(BaseModel):
    credencial: Annotated[str, Field(min_length=20, description="El id_token que devuelve Google")]


@router.post("/google", response_model=Sesion)
def ingreso_google(datos: CredencialGoogle, db: Session = Depends(get_db)) -> Sesion:
    """Ingreso con Google (docs/01 §5 R1).

    Si el correo ya tiene cuenta con contraseña, se vincula en vez de duplicarla:
    es la misma persona y el correo ya está probado del lado de Google.
    """
    client_id = get_settings().google_client_id
    if not client_id:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "El ingreso con Google todavía no está configurado: falta GOOGLE_CLIENT_ID.",
        )

    try:
        identidad = google.verificar(datos.credencial, client_id)
    except google.TokenGoogleInvalido as e:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "No pudimos validar tu cuenta de Google"
        ) from e

    # Sin correo verificado por Google no se crea ni se vincula nada: si no,
    # cualquiera con una cuenta de Google que diga tener tu correo entraría a
    # la tuya.
    if not identidad.email_verificado:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Tu cuenta de Google no tiene el correo verificado. Verificalo en Google "
            "o ingresá con tu correo y contraseña.",
        )

    existente = db.scalar(select(Usuario).where(Usuario.google_sub == identidad.sub)) or db.scalar(
        select(Usuario).where(Usuario.email == identidad.email)
    )
    if existente is not None:
        # El chequeo de baja va solo sobre cuentas que ya existen: en una recién
        # creada `activo` todavía no tomó su valor por defecto.
        if not existente.activo:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "La cuenta está dada de baja")
        existente.google_sub = identidad.sub
        usuario = existente
    else:
        usuario = Usuario(
            email=identidad.email,
            google_sub=identidad.sub,
            nombre=identidad.nombre or "Sin nombre",
            apellido=identidad.apellido or "",
            activo=True,
        )
        db.add(usuario)

    # Google ya verificó el correo: no tiene sentido pedirlo de nuevo.
    if identidad.email_verificado:
        usuario.email_verificado = True

    db.commit()
    return _sesion(usuario)


def _telefono(texto: str | None) -> str | None:
    if not texto or not texto.strip():
        return None
    try:
        return contacto.normalizar(texto)
    except contacto.TelefonoInvalido as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


class NuevoTelefono(BaseModel):
    # Sin largo mínimo acá: si no, el rechazo sale en inglés (Pydantic) y no con
    # el mensaje de contacto.normalizar.
    telefono: Annotated[str, Field(max_length=30)]


@router.put("/telefono", response_model=UsuarioOut)
def cambiar_telefono(
    datos: NuevoTelefono,
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
) -> UsuarioOut:
    """El WhatsApp de la cuenta: el viajero lo necesita para reservar y el
    anfitrión para mandar a revisión."""
    usuario.telefono = _telefono(datos.telefono)
    db.commit()
    return _usuario_out(usuario, db)


@router.get("/yo", response_model=UsuarioOut)
def yo(usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> UsuarioOut:
    return _usuario_out(usuario, db)


@router.post("/verificacion", response_model=VerificacionPedida)
def pedir_verificacion(
    usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)
) -> VerificacionPedida:
    if usuario.email_verificado:
        return VerificacionPedida(enviado=False, detalle="Tu correo ya está verificado")
    return _enlace_verificacion(usuario, db)


class ConfirmacionEmail(BaseModel):
    token: str


@router.post("/verificacion/confirmar", response_model=UsuarioOut)
def confirmar_email(datos: ConfirmacionEmail, db: Session = Depends(get_db)) -> UsuarioOut:
    try:
        sujeto = leer_token(datos.token, tipo=TIPO_VERIFICACION)
    except TokenInvalido as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "El enlace venció o no es válido. Pedí uno nuevo."
        ) from e

    usuario = db.get(Usuario, UUID(sujeto))
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontramos esa cuenta")
    usuario.email_verificado = True
    db.commit()
    return _usuario_out(usuario, db)


@router.post("/prestador", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def alta_prestador(
    datos: AltaPrestador,
    usuario: Usuario = Depends(usuario_actual),
    db: Session = Depends(get_db),
) -> UsuarioOut:
    """Un viajero se convierte también en prestador. Publicar requiere además la
    cuenta de cobro vinculada, que se hace por separado con Mercado Pago."""
    if db.scalar(select(Prestador).where(Prestador.usuario_id == usuario.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya cargaste tus datos de prestador")

    cuit = datos.cuit.replace("-", "").strip()
    if not cuit.isdigit() or len(cuit) != 11:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El CUIT tiene 11 dígitos")
    if db.scalar(select(Prestador).where(Prestador.cuit == cuit)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese CUIT ya está registrado")

    db.add(
        Prestador(
            usuario_id=usuario.id,
            razon_social=datos.razon_social.strip(),
            cuit=cuit,
            condicion_iva=datos.condicion_iva.strip(),
            porcentaje_sena=datos.porcentaje_sena,
        )
    )
    usuario.es_prestador = True
    db.commit()
    return _usuario_out(usuario, db)


@router.get("/prestador", response_model=PrestadorOut)
def mi_prestador(prestador: Prestador = Depends(prestador_actual)) -> PrestadorOut:
    salida = _prestador_out(prestador)
    assert salida is not None
    return salida


class CredencialMercadoPago(BaseModel):
    access_token: Annotated[str, Field(min_length=20, max_length=300)] = Field(
        description="Access Token de producción de la cuenta de Mercado Pago del anfitrión"
    )


@router.put("/prestador/mercadopago", response_model=PrestadorOut)
def vincular_mercadopago(
    datos: CredencialMercadoPago,
    prestador: Prestador = Depends(prestador_actual),
    db: Session = Depends(get_db),
) -> PrestadorOut:
    """El anfitrión carga su credencial: desde ahí, lo que se le reserva le entra
    directo a su cuenta. Se prueba con Mercado Pago antes de guardarla, se guarda
    cifrada y no se devuelve nunca."""
    try:
        cuenta_cobro.vincular(prestador, datos.access_token)
    except CredencialInvalida as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except ErrorDePasarela as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    db.commit()
    salida = _prestador_out(prestador)
    assert salida is not None
    return salida


@router.delete("/prestador/mercadopago", response_model=PrestadorOut)
def desvincular_mercadopago(
    prestador: Prestador = Depends(prestador_actual), db: Session = Depends(get_db)
) -> PrestadorOut:
    cuenta_cobro.desvincular(prestador)
    db.commit()
    salida = _prestador_out(prestador)
    assert salida is not None
    return salida
