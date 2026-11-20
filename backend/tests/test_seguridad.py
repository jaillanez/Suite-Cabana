"""Controles que existen para que un usuario no pueda usar la plataforma contra
ella misma o contra otros: descargas a la red interna, cuentas ajenas por Google,
pagos por menos de lo debido y fórmulas en las exportaciones."""

import socket

import httpx
import pytest

from app.core.config import get_settings
from app.core.security import crear_token
from app.models import Reserva, Usuario
from app.services import google, red, reservas
from tests.test_api_reservas import notificar, reservar, viajero  # noqa: F401  (fixture)

# --- Descargas de direcciones que pega un usuario ---


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/cal.ics",
        "http://127.0.0.1/cal.ics",
        "http://10.0.0.5/cal.ics",
        "http://172.18.0.1/cal.ics",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/cal.ics",
        "http://usuario:clave@airbnb.com/cal.ics",
        "https://airbnb.com:8443/cal.ics",
        "file:///etc/passwd",
        "gopher://airbnb.com/",
        "http://postgres.internal/cal.ics",
    ],
)
def test_no_se_aceptan_direcciones_que_no_son_internet_publica(url):
    with pytest.raises(red.DireccionNoPermitida):
        red.validar_forma(url)


def test_una_direccion_publica_normal_se_acepta():
    red.validar_forma("https://www.airbnb.com/calendar/ical/123.ics?s=abc")


def _resolver_a(ip):
    def resolver(host, puerto, *a, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, puerto))]

    return resolver


def test_un_nombre_que_resuelve_a_la_red_interna_no_se_descarga(monkeypatch):
    monkeypatch.setattr(red.socket, "getaddrinfo", _resolver_a("172.18.0.1"))
    with pytest.raises(red.DireccionNoPermitida):
        red.descargar_publica("https://calendario.ejemplo.com/a.ics", agente="t", tiempo=1)


def test_una_redireccion_a_la_red_interna_no_se_sigue(monkeypatch):
    def resolver(host, puerto, *a, **kw):
        ip = "93.184.216.34" if host == "calendario.ejemplo.com" else "10.0.0.7"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, puerto))]

    monkeypatch.setattr(red.socket, "getaddrinfo", resolver)
    vistos = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        vistos.append(pedido)
        return httpx.Response(302, headers={"location": "http://interno.ejemplo.com/x"})

    original = httpx.Client
    monkeypatch.setattr(
        red.httpx, "Client",
        lambda *a, **kw: original(*a, **{**kw, "transport": httpx.MockTransport(responder)}),
    )
    with pytest.raises(red.DireccionNoPermitida):
        red.descargar_publica("https://calendario.ejemplo.com/a.ics", agente="t", tiempo=1)
    # Se fue a la IP revisada, con el nombre en Host.
    assert len(vistos) == 1
    assert vistos[0].url.host == "93.184.216.34"
    assert vistos[0].headers["host"] == "calendario.ejemplo.com"


def test_conectar_un_calendario_interno_se_rechaza(cliente, db, oferta):
    usuario = db.get(Usuario, oferta["prestador"].usuario_id)
    cabecera = {"Authorization": f"Bearer {crear_token(str(usuario.id))}"}
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{oferta['cara'].id}/unidades/"
        f"{oferta['u_cara'].id}/calendarios",
        headers=cabecera,
        json={"nombre": "Booking", "url": "http://172.18.0.1:8021/"},
    )
    assert r.status_code == 422


# --- Google ---


def test_google_sin_correo_verificado_no_entra_a_una_cuenta_existente(
    cliente, viajero, monkeypatch  # noqa: F811
):
    monkeypatch.setattr(get_settings(), "google_client_id", "cliente-de-prueba")
    monkeypatch.setattr(
        google, "verificar",
        lambda c, cid: google.IdentidadGoogle(
            sub="atacante", email="viajera@ejemplo.com.ar", email_verificado=False,
            nombre="X", apellido="Y",
        ),
    )
    r = cliente.post("/api/v1/auth/google", json={"credencial": "x" * 40})
    assert r.status_code == 401
    assert "verificado" in r.json()["detail"]


