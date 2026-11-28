"""Mercado Pago con un botón (OAuth): el anfitrión autoriza en Mercado Pago, vuelve
conectado, y en cada cobro Mercado Pago retiene la comisión de la plataforma.

Mercado Pago no se llama de verdad: un falso responde como su API y deja ver qué
se le pidió.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import crear_token
from app.models import Pago, Usuario
from app.services import cifrado, cuenta_cobro, mp_oauth, reservas
from app.services.pagos import mercadopago as mp
from app.services.pagos.base import EstadoPago
from tests.conftest import LLEGADA, SALIDA
from tests.test_api_reservas import reservar, viajero  # noqa: F401  (fixture)

TOKEN = "APP_USR-oauth-anfitrion"
REFRESH = "TG-renovar-anfitrion"


class FalsoMercadoPago:
    def __init__(self):
        self.pedidos: list[httpx.Request] = []
        self.cuenta = 4242
        self.token_dice = 4242
        self.oauth_falla = False
        self.preferencias: list[dict] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        if pedido.url.path == "/oauth/token":
            if self.oauth_falla:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={
                "access_token": TOKEN, "refresh_token": REFRESH, "user_id": self.token_dice,
                "expires_in": 15552000, "live_mode": True,
            })
        if pedido.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"message": "invalid access token"})
        if pedido.url.path == "/users/me":
            return httpx.Response(200, json={"id": self.cuenta, "nickname": "CABANASANA"})
        if pedido.url.path == "/checkout/preferences":
            import json

            self.preferencias.append(json.loads(pedido.content))
            return httpx.Response(201, json={"id": "PREF-1", "init_point": "https://mp/pagar"})
        return httpx.Response(404)


@pytest.fixture
def api_mp(monkeypatch):
    falso = FalsoMercadoPago()
    original = httpx.Client

    def cliente(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(falso)
        return original(*args, **kwargs)

    monkeypatch.setattr(mp.httpx, "Client", cliente)
    return falso


@pytest.fixture
def aplicacion(monkeypatch):
    """La aplicación de Mercado Pago de la plataforma, configurada."""
    s = get_settings()
    monkeypatch.setattr(s, "mp_client_id", "123456")
    monkeypatch.setattr(s, "mp_client_secret", "secreto-app")
    monkeypatch.setattr(s, "mp_cobro_directo", True)
    monkeypatch.setattr(s, "url_publica_web", "https://alojateaqui.com.ar")


@pytest.fixture
def anfitrion(db, oferta):
    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    return {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}


def _estado(oferta) -> str:
    return crear_token(str(oferta["prestador"].usuario_id), tipo=mp_oauth.TIPO_ESTADO, minutos=15)


def _desvinculado(db, oferta):
    p = oferta["prestador"]
    cuenta_cobro.desvincular(p)
    db.commit()
    return p


# --- El botón ---


def test_el_boton_lleva_a_mercado_pago_con_un_state_del_usuario(
    cliente, oferta, anfitrion, aplicacion
):
    r = cliente.get("/api/v1/auth/prestador/mercadopago/conectar", headers=anfitrion)
    assert r.status_code == 200, r.text
    url = urlsplit(r.json()["url"])
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.netloc == "auth.mercadopago.com.ar"
    assert q["client_id"] == "123456" and q["response_type"] == "code"
    assert q["redirect_uri"] == "https://alojateaqui.com.ar/cuenta/mercadopago"
    mp_oauth.validar_estado(q["state"], str(oferta["prestador"].usuario_id))


def test_sin_la_aplicacion_configurada_el_boton_no_esta(cliente, anfitrion):
    yo = cliente.get("/api/v1/auth/prestador", headers=anfitrion)
    assert yo.json()["conexion_mp_disponible"] is False
    r = cliente.get("/api/v1/auth/prestador/mercadopago/conectar", headers=anfitrion)
    assert r.status_code == 501


# --- La vuelta ---


def test_la_vuelta_conecta_la_cuenta_y_la_guarda_cifrada(
    cliente, db, oferta, anfitrion, aplicacion, api_mp
):
    p = _desvinculado(db, oferta)
    r = cliente.post(
        "/api/v1/auth/prestador/mercadopago/oauth", headers=anfitrion,
        json={"code": "TG-codigo", "state": _estado(oferta)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["cuenta_cobro_con_boton"] is True
    assert r.json()["cuenta_cobro"] == "CABANASANA"
    assert r.json()["cuenta_cobro_vinculada"] is True

    db.refresh(p)
    assert p.mp_oauth and p.mp_user_id == "4242"
    assert TOKEN not in p.mp_access_token and REFRESH not in p.mp_refresh_token
    assert cuenta_cobro.credencial(p) == TOKEN
    assert p.mp_token_vence_en > datetime.now(UTC) + timedelta(days=170)

    # Lo que se le pidió a Mercado Pago: el code, la vuelta y el secreto de la app.
    (pedido,) = [x for x in api_mp.pedidos if x.url.path == "/oauth/token"]
    cuerpo = {k: v[0] for k, v in parse_qs(pedido.content.decode()).items()}
    assert cuerpo == {
        "client_id": "123456", "client_secret": "secreto-app",
        "grant_type": "authorization_code", "code": "TG-codigo",
        "redirect_uri": "https://alojateaqui.com.ar/cuenta/mercadopago",
    }


def test_un_state_de_otra_cuenta_no_conecta_nada(
    cliente, db, oferta, anfitrion, aplicacion, api_mp
):
    """Sin esto, un atacante podría hacer que un anfitrión cobre en la cuenta del
    atacante: le manda el enlace de vuelta con su propio code."""
    p = _desvinculado(db, oferta)
    ajeno = crear_token("00000000-0000-0000-0000-000000000000", tipo=mp_oauth.TIPO_ESTADO)
    for estado in (ajeno, crear_token(str(p.usuario_id))):  # otro usuario; un token de acceso
        r = cliente.post(
            "/api/v1/auth/prestador/mercadopago/oauth", headers=anfitrion,
            json={"code": "TG-codigo", "state": estado},
        )
        assert r.status_code == 422
    assert api_mp.pedidos == []  # ni se fue a cambiar el code
    db.refresh(p)
    assert p.mp_user_id is None and not p.mp_oauth


def test_un_state_vencido_no_conecta(cliente, db, oferta, anfitrion, aplicacion, api_mp):
    vencido = crear_token(str(oferta["prestador"].usuario_id), tipo=mp_oauth.TIPO_ESTADO,
                          minutos=-1)
    r = cliente.post(
        "/api/v1/auth/prestador/mercadopago/oauth", headers=anfitrion,
        json={"code": "TG-codigo", "state": vencido},
    )
    assert r.status_code == 422 and "venció" in r.json()["detail"]


@pytest.mark.parametrize("problema", ["rechazo", "otra_cuenta"])
def test_si_mercado_pago_no_cierra_no_se_guarda_nada(
    cliente, db, oferta, anfitrion, aplicacion, api_mp, problema
):
    p = _desvinculado(db, oferta)
    if problema == "rechazo":
        api_mp.oauth_falla = True
    else:
        api_mp.token_dice = 9999  # el token dice una cuenta y /users/me otra
    r = cliente.post(
        "/api/v1/auth/prestador/mercadopago/oauth", headers=anfitrion,
        json={"code": "TG-codigo", "state": _estado(oferta)},
    )
    assert r.status_code == 422
    db.refresh(p)
    assert p.mp_access_token is None and not p.mp_oauth


def test_pegar_una_credencial_a_mano_no_queda_como_conectada_con_boton(
    db, oferta, aplicacion, api_mp
):
    p = oferta["prestador"]
    p.mp_oauth = True
    cuenta_cobro.vincular(p, TOKEN)
    assert p.mp_oauth is False and p.mp_token_vence_en is None


# --- Cobrar ---


def _conectar(db, p, oauth: bool):
    p.mp_user_id = "4242"
    p.mp_access_token = cifrado.cifrar(TOKEN)
    p.mp_oauth = oauth
    db.commit()


@pytest.mark.parametrize("oauth", [True, False])
def test_con_el_boton_mercado_pago_retiene_la_comision(
    cliente, db, oferta, viajero, aplicacion, api_mp, oauth  # noqa: F811
):
    _conectar(db, oferta["prestador"], oauth)
    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    r = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero,
                     json={"pasarela": "mercadopago"})
    assert r.status_code == 200, r.text

    reserva = reservas.traer(db, codigo)
    comision = sum((i.comision.comision_total for i in reserva.items), Decimal(0))
    (preferencia,) = api_mp.preferencias
    (pago,) = db.scalars(select(Pago).where(Pago.reserva_id == reserva.id)).all()
    if oauth:
        # Comisión más IVA, descontada por Mercado Pago en el mismo pago.
        assert Decimal(str(preferencia["marketplace_fee"])) == comision
        assert pago.comision_retenida == comision
    else:
        # Con una credencial pegada a mano no se puede: se factura aparte.
        assert "marketplace_fee" not in preferencia
        assert pago.comision_retenida == 0


def test_con_sena_se_retiene_como_mucho_la_sena(cliente, db, oferta, viajero, aplicacion, api_mp):  # noqa: F811
    _conectar(db, oferta["prestador"], True)
    oferta["cara"].porcentaje_sena = 5  # una seña más chica que la comisión (10 % + IVA)
    db.commit()
    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero,
                 json={"pasarela": "mercadopago"})
    (preferencia,) = api_mp.preferencias
    assert preferencia["marketplace_fee"] == preferencia["items"][0]["unit_price"]


# --- Renovación ---


def test_las_credenciales_por_vencer_se_renuevan(db, oferta, aplicacion, api_mp):
    p = oferta["prestador"]
    _conectar(db, p, True)
    p.mp_refresh_token = cifrado.cifrar(REFRESH)
    p.mp_token_vence_en = datetime.now(UTC) + timedelta(days=10)
    db.flush()
    assert cuenta_cobro.renovar_por_vencer(db) == {"mp_renovadas": 1, "mp_sin_renovar": 0}
    assert p.mp_token_vence_en > datetime.now(UTC) + timedelta(days=170)
    (pedido,) = [x for x in api_mp.pedidos if x.url.path == "/oauth/token"]
    assert "grant_type=refresh_token" in pedido.content.decode()

    # Con margen no se toca; si Mercado Pago no renueva o dice otra cuenta, tampoco.
    assert cuenta_cobro.renovar_por_vencer(db) == {"mp_renovadas": 0, "mp_sin_renovar": 0}
    p.mp_token_vence_en = datetime.now(UTC) + timedelta(days=5)
    api_mp.token_dice = 9999
    db.flush()
    assert cuenta_cobro.renovar_por_vencer(db) == {"mp_renovadas": 0, "mp_sin_renovar": 1}
    assert p.mp_token_vence_en < datetime.now(UTC) + timedelta(days=6)


def test_el_resumen_separa_lo_retenido_de_lo_que_hay_que_facturar(
    cliente, db, oferta, viajero, aplicacion, api_mp  # noqa: F811
):
    """Una reserva cobrada con el botón (comisión retenida) y otra con credencial
    pegada a mano (comisión a facturar aparte)."""
    p = oferta["prestador"]
    totales = {}
    for oauth, dias in ((True, 0), (False, 10)):
        _conectar(db, p, oauth)
        fechas = {"desde": (LLEGADA + timedelta(days=dias)).isoformat(),
                  "hasta": (SALIDA + timedelta(days=dias)).isoformat()}
        codigo = reservar(cliente, viajero, oferta, **fechas).json()["codigo"]
        cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero,
                     json={"pasarela": "mercadopago"})
        r = reservas.traer(db, codigo)
        reservas.registrar_pago(db, r, f"mp-{dias}", "mercadopago", EstadoPago.APROBADO,
                                monto=r.total)
        db.commit()
        totales[oauth] = sum((i.comision.comision_total for i in r.items), Decimal(0))

    operador = Usuario(email="op@ejemplo.com.ar", nombre="O", apellido="P", es_operador=True,
                       email_verificado=True)
    db.add(operador)
    db.commit()
    cabecera = {"Authorization": f"Bearer {crear_token(str(operador.id))}"}
    resumen = cliente.get("/api/v1/admin/comisiones", headers=cabecera).json()
    assert Decimal(resumen["retenida_por_mercadopago"]) == totales[True]
    assert Decimal(resumen["a_facturar_aparte"]) == totales[False]
