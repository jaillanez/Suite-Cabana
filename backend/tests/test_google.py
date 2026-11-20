"""El ingreso con Google se prueba con una clave propia: se firma un token como lo
haría Google y se reemplaza el proveedor de claves públicas. Sin esto, la única
verificación posible sería contra los servidores de Google en cada corrida."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Usuario
from app.services import google

CLIENT_ID = "123456.apps.googleusercontent.com"


@pytest.fixture
def firmar(monkeypatch):
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class ClaveFalsa:
        key = clave.public_key()

    monkeypatch.setattr(
        google._claves, "get_signing_key_from_jwt", lambda _token: ClaveFalsa(), raising=False
    )
    get_settings.cache_clear()
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)

    def hacer(**cambios) -> str:
        ahora = datetime.now(UTC)
        datos = {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "sub": "1029384756",
            "email": "jorge@gmail.com",
            "email_verified": True,
            "given_name": "Jorge",
            "family_name": "Illanez",
            "iat": ahora,
            "exp": ahora + timedelta(hours=1),
        }
        datos.update(cambios)
        return jwt.encode(datos, clave, algorithm="RS256")

    yield hacer
    get_settings.cache_clear()


def test_sin_client_id_avisa_que_falta_configurarlo(cliente, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    r = cliente.post("/api/v1/auth/google", json={"credencial": "x" * 30})
    assert r.status_code == 501
    assert "GOOGLE_CLIENT_ID" in r.json()["detail"]
    get_settings.cache_clear()


def test_crea_la_cuenta_y_la_deja_verificada(cliente, db, firmar):
    r = cliente.post("/api/v1/auth/google", json={"credencial": firmar()})
    assert r.status_code == 200, r.text
    assert r.json()["token"]

    usuario = db.scalar(select(Usuario).where(Usuario.email == "jorge@gmail.com"))
    assert usuario is not None
    assert usuario.google_sub == "1029384756"
    assert usuario.email_verificado is True  # Google ya lo verificó
    assert usuario.hash_password is None


def test_el_segundo_ingreso_no_duplica_la_cuenta(cliente, db, firmar):
    cliente.post("/api/v1/auth/google", json={"credencial": firmar()})
    cliente.post("/api/v1/auth/google", json={"credencial": firmar()})
    cuentas = db.scalars(select(Usuario).where(Usuario.email == "jorge@gmail.com")).all()
    assert len(cuentas) == 1


def test_vincula_con_una_cuenta_existente_de_contrasena(cliente, db, firmar):
    """Misma persona, mismo correo: se vincula, no se duplica."""
    cliente.post(
        "/api/v1/auth/registro",
        json={
            "email": "jorge@gmail.com",
            "password": "unaclavelarga",
            "nombre": "Jorge",
            "apellido": "Illanez", "acepta_terminos": True,
        },
    )
    r = cliente.post("/api/v1/auth/google", json={"credencial": firmar()})
    assert r.status_code == 200

    cuentas = db.scalars(select(Usuario).where(Usuario.email == "jorge@gmail.com")).all()
    assert len(cuentas) == 1
    assert cuentas[0].google_sub == "1029384756"
    assert cuentas[0].hash_password is not None  # sigue pudiendo entrar con contraseña


def test_rechaza_un_token_para_otra_aplicacion(cliente, firmar):
    token = firmar(aud="otra-app.apps.googleusercontent.com")
    r = cliente.post("/api/v1/auth/google", json={"credencial": token})
    assert r.status_code == 401


def test_rechaza_un_emisor_que_no_es_google(cliente, firmar):
    token = firmar(iss="https://malicioso.example")
    r = cliente.post("/api/v1/auth/google", json={"credencial": token})
    assert r.status_code == 401


def test_rechaza_un_token_vencido(cliente, firmar):
    ayer = datetime.now(UTC) - timedelta(days=1)
    r = cliente.post(
        "/api/v1/auth/google",
        json={"credencial": firmar(exp=ayer, iat=ayer - timedelta(hours=1))},
    )
    assert r.status_code == 401


def test_rechaza_basura(cliente, firmar):
    r = cliente.post("/api/v1/auth/google", json={"credencial": "no-es-un-token-pero-es-largo"})
    assert r.status_code == 401


def test_si_google_dice_que_el_correo_no_esta_verificado_no_lo_damos_por_verificado(
    cliente, db, firmar
):
    cliente.post("/api/v1/auth/google", json={"credencial": firmar(email_verified=False)})
    usuario = db.scalar(select(Usuario).where(Usuario.email == "jorge@gmail.com"))
    assert usuario.email_verificado is False