# --- Monto ---


def _pagar(cliente, viajero, oferta, total):  # noqa: F811
    reserva = reservar(cliente, viajero, oferta).json()
    codigo = reserva["codigo"]
    pago = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={}).json()
    total = reserva["total"] if total is None else total
    return codigo, notificar(cliente, pago["id_externo"], codigo, total=total).json()


def test_un_pago_aprobado_por_menos_no_confirma(cliente, db, viajero, oferta):  # noqa: F811
    codigo, r = _pagar(cliente, viajero, oferta, "1.00")
    assert r["resultado"] == "pendiente_pago"
    reserva = db.query(Reserva).filter(Reserva.codigo == codigo).one()
    assert reserva.pagos[0].estado == reservas.ESTADO_MONTO_DISTINTO


def test_un_pago_aprobado_por_el_total_confirma(cliente, viajero, oferta):  # noqa: F811
    _, r = _pagar(cliente, viajero, oferta, None)
    assert r["resultado"] == "confirmada"


# --- Exportación ---


def test_la_exportacion_neutraliza_formulas(cliente, db, oferta):
    from app.api.v1.panel import _celda

    assert _celda("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")"
    assert _celda("@SUMA(A1)") == "'@SUMA(A1)"
    assert _celda("-2+3") == "'-2+3"
    assert _celda("Cabañas del Lago") == "Cabañas del Lago"


# --- Dirección del alojamiento ---


def test_la_ficha_publica_no_da_la_direccion_ni_el_punto_exacto(cliente, db, oferta):
    oferta["cara"].direccion = "Av. Siempreviva 742"
    db.commit()
    ficha = cliente.get(f"/api/v1/publicaciones/{oferta['cara'].slug}").json()
    assert "direccion" not in ficha
    assert "Siempreviva" not in str(ficha)
    assert ficha["lat"] == round(ficha["lat"], 2)
    assert ficha["lon"] == round(ficha["lon"], 2)


def test_la_direccion_aparece_recien_con_la_reserva_confirmada(
    cliente, db, viajero, oferta  # noqa: F811
):
    oferta["cara"].direccion = "Av. Siempreviva 742"
    db.commit()
    reserva = reservar(cliente, viajero, oferta).json()
    codigo = reserva["codigo"]
    assert reserva["items"][0]["direccion"] is None
    assert reserva["items"][0]["lat"] is None

    pago = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={}).json()
    notificar(cliente, pago["id_externo"], codigo, total=reserva["total"])
    item = cliente.get(f"/api/v1/reservas/{codigo}", headers=viajero).json()["items"][0]
    assert item["direccion"] == "Av. Siempreviva 742"
    from app.services.publicaciones import _coordenadas

    assert (item["lat"], item["lon"]) == _coordenadas(db, oferta["cara"].id)


def test_los_resultados_de_busqueda_muestran_el_punto_aproximado(cliente, oferta):
    from tests.test_api_reservas import FECHAS

    r = cliente.get(
        "/api/v1/publicaciones/buscar",
        params={"localidad": "bariloche", **FECHAS, "personas": 2},
    ).json()
    assert r["resultados"]
    for x in r["resultados"]:
        assert x["lat"] == round(x["lat"], 2) and x["lon"] == round(x["lon"], 2)


def test_la_distancia_publica_va_en_kilometros_enteros(cliente, oferta):
    from tests.test_api_reservas import FECHAS

    r = cliente.get(
        "/api/v1/publicaciones/buscar",
        params={"lat": -41.1, "lon": -71.3, "radio_km": 49.37, **FECHAS, "personas": 2},
    ).json()
    assert r["resultados"]
    for x in r["resultados"]:
        assert x["distancia_km"] == int(x["distancia_km"]) and x["distancia_km"] >= 1


def test_el_radio_se_redondea_a_kilometros():
    from app.services.privacidad import distancia_publica, radio_publico

    assert radio_publico(0.3) == 1 and radio_publico(2.01) == 3
    assert distancia_publica(0.2) == 1 and distancia_publica(7.6) == 8
