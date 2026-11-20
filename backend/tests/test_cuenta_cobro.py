"""Cobro directo: cada anfitrión carga su credencial de Mercado Pago y cobra en
su cuenta.

Mercado Pago no se llama de verdad: se reemplaza el cliente HTTP por uno que
responde como la API y deja ver qué se le mandó.
"""

import json

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.models import NotificacionPago, Reserva
from app.services import cifrado, cuenta_cobro
from app.services.pagos import mercadopago as mp
from tests.test_api_reservas import reservar, viajero  # noqa: F401  (fixture)
from tests.test_auth import encabezado, registrar

TOKEN = "APP_USR-1234567890-abcdef-anfitrion"


@pytest.fixture
def cobro_directo(monkeypatch):
    monkeypatch.setattr(get_settings(), "mp_cobro_directo", True)


class FalsoMercadoPago:
    """Responde como la API de Mercado Pago y guarda lo que recibió."""

    def __init__(self):
        self.pedidos: list[httpx.Request] = []
        self.pagos: dict[str, dict] = {}

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        if pedido.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"message": "invalid access token"})
        if pedido.url.path == "/users/me":
            return httpx.Response(200, json={"id": 4242, "nickname": "CABANASANA", "tags": []})
        if pedido.url.path == "/checkout/preferences":
            return httpx.Response(201, json={"id": "PREF-1", "init_point": "https://mp/pagar"})
        if pedido.url.path.startswith("/v1/payments/"):
            pago = self.pagos.get(pedido.url.path.rsplit("/", 1)[-1])
            if pago is None:
                return httpx.Response(404, json={"message": "not found"})
            return httpx.Response(200, json=pago)
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


def _vincular(oferta, db):
    oferta["prestador"].mp_user_id = "4242"
    oferta["prestador"].mp_access_token = cifrado.cifrar(TOKEN)
    db.commit()


def _alta_prestador(cliente) -> dict:
    cabecera = encabezado(registrar(cliente))
    r = cliente.post(
        "/api/v1/auth/prestador",
        headers=cabecera,
        json={"razon_social": "Cabañas de Ana", "cuit": "27301234564",
              "condicion_iva": "Monotributo"},
    )
    assert r.status_code == 201, r.text
    return cabecera


# --- Cifrado ---


def test_la_credencial_se_guarda_cifrada_y_se_recupera():
    guardado = cifrado.cifrar(TOKEN)
    assert TOKEN not in guardado
    assert cifrado.descifrar(guardado) == TOKEN


def test_un_valor_alterado_no_se_descifra():
    guardado = cifrado.cifrar(TOKEN)
    with pytest.raises(cifrado.SecretoIlegible):
        cifrado.descifrar(guardado[:-4] + "AAAA")


def test_fuera_de_local_sin_clave_de_cifrado_no_arranca():
    with pytest.raises(ValueError, match="CLAVE_CIFRADO"):
        Settings(environment="production", secret_key="x" * 40, clave_cifrado="")


# --- Vincular ---


