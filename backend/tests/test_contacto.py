"""WhatsApp entre viajero y anfitrión: el botón de la reserva confirmada."""

from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from app.models import Usuario
from app.services import contacto
from tests.test_alta_publicaciones import _crear, catalogo, prestador  # noqa: F401
from tests.test_api_reservas import notificar, reservar, viajero  # noqa: F401
from tests.test_api_salones import evento  # noqa: F401
from tests.test_paneles import cuenta
from tests.test_salones import salon  # noqa: F401

# --- Normalizar ---


@pytest.mark.parametrize(
    ("escrito", "guardado"),
    [
        ("0264 15 412-3456", "+5492644123456"),  # a la vieja usanza, con 0 y 15
        ("264 412 3456", "+5492644123456"),
        ("+54 9 264 412-3456", "+5492644123456"),
        ("+54 264 412 3456", "+5492644123456"),  # sin el 9
        ("5492644123456", "+5492644123456"),
        ("011 15 5555-0000", "+5491155550000"),
        ("02966 15 123456", "+5492966123456"),  # característica de 4 cifras
        ("+56 9 1234 5678", "+56912345678"),  # otro país: tal cual
        ("0056 9 1234 5678", "+56912345678"),
    ],
)
def test_el_numero_se_guarda_normalizado(escrito, guardado):
    assert contacto.normalizar(escrito) == guardado


@pytest.mark.parametrize("escrito", ["123", "hola", "264 412", "+1 2"])
def test_un_numero_que_no_es_celular_se_rechaza(escrito):
    with pytest.raises(contacto.TelefonoInvalido):
        contacto.normalizar(escrito)


# --- Reservar pide el WhatsApp ---


def test_sin_whatsapp_no_se_reserva_y_se_puede_dar_al_reservar(cliente, db, oferta):
    sin = cuenta(cliente, db, "sintel@ejemplo.com.ar")
    usuario = db.scalar(select(Usuario).where(Usuario.email == "sintel@ejemplo.com.ar"))
    usuario.telefono = None
    db.commit()

    r = reservar(cliente, sin, oferta)
    assert r.status_code == 428  # la web muestra el campo y reenvía
    assert "WhatsApp" in r.json()["detail"]

    assert reservar(cliente, sin, oferta, telefono="cualquier cosa").status_code == 422
    r = reservar(cliente, sin, oferta, telefono="0264 15 412-3456")
    assert r.status_code == 201, r.text
    db.refresh(usuario)
    assert usuario.telefono == "+5492644123456"  # queda en la cuenta


def test_el_whatsapp_se_cambia_desde_la_cuenta(cliente, db, viajero):  # noqa: F811
    r = cliente.put("/api/v1/auth/telefono", headers=viajero, json={"telefono": "11 5555 0000"})
    assert r.status_code == 200
    assert r.json()["telefono"] == "+5491155550000"
    r = cliente.put("/api/v1/auth/telefono", headers=viajero, json={"telefono": "123456"})
    assert r.status_code == 422


# --- El botón ---


def _confirmar(cliente, viajero, reserva):  # noqa: F811
    pago = cliente.post(
        f"/api/v1/reservas/{reserva['codigo']}/pagar", headers=viajero, json={}
    ).json()
    notificar(cliente, pago["id_externo"], reserva["codigo"], total=reserva["total"])


def test_el_boton_aparece_solo_con_la_reserva_confirmada(cliente, db, viajero, oferta):  # noqa: F811
    from app.core.security import crear_token

    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    anfitrion = {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}
    reserva = reservar(cliente, viajero, oferta).json()
    codigo = reserva["codigo"]

    # Esperando el pago: nadie ve el número del otro.
    assert reserva["whatsapp"] is None
    assert all(r["whatsapp"] is None for r in cliente.get(
        "/api/v1/mis-reservas", headers=anfitrion).json())

    _confirmar(cliente, viajero, reserva)

    para_viajero = cliente.get(f"/api/v1/reservas/{codigo}", headers=viajero).json()["whatsapp"]
    url = urlsplit(para_viajero)
    assert url.netloc == "wa.me"
    assert url.path == "/5492944000000"  # el del anfitrión
    texto = parse_qs(url.query)["text"][0]
    assert codigo in texto and "Complejo Caro" in texto

    del_anfitrion = next(
        r for r in cliente.get("/api/v1/mis-reservas", headers=anfitrion).json()
        if r["codigo"] == codigo
    )["whatsapp"]
    url = urlsplit(del_anfitrion)
    assert url.path == "/5492644123456"  # el de la viajera
    assert parse_qs(url.query)["text"][0].startswith("Hola Ana")

    # Cancelada, ya no hay nada que coordinar.
    r = cliente.post(f"/api/v1/reservas/{codigo}/cancelar", headers=viajero, json={})
    assert r.json()["whatsapp"] is None


def test_un_numero_viejo_mal_escrito_no_arma_un_enlace_roto(cliente, db, viajero, oferta):  # noqa: F811
    """Antes el teléfono se guardaba como lo escribía cada uno."""
    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    dueno.telefono = "llamar al fijo"
    db.commit()
    reserva = reservar(cliente, viajero, oferta).json()
    _confirmar(cliente, viajero, reserva)
    r = cliente.get(f"/api/v1/reservas/{reserva['codigo']}", headers=viajero).json()
    assert r["estado"] == "confirmada"
    assert r["whatsapp"] is None


# --- El anfitrión ---


def test_sin_whatsapp_el_anfitrion_no_manda_a_revision(cliente, db, prestador, catalogo):  # noqa: F811
    pid = _crear(cliente, prestador, catalogo)
    yo = cliente.get("/api/v1/auth/yo", headers=prestador).json()
    usuario = db.get(Usuario, yo["id"])
    usuario.telefono = None
    db.commit()
    r = cliente.post(f"/api/v1/mis-publicaciones/{pid}/enviar-a-revision", headers=prestador)
    assert any("WhatsApp" in f for f in r.json()["detail"]["faltantes"])

    cliente.put("/api/v1/auth/telefono", headers=prestador, json={"telefono": "351 400 0000"})
    r = cliente.post(f"/api/v1/mis-publicaciones/{pid}/enviar-a-revision", headers=prestador)
    assert not any("WhatsApp" in f for f in r.json()["detail"]["faltantes"])


def test_el_salon_tambien_pide_el_whatsapp(cliente, db, evento):  # noqa: F811
    from tests.test_api_salones import _reservar

    sin = cuenta(cliente, db, "sintel-salon@ejemplo.com.ar")
    usuario = db.scalar(select(Usuario).where(Usuario.email == "sintel-salon@ejemplo.com.ar"))
    usuario.telefono = None
    db.commit()
    franja = str(evento["noche"].id)
    assert _reservar(cliente, sin, evento, franja_id=franja).status_code == 428
    r = _reservar(cliente, sin, evento, franja_id=franja, telefono="264 412 3456")
    assert r.status_code == 201, r.text
