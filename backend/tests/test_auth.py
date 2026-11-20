import pytest

from app.core.security import crear_token
from app.models import Prestador, Usuario

REGISTRO = {
    "email": "Ana@Ejemplo.com.ar",
    "password": "unaclavelarga",
    "nombre": "Ana",
    "apellido": "Pérez", "acepta_terminos": True,
    "telefono": "2645550000",
}


def registrar(cliente, **cambios) -> str:
    datos = {**REGISTRO, **cambios}
    r = cliente.post("/api/v1/auth/registro", json=datos)
    assert r.status_code == 201, r.text
    return r.json()["token"]


def encabezado(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_registro_devuelve_sesion_y_guarda_el_usuario(cliente, db):
    token = registrar(cliente)
    assert token
    usuario = db.query(Usuario).filter(Usuario.email == "ana@ejemplo.com.ar").one()
    assert usuario.nombre == "Ana"
    assert usuario.es_viajero is True
    assert usuario.es_prestador is False
    assert usuario.email_verificado is False


def test_la_contrasena_no_se_guarda_en_texto(cliente, db):
    registrar(cliente)
    usuario = db.query(Usuario).filter(Usuario.email == "ana@ejemplo.com.ar").one()
    assert usuario.hash_password
    assert "unaclavelarga" not in usuario.hash_password


def test_el_correo_no_distingue_mayusculas_y_no_se_repite(cliente):
    registrar(cliente)
    r = cliente.post("/api/v1/auth/registro", json={**REGISTRO, "email": "ANA@ejemplo.com.ar"})
    assert r.status_code == 409


def test_contrasena_corta_se_rechaza(cliente):
    r = cliente.post("/api/v1/auth/registro", json={**REGISTRO, "password": "corta"})
    assert r.status_code == 422


def test_ingreso_con_credenciales_correctas(cliente):
    registrar(cliente)
    r = cliente.post(
        "/api/v1/auth/ingreso", json={"email": "ana@ejemplo.com.ar", "password": "unaclavelarga"}
    )
    assert r.status_code == 200
    assert r.json()["token"]


def test_ingreso_fallido_no_revela_si_el_correo_existe(cliente):
    registrar(cliente)
    existente = cliente.post(
        "/api/v1/auth/ingreso", json={"email": "ana@ejemplo.com.ar", "password": "otraclavelarga"}
    )
    inexistente = cliente.post(
        "/api/v1/auth/ingreso", json={"email": "nadie@ejemplo.com.ar", "password": "otraclavelarga"}
    )
    assert existente.status_code == inexistente.status_code == 401
    assert existente.json()["detail"] == inexistente.json()["detail"]


def test_yo_necesita_sesion(cliente):
    assert cliente.get("/api/v1/auth/yo").status_code == 401
    assert cliente.get("/api/v1/auth/yo", headers=encabezado("basura")).status_code == 401


def test_yo_devuelve_el_usuario(cliente):
    token = registrar(cliente)
    r = cliente.get("/api/v1/auth/yo", headers=encabezado(token))
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["email"] == "ana@ejemplo.com.ar"
    assert cuerpo["es_viajero"] is True
    assert cuerpo["prestador"] is None


def test_un_token_de_verificacion_no_sirve_para_entrar(cliente, db):
    registrar(cliente)
    usuario = db.query(Usuario).filter(Usuario.email == "ana@ejemplo.com.ar").one()
    token = crear_token(str(usuario.id), tipo="verificacion_email")
    assert cliente.get("/api/v1/auth/yo", headers=encabezado(token)).status_code == 401


def test_circuito_de_verificacion_de_correo(cliente, db):
    token = registrar(cliente)
    pedido = cliente.post("/api/v1/auth/verificacion", headers=encabezado(token))
    assert pedido.status_code == 200
    enlace = pedido.json()["enlace"]
    assert enlace and "token=" in enlace  # en local se devuelve para poder probar

    verificacion = enlace.split("token=")[1]
    r = cliente.post("/api/v1/auth/verificacion/confirmar", json={"token": verificacion})
    assert r.status_code == 200
    assert r.json()["email_verificado"] is True

    usuario = db.query(Usuario).filter(Usuario.email == "ana@ejemplo.com.ar").one()
    db.refresh(usuario)
    assert usuario.email_verificado is True


def test_token_de_verificacion_invalido(cliente):
    r = cliente.post("/api/v1/auth/verificacion/confirmar", json={"token": "no-es-un-token"})
    assert r.status_code == 400


def test_un_token_de_acceso_no_sirve_para_verificar(cliente):
    token = registrar(cliente)
    r = cliente.post("/api/v1/auth/verificacion/confirmar", json={"token": token})
    assert r.status_code == 400


def test_alta_de_prestador_suma_el_rol_sin_sacar_el_de_viajero(cliente, db):
    token = registrar(cliente)
    r = cliente.post(
        "/api/v1/auth/prestador",
        headers=encabezado(token),
        json={
            "razon_social": "Cabañas de Ana",
            "cuit": "27-30123456-4",
            "condicion_iva": "Monotributo",
        },
    )
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["es_prestador"] is True
    assert cuerpo["es_viajero"] is True
    assert cuerpo["prestador"]["razon_social"] == "Cabañas de Ana"
    # Guarda el CUIT sin guiones.
    assert cuerpo["prestador"]["cuit"] == "27301234564"


def test_sin_cuenta_de_cobro_no_puede_publicar(cliente):
    """docs/01 §5 R1: datos fiscales no alcanzan, hace falta la cuenta de cobro."""
    token = registrar(cliente)
    cliente.post(
        "/api/v1/auth/prestador",
        headers=encabezado(token),
        json={
            "razon_social": "Cabañas de Ana",
            "cuit": "27301234564",
            "condicion_iva": "Monotributo",
        },
    )
    r = cliente.get("/api/v1/auth/prestador", headers=encabezado(token))
    assert r.json()["puede_publicar"] is False
    assert r.json()["cuenta_cobro_vinculada"] is False


def test_con_cuenta_de_cobro_si_puede_publicar(cliente, db):
    token = registrar(cliente)
    cliente.post(
        "/api/v1/auth/prestador",
        headers=encabezado(token),
        json={
            "razon_social": "Cabañas de Ana",
            "cuit": "27301234564",
            "condicion_iva": "Monotributo",
        },
    )
    prestador = db.query(Prestador).filter(Prestador.cuit == "27301234564").one()
    prestador.mp_user_id = "MP-123"
    db.commit()
    r = cliente.get("/api/v1/auth/prestador", headers=encabezado(token))
    assert r.json()["puede_publicar"] is True


def test_cuit_invalido(cliente):
    token = registrar(cliente)
    r = cliente.post(
        "/api/v1/auth/prestador",
        headers=encabezado(token),
        json={"razon_social": "X S.A.", "cuit": "no-es-cuit", "condicion_iva": "RI"},
    )
    assert r.status_code in (422,)


def test_no_se_puede_ser_prestador_dos_veces(cliente):
    token = registrar(cliente)
    datos = {
        "razon_social": "Cabañas de Ana",
        "cuit": "27301234564",
        "condicion_iva": "Monotributo",
    }
    primera = cliente.post("/api/v1/auth/prestador", headers=encabezado(token), json=datos)
    segunda = cliente.post("/api/v1/auth/prestador", headers=encabezado(token), json=datos)
    assert primera.status_code == 201
    assert segunda.status_code == 409


def test_sin_aceptar_los_terminos_no_se_crea_la_cuenta(cliente):
    """docs/01 §5 R11: se aceptan al registrarse."""
    r = cliente.post("/api/v1/auth/registro", json={**REGISTRO, "acepta_terminos": False})
    assert r.status_code == 422
    assert "términos" in r.json()["detail"]


def test_la_cuenta_guarda_cuando_se_aceptaron(cliente, db):
    registrar(cliente)
    usuario = db.query(Usuario).filter(Usuario.email == "ana@ejemplo.com.ar").one()
    assert usuario.acepto_terminos_en is not None
    assert usuario.version_terminos


# --- Envío del correo de verificación ---


@pytest.fixture
def smtp_falso(monkeypatch):
    """SMTP configurado, con el envío capturado en vez de salir a la red."""
    from app.core.config import get_settings
    from app.services.notificaciones import correo

    s = get_settings()
    monkeypatch.setattr(s, "environment", "production")
    monkeypatch.setattr(s, "smtp_host", "smtp.ejemplo.com")
    monkeypatch.setattr(s, "smtp_desde", "Alojate Aquí <hola@ejemplo.com>")
    monkeypatch.setattr(s, "url_publica_web", "https://alojateaqui.com.ar")
    enviados = []
    monkeypatch.setattr(correo.CorreoSMTP, "enviar", lambda self, m: enviados.append(m))
    return enviados


def test_al_registrarse_se_manda_el_enlace_de_verificacion(cliente, smtp_falso):
    registrar(cliente)
    assert len(smtp_falso) == 1
    mensaje = smtp_falso[0]
    assert mensaje.destino == "ana@ejemplo.com.ar"
    assert "https://alojateaqui.com.ar/verificar-email?token=" in mensaje.cuerpo


def _pasar_la_espera(db):
    """Corre hacia atrás los envíos registrados, como si hubiera pasado el rato."""
    from datetime import timedelta

    from app.models import Notificacion

    for n in db.query(Notificacion).filter(Notificacion.evento == "verificacion_email"):
        n.creado_en = n.creado_en - timedelta(minutes=5)
    db.commit()


def test_pedir_verificacion_manda_el_correo_y_no_devuelve_el_enlace(cliente, db, smtp_falso):
    token = registrar(cliente)
    _pasar_la_espera(db)
    r = cliente.post("/api/v1/auth/verificacion", headers=encabezado(token))
    cuerpo = r.json()
    assert cuerpo["enviado"] is True
    assert cuerpo["enlace"] is None
    assert len(smtp_falso) == 2

    # Y el enlace del correo verifica de verdad.
    enlace = smtp_falso[-1].cuerpo.split("token=")[1].split()[0]
    r = cliente.post("/api/v1/auth/verificacion/confirmar", json={"token": enlace})
    assert r.status_code == 200
    assert r.json()["email_verificado"] is True


def test_si_el_correo_no_sale_la_cuenta_igual_se_crea(cliente, db, monkeypatch, smtp_falso):
    from app.services.notificaciones import correo
    from app.services.notificaciones.base import ErrorDeEnvio

    def falla(self, m):
        raise ErrorDeEnvio("caído")

    monkeypatch.setattr(correo.CorreoSMTP, "enviar", falla)
    token = registrar(cliente)
    _pasar_la_espera(db)
    r = cliente.post("/api/v1/auth/verificacion", headers=encabezado(token))
    assert r.json()["enviado"] is False
    assert "No pudimos" in r.json()["detalle"]


def test_no_se_puede_pedir_el_correo_en_bucle(cliente, smtp_falso):
    token = registrar(cliente)  # el registro ya mandó uno
    for _ in range(3):
        r = cliente.post("/api/v1/auth/verificacion", headers=encabezado(token))
        assert r.json()["enviado"] is False
        assert "Esperá" in r.json()["detalle"]
    assert len(smtp_falso) == 1


def test_el_registro_del_envio_no_guarda_el_enlace(cliente, db, smtp_falso):
    from app.models import Notificacion

    registrar(cliente)
    n = db.query(Notificacion).filter(Notificacion.evento == "verificacion_email").one()
    assert n.estado.value == "enviada"
    assert "token=" not in n.cuerpo
