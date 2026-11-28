"""Conectar calendarios sin adivinar (mejora 2): el enlace se revisa y se lee en el
momento, se sabe si Airbnb o Booking ya leen el nuestro, y si un calendario deja
de funcionar se le avisa al anfitrión una vez."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.security import crear_token
from app.models import BloqueoFecha, CalendarioExterno, LecturaCalendario, Notificacion, Usuario
from app.services import calendario, canales
from tests.conftest import HOY
from tests.test_calendario import ics

AIRBNB = "https://www.airbnb.com/calendar/ical/12345.ics?s=abc"
BOOKING = "https://admin.booking.com/hotel/hoteladmin/ical.html?t=xyz"


@pytest.fixture
def anfitrion(db, oferta):
    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    return {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}


def _url(oferta) -> str:
    return (
        f"/api/v1/mis-publicaciones/{oferta['cara'].id}/unidades/{oferta['u_cara'].id}"
        "/calendarios"
    )


def _responde(monkeypatch, estado=200, contenido=b""):
    pedidas = []

    def descargar(url):
        pedidas.append(url)
        r = httpx.Response(estado, content=contenido, request=httpx.Request("GET", url))
        return r.raise_for_status().content

    monkeypatch.setattr(calendario, "descargar", descargar)
    return pedidas


def _dia(n: int) -> str:
    return (HOY + timedelta(days=n)).strftime("%Y%m%d")


# --- Revisar el enlace antes de guardarlo ---


@pytest.mark.parametrize(
    "url, plataforma, dice",
    [
        ("https://www.airbnb.com.ar/rooms/12345", None, "enlace de tu anuncio"),
        ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/home.html", None,
         "enlace de tu anuncio"),
        (BOOKING, "airbnb", "es de Booking.com y elegiste Airbnb"),
        ("https://www.despegar.com.ar/alojamiento/123", None, "no da una dirección"),
    ],
)
def test_un_enlace_que_no_es_el_del_calendario_se_explica(url, plataforma, dice):
    with pytest.raises(canales.EnlaceEquivocado, match=dice):
        canales.revisar_enlace(url, plataforma)


@pytest.mark.parametrize(
    "url, plataforma, esperada",
    [(AIRBNB, "airbnb", "airbnb"), (BOOKING, None, "booking"),
     ("https://mi-portal.com/cal/1.ics", "otro", "otro")],
)
def test_los_enlaces_buenos_pasan(url, plataforma, esperada):
    assert canales.revisar_enlace(url, plataforma) == esperada


# --- Conectar: se lee en el momento ---


def test_al_conectar_se_lee_y_se_dice_que_se_encontro(cliente, db, oferta, anfitrion, monkeypatch):
    _responde(monkeypatch, contenido=ics((_dia(5), _dia(8)), (_dia(20), _dia(22))))
    r = cliente.post(_url(oferta), headers=anfitrion,
                     json={"nombre": "Airbnb", "url": AIRBNB, "plataforma": "airbnb"})
    assert r.status_code == 201, r.text
    aviso = r.json()["aviso"]
    assert aviso.startswith("¡Conectado! Leímos el calendario de Airbnb: 2 períodos ocupados")
    assert (HOY + timedelta(days=21)).strftime("%d/%m/%Y") in aviso  # el último día ocupado
    (c,) = r.json()["calendarios"]
    assert c["ultima_sincronizacion"] and c["ultimo_error"] is None
    assert len(db.scalars(select(BloqueoFecha).where(
        BloqueoFecha.unidad_id == oferta["u_cara"].id, BloqueoFecha.origen == "ical"
    )).all()) == 2


@pytest.mark.parametrize(
    "estado, contenido",
    [(200, b"<html><body>Tu anuncio</body></html>"), (404, b""), (403, b"")],
)
def test_un_enlace_que_no_sirve_no_se_guarda(cliente, db, oferta, anfitrion, monkeypatch,
                                             estado, contenido):
    _responde(monkeypatch, estado, contenido)
    r = cliente.post(_url(oferta), headers=anfitrion, json={"nombre": "Airbnb", "url": AIRBNB})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("No pudimos leer ese calendario:")
    assert db.scalar(select(CalendarioExterno)) is None


def test_con_el_portal_caido_se_guarda_y_se_reintenta(cliente, db, oferta, anfitrion):
    """Sin internet (el conftest): Airbnb "no responde". No es culpa del enlace."""
    r = cliente.post(_url(oferta), headers=anfitrion, json={"nombre": "Airbnb", "url": AIRBNB})
    assert r.status_code == 201, r.text
    assert r.json()["aviso"].startswith("Lo guardamos, pero ahora no pudimos leerlo")
    (c,) = r.json()["calendarios"]
    assert c["ultimo_error"] and c["error_desde"]


def test_el_enlace_del_anuncio_se_rechaza_sin_ir_a_buscarlo(cliente, db, oferta, anfitrion,
                                                           monkeypatch):
    pedidas = _responde(monkeypatch, contenido=ics())
    r = cliente.post(_url(oferta), headers=anfitrion,
                     json={"nombre": "Airbnb", "url": "https://www.airbnb.com.ar/rooms/9"})
    assert r.status_code == 422 and "anuncio" in r.json()["detail"]
    assert pedidas == []


# --- Quién lee el nuestro ---


def _leer(cliente, unidad, agente):
    return cliente.get(f"/api/v1/ical/{unidad.ical_export_token}.ics",
                       headers={"user-agent": agente})


def test_se_anota_que_airbnb_lee_nuestro_calendario(cliente, db, oferta, anfitrion):
    u = oferta["u_cara"]
    assert _leer(cliente, u, "Mozilla/5.0 (Macintosh) Chrome/120").status_code == 200
    assert db.scalar(select(LecturaCalendario)) is None  # el anfitrión probando no cuenta
    _leer(cliente, u, "Airbnb Calendar Sync (+https://www.airbnb.com)")
    _leer(cliente, u, "Booking.com iCal")
    r = cliente.get(f"/api/v1/mis-publicaciones/{oferta['cara'].id}/calendarios",
                    headers=anfitrion)
    assert r.status_code == 200, r.text
    unidad = next(x for x in r.json()["unidades"] if x["unidad_id"] == str(u.id))
    assert {x["nombre"] for x in unidad["lecturas"]} == {"Airbnb", "Booking.com"}
    assert unidad["url_exportacion"].endswith(f"{u.ical_export_token}.ics")


def test_una_lectura_seguida_no_reescribe_la_hora(db, oferta):
    u = oferta["u_cara"]
    antes = datetime.now(UTC) - timedelta(minutes=2)
    calendario.anotar_lectura(db, u.id, "airbnb", ahora=antes)
    calendario.anotar_lectura(db, u.id, "airbnb", ahora=antes + timedelta(minutes=1))
    db.expire_all()
    assert db.scalar(select(LecturaCalendario.leido_en)) == antes
    calendario.anotar_lectura(db, u.id, "airbnb", ahora=antes + timedelta(minutes=10))
    db.expire_all()
    assert db.scalar(select(LecturaCalendario.leido_en)) == antes + timedelta(minutes=10)


def test_el_resumen_es_solo_para_alojamientos_y_del_dueno(cliente, db, oferta, anfitrion):
    from datetime import date

    from app.models import Prestador

    otro = Usuario(email="otro@ejemplo.com.ar", nombre="O", apellido="O", email_verificado=True)
    db.add(otro)
    db.flush()
    db.add(Prestador(usuario_id=otro.id, razon_social="Otro", fecha_alta=date.today()))
    db.commit()
    ajeno = {"Authorization": f"Bearer {crear_token(str(otro.id))}"}
    url = f"/api/v1/mis-publicaciones/{oferta['cara'].id}/calendarios"
    assert cliente.get(url, headers=ajeno).status_code == 404


# --- Si deja de funcionar, se avisa una vez ---


def _calendario(db, oferta, error_desde=None) -> CalendarioExterno:
    c = CalendarioExterno(unidad_id=oferta["u_cara"].id, nombre="Airbnb", plataforma="airbnb",
                          url=AIRBNB, error_desde=error_desde, ultimo_error="caído")
    db.add(c)
    db.commit()
    return c


def _avisos(db):
    return db.scalars(
        select(Notificacion).where(Notificacion.evento == "calendario_con_error")
    ).all()


def test_si_falla_mas_de_un_dia_se_avisa_una_sola_vez(db, oferta, monkeypatch):
    _responde(monkeypatch, 503)
    c = _calendario(db, oferta, error_desde=datetime.now(UTC) - timedelta(hours=25))
    calendario.sincronizar_vencidos(db, ahora=datetime.now(UTC) + timedelta(hours=7))
    (aviso,) = _avisos(db)
    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    assert aviso.destino == dueno.email
    assert "Airbnb" in aviso.asunto
    assert f"/mis-publicaciones/{oferta['cara'].id}/calendarios" in aviso.cuerpo
    # Sigue fallando: no se repite el aviso.
    calendario.sincronizar_vencidos(db, ahora=datetime.now(UTC) + timedelta(hours=14))
    assert len(_avisos(db)) == 1
    # Vuelve a andar: la racha se cierra y un próximo problema avisa de nuevo.
    _responde(monkeypatch, contenido=ics())
    calendario.sincronizar(db, c)
    assert c.error_desde is None and c.aviso_error_en is None


def test_una_falla_reciente_no_avisa(db, oferta, monkeypatch):
    _responde(monkeypatch, 503)
    _calendario(db, oferta)
    calendario.sincronizar_vencidos(db)
    assert _avisos(db) == []


# --- Un calendario con eventos que se pisan ---


def test_un_calendario_con_eventos_superpuestos_se_importa_igual(db, oferta):
    """Google trae dos feriados el mismo día; antes eso hacía fallar toda la
    sincronización (la base no admite dos bloqueos superpuestos)."""
    c = CalendarioExterno(unidad_id=oferta["u_cara"].id, nombre="Feriados", url=AIRBNB)
    db.add(c)
    db.flush()
    contenido = ics(
        (_dia(5), _dia(6)), (_dia(5), _dia(6)), (_dia(5), _dia(8)), (_dia(10), _dia(11))
    )
    r = calendario.sincronizar(db, c, contenido)
    assert r.importados == 2
    bloqueos = sorted(
        calendario.limites(b) for b in db.scalars(
            select(BloqueoFecha).where(BloqueoFecha.calendario_externo_id == c.id)
        )
    )
    assert bloqueos == [
        (HOY + timedelta(days=5), HOY + timedelta(days=8)),
        (HOY + timedelta(days=10), HOY + timedelta(days=11)),
    ]
