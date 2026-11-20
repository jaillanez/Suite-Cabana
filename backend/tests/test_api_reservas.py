"""El circuito de reserva y pago por la API, de punta a punta (docs/01 §7).

Se usa la pasarela simulada: sin credenciales de ninguna billetera se puede
recorrer reservar → pagar → notificación → confirmada, que es donde viven las
reglas que importan.
"""

import json

import pytest
from sqlalchemy import select

from app.models import NotificacionPago, Usuario
from app.services.pagos import Simulada
from tests.conftest import LLEGADA, SALIDA

FECHAS = {"desde": LLEGADA.isoformat(), "hasta": SALIDA.isoformat()}


@pytest.fixture
def viajero(cliente, db):
    """Cuenta de viajero con el correo ya verificado."""
    r = cliente.post(
        "/api/v1/auth/registro",
        json={
            "email": "viajera@ejemplo.com.ar",
            "password": "unaclavelarga",
            "nombre": "Ana",
            "apellido": "Pérez", "acepta_terminos": True,
        },
    )
    token = r.json()["token"]
    usuario = db.scalar(select(Usuario).where(Usuario.email == "viajera@ejemplo.com.ar"))
    usuario.email_verificado = True
    db.commit()
    return {"Authorization": f"Bearer {token}"}


def notificar(cliente, pago: str, reserva: str, estado: str = "aprobado", total: str = "0"):
    """Manda la notificación como lo haría la pantalla de pago simulado."""
    cuerpo = json.dumps(
        {"pago": pago, "reserva": reserva, "estado": estado, "total": total}
    ).encode()
    firma = Simulada().firmar(cuerpo)
    return cliente.post(
        "/api/v1/webhooks/simulada",
        content=cuerpo,
        headers={"x-firma-simulada": firma, "content-type": "application/json"},
    )


def reservar(cliente, viajero, oferta, **kw):
    datos = {
        "unidad_id": str(oferta["u_cara"].id),
        **FECHAS,
        "adultos": 2,
        "acepta_terminos": True,
    }
    datos.update(kw)
    return cliente.post("/api/v1/reservas", headers=viajero, json=datos)


# --- Pasarelas ---


def test_las_pasarelas_dicen_cual_se_puede_usar_y_por_que_no(cliente):
    r = cliente.get("/api/v1/pasarelas")
    assert r.status_code == 200
    por_codigo = {p["codigo"]: p for p in r.json()}
    assert por_codigo["simulada"]["disponible"] is True
    assert por_codigo["mercadopago"]["disponible"] is False
    assert "MP_ACCESS_TOKEN" in por_codigo["mercadopago"]["motivo"]
    # Las previstas figuran, con el motivo a la vista.
    assert "modo" in por_codigo
    assert "adaptador" in por_codigo["modo"]["motivo"]


# --- Reservar ---


def test_sin_sesion_no_se_reserva(cliente, oferta):
    r = cliente.post(
        "/api/v1/reservas",
        json={"unidad_id": str(oferta["u_cara"].id), **FECHAS, "acepta_terminos": True},
    )
    assert r.status_code == 401


def test_sin_correo_verificado_no_se_reserva(cliente, db, oferta):
    r = cliente.post(
        "/api/v1/auth/registro",
        json={"email": "nueva@ejemplo.com.ar", "password": "unaclavelarga",
              "nombre": "N", "apellido": "N", "acepta_terminos": True},
    )
    cabecera = {"Authorization": f"Bearer {r.json()['token']}"}
    respuesta = cliente.post(
        "/api/v1/reservas", headers=cabecera,
        json={"unidad_id": str(oferta["u_cara"].id), **FECHAS, "acepta_terminos": True},
    )
    assert respuesta.status_code == 403
    assert "erific" in respuesta.json()["detail"]


def test_reservar_devuelve_el_desglose_completo(cliente, viajero, oferta):
    r = reservar(cliente, viajero, oferta)
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == "pendiente_pago"
    assert cuerpo["vence_pago_en"] is not None
    item = cuerpo["items"][0]
    assert item["noches"] == 3
    assert item["comision"] is not None  # snapshot guardado
    assert item["desglose"]["subtotal"] == item["subtotal"]


def test_las_mismas_fechas_dos_veces_dan_conflicto(cliente, db, viajero, oferta):
    assert reservar(cliente, viajero, oferta).status_code == 201
    r = reservar(cliente, viajero, oferta)
    assert r.status_code == 409
    assert "disponibles" in r.json()["detail"]


def test_la_unidad_reservada_sale_de_la_busqueda(cliente, viajero, oferta):
    reservar(cliente, viajero, oferta)
    r = cliente.get(
        "/api/v1/publicaciones/buscar",
        params={"localidad": "bariloche", **{"desde": FECHAS["desde"], "hasta": FECHAS["hasta"]},
                "personas": 6},
    )
    assert all(x["unidad"]["id"] != str(oferta["u_cara"].id) for x in r.json()["resultados"])


# --- Pagar ---


def test_pagar_devuelve_a_donde_ir(cliente, viajero, oferta):
    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    r = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["pasarela"] == "simulada"
    assert codigo in cuerpo["url_pago"]


def test_una_pasarela_sin_credenciales_lo_dice(cliente, viajero, oferta):
    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    r = cliente.post(
        f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={"pasarela": "mercadopago"}
    )
    assert r.status_code == 501
    assert "MP_ACCESS_TOKEN" in r.json()["detail"]


