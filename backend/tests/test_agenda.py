"""Calendario integrado entre plataformas (docs/01 §5 R3).

El anfitrión ya vende en Airbnb y en Booking. La pregunta que estas pruebas
cuidan es una sola: ¿puede ver todo lo que tiene tomado, en todas sus unidades,
en un solo lugar, y traerlo de golpe sin que un portal caído frene a los otros?
"""

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.security import crear_token
from app.models import CalendarioExterno, Unidad, Usuario
from app.services import canales
from tests.conftest import HOY, LLEGADA, SALIDA
from tests.test_calendario import ics


@pytest.fixture
def anfitrion(db, oferta):
    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    return {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}


def conectar(cliente, anfitrion, publicacion, unidad, nombre, url):
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{publicacion.id}/unidades/{unidad.id}/calendarios",
        headers=anfitrion,
        json={"nombre": nombre, "url": url},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


# --- Catálogo de plataformas ---


def test_el_catalogo_dice_donde_sacar_cada_direccion(cliente):
    plataformas = {p["codigo"]: p for p in cliente.get("/api/v1/canales").json()}
    for codigo in ("airbnb", "booking", "vrbo"):
        assert plataformas[codigo]["tiene_ical"]
        assert plataformas[codigo]["donde_esta"], f"{codigo} sin instrucciones"


def test_despegar_figura_con_el_motivo_de_por_que_no_se_puede(cliente):
    """Esconderla sería peor: el anfitrión vende ahí y necesita saber que va a mano."""
    despegar = next(
        p for p in cliente.get("/api/v1/canales").json() if p["codigo"] == "despegar"
    )
    assert despegar["tiene_ical"] is False
    assert "channel manager" in despegar["nota"]


@pytest.mark.parametrize(
    ("url", "esperado"),
    [
        ("https://www.airbnb.com/calendar/ical/1.ics?s=x", "airbnb"),
        ("https://admin.booking.com/hotel/hoteladmin/ical.html?t=x", "booking"),
        ("http://www.vrbo.com/icalendar/abc.ics", "vrbo"),
        ("https://calendar.google.com/calendar/ical/x/basic.ics", "google"),
        ("https://portal-desconocido.com.ar/cal.ics", "otro"),
    ],
)
def test_adivina_la_plataforma_por_el_dominio(url, esperado):
    assert canales.detectar(url) == esperado


def test_al_conectar_se_guarda_la_plataforma_sin_preguntarla(cliente, db, oferta, anfitrion):
    conectar(
        cliente,
        anfitrion,
        oferta["cara"],
        oferta["u_cara"],
        "El de siempre",
        "https://www.airbnb.com/calendar/ical/99.ics?s=z",
    )
    guardado = db.scalar(select(CalendarioExterno))
    assert guardado.plataforma == "airbnb"


# --- La grilla ---


def test_trae_todas_las_unidades_del_anfitrion_en_una_sola_respuesta(cliente, anfitrion, oferta):
    r = cliente.get("/api/v1/mi-calendario", headers=anfitrion)
    assert r.status_code == 200
    cuerpo = r.json()
    nombres = {(u["publicacion"], u["unidad"]) for u in cuerpo["unidades"]}
    # Incluye el borrador: el anfitrión también bloquea fechas de lo que no publicó.
    assert ("Complejo Caro", "Cabaña 1") in nombres
    assert ("Complejo Caro", "Cabaña chica") in nombres
    assert ("Cabañas Baratas", "Cabaña 1") in nombres
    assert cuerpo["resumen"]["unidades"] == len(cuerpo["unidades"])


def test_el_bloqueo_existente_aparece_con_su_origen(cliente, anfitrion, oferta):
    """La fixture deja `u_barata` tomada entre LLEGADA y SALIDA."""
    dias = (SALIDA - HOY).days + 1
    cuerpo = cliente.get(f"/api/v1/mi-calendario?dias={dias}", headers=anfitrion).json()
    barata = next(
        u for u in cuerpo["unidades"] if u["unidad_id"] == str(oferta["u_barata"].id)
    )
    tramo = next(t for t in barata["tramos"] if t["desde"] == LLEGADA.isoformat())
    assert tramo["hasta"] == SALIDA.isoformat()
    assert tramo["noches"] == (SALIDA - LLEGADA).days
    assert tramo["origen"] == "manual"