def test_vincular_prueba_la_credencial_y_no_la_devuelve(cliente, db, api_mp):
    cabecera = _alta_prestador(cliente)
    r = cliente.put(
        "/api/v1/auth/prestador/mercadopago", headers=cabecera, json={"access_token": TOKEN}
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["cuenta_cobro_vinculada"] is True
    assert cuerpo["cuenta_cobro"] == "CABANASANA"
    assert cuerpo["puede_publicar"] is True
    assert TOKEN not in r.text

    from app.models import Prestador

    prestador = db.scalar(select(Prestador).where(Prestador.cuit == "27301234564"))
    assert prestador.mp_user_id == "4242"
    assert prestador.mp_access_token != TOKEN
    assert cuenta_cobro.credencial(prestador) == TOKEN


def test_una_credencial_que_mercado_pago_no_reconoce_no_se_guarda(cliente, db, api_mp):
    cabecera = _alta_prestador(cliente)
    r = cliente.put(
        "/api/v1/auth/prestador/mercadopago",
        headers=cabecera,
        json={"access_token": "APP_USR-0000000000-inventada"},
    )
    assert r.status_code == 422
    assert "no reconoce" in r.json()["detail"]
    r = cliente.get("/api/v1/auth/prestador", headers=cabecera)
    assert r.json()["cuenta_cobro_vinculada"] is False


def test_en_produccion_no_se_acepta_una_credencial_de_prueba(db, oferta, monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "production")
    monkeypatch.setattr(
        cuenta_cobro, "verificar_credencial",
        lambda t: mp.CuentaMercadoPago(id="1", nombre="TESTUSER", de_prueba=True),
    )
    with pytest.raises(mp.CredencialInvalida, match="prueba"):
        cuenta_cobro.vincular(oferta["prestador"], "TEST-123456789012345678")
    assert oferta["prestador"].mp_access_token is None


def test_desvincular_borra_la_credencial(cliente, db, api_mp):
    cabecera = _alta_prestador(cliente)
    cliente.put(
        "/api/v1/auth/prestador/mercadopago", headers=cabecera, json={"access_token": TOKEN}
    )
    r = cliente.delete("/api/v1/auth/prestador/mercadopago", headers=cabecera)
    assert r.status_code == 200
    assert r.json()["cuenta_cobro_vinculada"] is False
    assert r.json()["puede_publicar"] is False


# --- Cobrar ---


def test_el_pago_se_crea_con_la_cuenta_del_anfitrion(
    cliente, db, viajero, oferta, cobro_directo, api_mp  # noqa: F811
):
    _vincular(oferta, db)
    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    r = cliente.post(
        f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={"pasarela": "mercadopago"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["url_pago"] == "https://mp/pagar"

    pedido = next(p for p in api_mp.pedidos if p.url.path == "/checkout/preferences")
    assert pedido.headers["authorization"] == f"Bearer {TOKEN}"
    cuerpo = json.loads(pedido.content)
    # Con credencial propia Mercado Pago no deja retener la comisión.
    assert "marketplace_fee" not in cuerpo
    assert cuerpo["notification_url"].endswith(f"?prestador={oferta['prestador'].id}")
    assert cuerpo["external_reference"] == codigo


def test_sin_cuenta_vinculada_no_se_puede_pagar_con_mercado_pago(
    cliente, viajero, oferta, cobro_directo  # noqa: F811
):
    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    r = cliente.post(
        f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={"pasarela": "mercadopago"}
    )
    assert r.status_code == 409
    assert "vinculó" in r.json()["detail"]


# --- Avisos de pago ---


def _avisar(cliente, oferta, id_pago, tipo="payment"):
    return cliente.post(
        f"/api/v1/webhooks/mercadopago?prestador={oferta['prestador'].id}",
        json={"type": tipo, "data": {"id": id_pago}},
    )


def test_pendiente_y_despues_aprobado_confirma_la_reserva(
    cliente, db, viajero, oferta, cobro_directo, api_mp  # noqa: F811
):
    """Un pago en efectivo avisa dos veces. El segundo aviso no puede perderse."""
    _vincular(oferta, db)
    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={})
    total = db.scalar(select(Reserva).where(Reserva.codigo == codigo)).total
    pago = {"id": 777, "external_reference": codigo, "transaction_amount": str(total)}

    api_mp.pagos["777"] = {**pago, "status": "pending"}
    r = _avisar(cliente, oferta, "777")
    assert r.json()["estado"] == "procesada"
    assert r.json()["resultado"] == "pendiente_pago"

    api_mp.pagos["777"] = {**pago, "status": "approved"}
    r = _avisar(cliente, oferta, "777")
    assert r.json()["estado"] == "procesada"
    assert r.json()["resultado"] == "confirmada"

    # Y el mismo aviso repetido no vuelve a aplicarse.
    assert _avisar(cliente, oferta, "777").json()["estado"] == "ya procesada"
    registros = db.scalars(
        select(NotificacionPago).where(NotificacionPago.pasarela == "mercadopago")
    ).all()
    assert len(registros) == 2


def test_un_aviso_con_un_pago_inexistente_no_confirma_nada(
    cliente, db, viajero, oferta, cobro_directo, api_mp  # noqa: F811
):
    _vincular(oferta, db)
    reservar(cliente, viajero, oferta)
    r = _avisar(cliente, oferta, "999")
    assert r.status_code == 502  # Mercado Pago no lo encuentra: no sabemos nada


def test_un_pago_de_otra_reserva_no_se_aplica(
    cliente, db, viajero, oferta, cobro_directo, api_mp  # noqa: F811
):
    _vincular(oferta, db)
    api_mp.pagos["555"] = {
        "id": 555, "external_reference": "NO-EXISTE", "status": "approved",
        "transaction_amount": "1",
    }
    assert _avisar(cliente, oferta, "555").json()["estado"] == "reserva inexistente"


def test_los_avisos_que_no_son_de_pagos_se_ignoran(
    cliente, db, oferta, cobro_directo, api_mp
):
    _vincular(oferta, db)
    r = _avisar(cliente, oferta, "123", tipo="merchant_order")
    assert r.status_code == 200
    assert r.json()["estado"] == "ignorada"