def test_una_billetera_prevista_pero_sin_adaptador_lo_dice(cliente, viajero, oferta):
    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    r = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={"pasarela": "modo"})
    assert r.status_code == 501
    assert "adaptador" in r.json()["detail"]


# --- Notificación ---


def test_el_circuito_completo_confirma_la_reserva(cliente, db, viajero, oferta):
    reserva = reservar(cliente, viajero, oferta).json()
    codigo = reserva["codigo"]
    pago = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={}).json()

    r = notificar(cliente, pago["id_externo"], codigo, total=reserva["total"])
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "procesada"

    ficha = cliente.get(f"/api/v1/reservas/{codigo}", headers=viajero).json()
    assert ficha["estado"] == "confirmada"
    assert any(p["estado"] == "aprobado" for p in ficha["pagos"])


def test_la_misma_notificacion_dos_veces_se_procesa_una(cliente, db, viajero, oferta):
    """docs/01 §5 R6: sin duplicados."""
    reserva = reservar(cliente, viajero, oferta).json()
    codigo = reserva["codigo"]
    pago = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={}).json()

    primera = notificar(cliente, pago["id_externo"], codigo, total=reserva["total"])
    segunda = notificar(cliente, pago["id_externo"], codigo, total=reserva["total"])
    assert primera.json()["estado"] == "procesada"
    assert segunda.json()["estado"] == "ya procesada"

    registros = db.scalars(
        select(NotificacionPago).where(NotificacionPago.id_externo == pago["id_externo"])
    ).all()
    assert len(registros) == 1
    ficha = cliente.get(f"/api/v1/reservas/{codigo}", headers=viajero).json()
    assert len(ficha["pagos"]) == 1


def test_una_notificacion_con_firma_falsa_se_rechaza(cliente, viajero, oferta):
    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    r = cliente.post(
        "/api/v1/webhooks/simulada",
        content=json.dumps({"pago": "x", "reserva": codigo, "estado": "aprobado"}).encode(),
        headers={"x-firma-simulada": "mentira", "content-type": "application/json"},
    )
    assert r.status_code == 401


def test_una_notificacion_de_una_pasarela_desconocida(cliente):
    r = cliente.post("/api/v1/webhooks/billetera-inventada", content=b"{}")
    assert r.status_code == 404


def test_el_pago_rechazado_libera_las_fechas(cliente, viajero, oferta):
    reserva = reservar(cliente, viajero, oferta).json()
    codigo = reserva["codigo"]
    pago = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={}).json()
    notificar(cliente, pago["id_externo"], codigo, estado="rechazado")

    ficha = cliente.get(f"/api/v1/reservas/{codigo}", headers=viajero).json()
    assert ficha["estado"] == "cancelada"
    # Y la unidad vuelve a estar disponible.
    r = cliente.get(
        "/api/v1/publicaciones/buscar",
        params={"localidad": "bariloche", **FECHAS, "personas": 6},
    )
    assert any(x["unidad"]["id"] == str(oferta["u_cara"].id) for x in r.json()["resultados"])


# --- Cancelación ---


def test_cancelar_dice_cuanto_se_devuelve(cliente, db, viajero, oferta):
    from app.models import PoliticaCancelacion

    politica = PoliticaCancelacion(
        codigo="prueba", nombre="De prueba",
        tramos=[{"dias_antes": 7, "porcentaje_reintegro": 100}],
    )
    db.add(politica)
    db.flush()
    oferta["cara"].politica_cancelacion_id = politica.id
    db.commit()

    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    ficha = cliente.get(f"/api/v1/reservas/{codigo}", headers=viajero).json()
    assert ficha["reintegro_si_cancela"]["porcentaje"] == 100

    r = cliente.post(
        f"/api/v1/reservas/{codigo}/cancelar", headers=viajero, json={"motivo": "Cambio de planes"}
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "cancelada"


def test_la_reserva_de_otro_no_se_ve_ni_se_cancela(cliente, db, viajero, oferta):
    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    r = cliente.post(
        "/api/v1/auth/registro",
        json={"email": "intruso@ejemplo.com.ar", "password": "unaclavelarga",
              "nombre": "I", "apellido": "I", "acepta_terminos": True},
    )
    intruso = {"Authorization": f"Bearer {r.json()['token']}"}
    assert cliente.get(f"/api/v1/reservas/{codigo}", headers=intruso).status_code == 404
    assert cliente.post(
        f"/api/v1/reservas/{codigo}/cancelar", headers=intruso, json={}
    ).status_code == 404


# --- Términos (docs/01 §5 R11) ---


def test_sin_aceptar_los_terminos_no_se_reserva(cliente, viajero, oferta):
    r = cliente.post(
        "/api/v1/reservas",
        headers=viajero,
        json={"unidad_id": str(oferta["u_cara"].id), **FECHAS, "adultos": 2},
    )
    assert r.status_code == 422
    assert "términos" in r.json()["detail"]


def test_la_reserva_guarda_cuando_se_aceptaron(cliente, db, viajero, oferta):
    from app.models import Reserva

    codigo = reservar(cliente, viajero, oferta).json()["codigo"]
    reserva = db.scalar(select(Reserva).where(Reserva.codigo == codigo))
    assert reserva.acepto_terminos_en is not None
    assert reserva.version_terminos
