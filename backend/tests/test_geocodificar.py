"""Ubicar en el mapa a partir de la dirección: al guardar la primera vez y con el
botón. Sin red: la consulta a Nominatim se reemplaza."""

from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.core.security import crear_token
from app.models import Publicacion, Usuario
from app.services import geocodificar as geo
from app.services.busqueda import lat_lon

BASE = "/api/v1/mis-publicaciones"
CENTRO_BARILOCHE = geo.Punto(-41.1335, -71.3103)


@pytest.fixture(autouse=True)
def _memoria_limpia():
    geo._memoria.clear()
    yield
    geo._memoria.clear()


@pytest.fixture
def anfitrion(db, oferta):
    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    return {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}


# --- El servicio ---


def test_una_direccion_lejos_de_la_localidad_no_se_acepta(monkeypatch):
    """"San Martín 120" existe en cientos de pueblos: un punto en otra provincia
    es peor que ninguno."""
    monkeypatch.setattr(geo, "_consultar", lambda texto: (-31.53, -68.52))  # San Juan
    assert geo.ubicar("San Martín 120", "Bariloche", "Río Negro", CENTRO_BARILOCHE) is None
    monkeypatch.setattr(geo, "_consultar", lambda texto: (-41.14, -71.30))
    assert geo.ubicar("Mitre 120", "Bariloche", "Río Negro", CENTRO_BARILOCHE) == geo.Punto(
        -41.14, -71.30
    )


def test_se_busca_con_la_localidad_y_la_provincia(monkeypatch):
    pedidos = []
    monkeypatch.setattr(geo, "_consultar", lambda texto: pedidos.append(texto))
    geo.ubicar("Mitre 120", "Bariloche", "Río Negro", None)
    assert pedidos == ["Mitre 120, Bariloche, Río Negro, Argentina"]
    assert geo.ubicar("ab", "Bariloche", "Río Negro", None) is None  # muy corta: ni se consulta
    assert len(pedidos) == 1


def _con_url(monkeypatch):
    monkeypatch.setattr(
        geo, "get_settings",
        lambda: SimpleNamespace(geocodificador_url="https://geo.invalid/search",
                                url_publica_web="https://alojateaqui.com.ar"),
    )
    monkeypatch.setattr(geo, "ESPERA_MINIMA_S", 0)