def test_no_se_ven_las_unidades_de_otro_anfitrion(cliente, db, oferta):
    ajeno = Usuario(email="ajena@ejemplo.com.ar", nombre="A", apellido="B", es_prestador=True)
    db.add(ajeno)
    db.commit()
    r = cliente.get(
        "/api/v1/mi-calendario", headers={"Authorization": f"Bearer {crear_token(str(ajeno.id))}"}
    )
    assert r.status_code in (200, 403)
    if r.status_code == 200:
        assert r.json()["unidades"] == []


def test_sin_sesion_no_hay_calendario(cliente):
    assert cliente.get("/api/v1/mi-calendario").status_code == 401


def test_la_ventana_se_puede_agrandar(cliente, anfitrion):
    corta = cliente.get("/api/v1/mi-calendario?dias=30", headers=anfitrion).json()
    larga = cliente.get("/api/v1/mi-calendario?dias=180", headers=anfitrion).json()
    assert (
        larga["hasta"] > corta["hasta"]
    ), "pedir más días tiene que correr el final de la ventana"


# --- Traer todo de una ---


def test_un_portal_caido_no_frena_a_los_demas(cliente, db, oferta, anfitrion, monkeypatch):
    """Es la razón de ser del botón: si uno falla, los otros igual se actualizan."""
    sano = "https://www.airbnb.com/calendar/ical/ok.ics"
    roto = "https://admin.booking.com/hotel/hoteladmin/ical.html?t=roto"
    conectar(cliente, anfitrion, oferta["cara"], oferta["u_cara"], "Airbnb", sano)
    conectar(cliente, anfitrion, oferta["barata"], oferta["u_barata"], "Booking", roto)

    desde = (HOY + timedelta(days=5)).strftime("%Y%m%d")
    hasta = (HOY + timedelta(days=8)).strftime("%Y%m%d")

    def descarga(url, **kw):
        pedido = httpx.Request("GET", url)
        if url == roto:
            return httpx.Response(503, request=pedido)
        return httpx.Response(200, content=ics((desde, hasta)), request=pedido)

    monkeypatch.setattr(
        "app.services.calendario.descargar", lambda url: descarga(url).raise_for_status().content
    )

    r = cliente.post("/api/v1/mi-calendario/sincronizar", headers=anfitrion)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["sincronizados"] == 1
    assert cuerpo["con_error"] == 1

    ok = next(x for x in cuerpo["resultados"] if x["nombre"] == "Airbnb")
    falla = next(x for x in cuerpo["resultados"] if x["nombre"] == "Booking")
    assert ok["ok"] is True
    assert falla["ok"] is False
    # Y el motivo es accionable, no el nombre de una excepción de Python.
    assert "503" in falla["detalle"]
    assert "Error" not in falla["detalle"]

    # Lo que sí se pudo traer quedó tomado de verdad.
    unidad = db.get(Unidad, oferta["u_cara"].id)
    cuerpo = cliente.get("/api/v1/mi-calendario?dias=30", headers=anfitrion).json()
    cara = next(u for u in cuerpo["unidades"] if u["unidad_id"] == str(unidad.id))
    assert any(t["origen"] == "ical" for t in cara["tramos"])


def test_la_direccion_vencida_se_explica_en_castellano(cliente, oferta, anfitrion, monkeypatch):
    conectar(
        cliente,
        anfitrion,
        oferta["cara"],
        oferta["u_cara"],
        "Airbnb",
        "https://www.airbnb.com/calendar/ical/vieja.ics",
    )
    monkeypatch.setattr(
        "app.services.calendario.descargar",
        lambda url: httpx.Response(403, request=httpx.Request("GET", url)).raise_for_status(),
    )
    detalle = cliente.post("/api/v1/mi-calendario/sincronizar", headers=anfitrion).json()[
        "resultados"
    ][0]["detalle"]
    assert "caduca" in detalle and "sacala de nuevo" in detalle.lower()


def test_una_unidad_tiene_un_tope_de_calendarios(cliente, anfitrion, oferta):
    """Cada uno se descarga solo cada hora: sin tope, una cuenta podría usar el
    servidor para pedirle a terceros cientos de direcciones."""
    from app.services import calendario as agenda

    p, u = oferta["cara"], oferta["u_cara"]
    for i in range(agenda.MAX_POR_UNIDAD):
        conectar(cliente, anfitrion, p, u, f"Cal {i}", f"https://airbnb.test/{i}.ics")
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{p.id}/unidades/{u.id}/calendarios",
        headers=anfitrion,
        json={"nombre": "Uno más", "url": "https://airbnb.test/extra.ics"},
    )
    assert r.status_code == 409