def test_la_consulta_se_identifica_y_se_recuerda(monkeypatch):
    _con_url(monkeypatch)
    llamadas = []

    def falso_get(url, params, headers, timeout):
        llamadas.append((params["q"], headers["User-Agent"], params["countrycodes"]))
        return httpx.Response(200, json=[{"lat": "-41.14", "lon": "-71.30"}],
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(geo.httpx, "get", falso_get)
    assert geo._consultar("Mitre 120, Bariloche") == (-41.14, -71.30)
    assert geo._consultar("Mitre 120, Bariloche") == (-41.14, -71.30)
    # Una sola salida a la red, identificada con el sitio y sin datos de nadie.
    assert llamadas == [
        ("Mitre 120, Bariloche", "SuiteCabana/1.0 (+https://alojateaqui.com.ar)", "ar")
    ]


@pytest.mark.parametrize(
    "respuesta",
    [httpx.ConnectTimeout("lento"), httpx.Response(503), httpx.Response(200, json=[{"x": 1}])],
)
def test_si_el_servicio_falla_no_se_rompe_nada(monkeypatch, respuesta):
    _con_url(monkeypatch)

    def falso_get(url, **_):
        if isinstance(respuesta, Exception):
            raise respuesta
        respuesta.request = httpx.Request("GET", url)
        return respuesta

    monkeypatch.setattr(geo.httpx, "get", falso_get)
    assert geo._consultar("Mitre 120") is None


def test_sin_url_no_sale_a_la_red(monkeypatch):
    monkeypatch.setattr(geo.httpx, "get", lambda *a, **k: pytest.fail("salió a la red"))
    assert geo._consultar("Mitre 120") is None  # los tests corren sin geocodificador


# --- En el editor ---


def _nueva(cliente, anfitrion, oferta) -> dict:
    r = cliente.post(
        BASE, headers=anfitrion,
        json={"titulo": "Cabañas del Arroyo", "localidad_id": str(oferta["cara"].localidad_id)},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _punto(db, publicacion_id):
    return db.execute(
        select(*lat_lon(Publicacion.ubicacion)).where(Publicacion.id == publicacion_id)
    ).one()


def test_al_guardar_la_direccion_por_primera_vez_se_ubica_sola(
    cliente, db, anfitrion, oferta, monkeypatch
):
    pedidos = []

    def ubicar(direccion, localidad, provincia, centro):
        pedidos.append((direccion, localidad))
        return geo.Punto(-41.14, -71.30)

    monkeypatch.setattr(geo, "ubicar", ubicar)
    p = _nueva(cliente, anfitrion, oferta)
    assert p["lat"] is None
    r = cliente.patch(f"{BASE}/{p['id']}", headers=anfitrion, json={"direccion": "Mitre 120"})
    assert r.status_code == 200, r.text
    assert (r.json()["lat"], r.json()["lon"]) == (pytest.approx(-41.14), pytest.approx(-71.30))
    assert pedidos == [("Mitre 120", oferta["cara"].localidad.nombre)]

    # Con el punto ya puesto (quizá corrido a mano), cambiar la dirección no lo pisa.
    cliente.patch(f"{BASE}/{p['id']}", headers=anfitrion, json={"lat": -41.15, "lon": -71.31})
    cliente.patch(f"{BASE}/{p['id']}", headers=anfitrion, json={"direccion": "Moreno 50"})
    assert len(pedidos) == 1
    assert _punto(db, p["id"]) == (pytest.approx(-41.15), pytest.approx(-71.31))


def test_si_no_se_encuentra_se_guarda_igual_sin_punto(cliente, anfitrion, oferta, monkeypatch):
    monkeypatch.setattr(geo, "ubicar", lambda *a: None)
    p = _nueva(cliente, anfitrion, oferta)
    r = cliente.patch(f"{BASE}/{p['id']}", headers=anfitrion, json={"direccion": "Calle 123"})
    assert r.status_code == 200
    assert r.json()["direccion"] == "Calle 123" and r.json()["lat"] is None


def test_el_boton_ubica_con_la_direccion_guardada(cliente, anfitrion, oferta, monkeypatch):
    p = _nueva(cliente, anfitrion, oferta)
    url = f"{BASE}/{p['id']}/ubicar-por-direccion"
    r = cliente.post(url, headers=anfitrion)
    assert r.status_code == 422 and "guardá la dirección" in r.json()["detail"]

    monkeypatch.setattr(geo, "ubicar", lambda *a: None)
    cliente.patch(f"{BASE}/{p['id']}", headers=anfitrion, json={"direccion": "Calle Falsa 123"})
    r = cliente.post(url, headers=anfitrion)
    assert r.status_code == 422 and "marcá el punto en el mapa" in r.json()["detail"]

    monkeypatch.setattr(geo, "ubicar", lambda *a: geo.Punto(-41.14, -71.30))
    r = cliente.post(url, headers=anfitrion)
    assert r.status_code == 200, r.text
    assert r.json()["lat"] == pytest.approx(-41.14)


def test_otro_prestador_no_ubica_lo_ajeno(cliente, db, oferta):
    from datetime import date

    from app.models import Prestador

    otro = Usuario(email="otro@ejemplo.com.ar", nombre="O", apellido="O", email_verificado=True)
    db.add(otro)
    db.flush()
    db.add(Prestador(usuario_id=otro.id, razon_social="Otro", fecha_alta=date.today()))
    db.flush()
    ajeno = {"Authorization": f"Bearer {crear_token(str(otro.id))}"}
    r = cliente.post(f"{BASE}/{oferta['cara'].id}/ubicar-por-direccion", headers=ajeno)
    assert r.status_code == 404
