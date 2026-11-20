"""Paneles de viajero, prestador y operador (docs/01 §5 R10)."""

import pytest
from sqlalchemy import select

from app.models import Prestador, Usuario
from tests.conftest import LLEGADA, SALIDA

FECHAS = {"desde": LLEGADA.isoformat(), "hasta": SALIDA.isoformat()}


def cuenta(cliente, db, email, *, operador=False, verificado=True):
    r = cliente.post(
        "/api/v1/auth/registro",
        json={
            "email": email,
            "password": "unaclavelarga",
            "nombre": "N",
            "apellido": "A",
            "acepta_terminos": True,
        },
    )
    token = r.json()["token"]
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    usuario.email_verificado = verificado
    usuario.es_operador = operador
    db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viajero(cliente, db):
    return cuenta(cliente, db, "viajera@ejemplo.com.ar")


@pytest.fixture
def jefe(cliente, db):
    return cuenta(cliente, db, "operador@ejemplo.com.ar", operador=True)


def reservar(cliente, viajero, oferta):
    return cliente.post(
        "/api/v1/reservas",
        headers=viajero,
        json={
            "unidad_id": str(oferta["u_cara"].id),
            **FECHAS,
            "adultos": 2,
            "acepta_terminos": True,
        },
    )


# --- Favoritos ---


def test_guardar_y_sacar_un_favorito(cliente, viajero, oferta):
    pid = str(oferta["cara"].id)
    assert cliente.get("/api/v1/favoritos", headers=viajero).json() == []

    assert cliente.put(f"/api/v1/favoritos/{pid}", headers=viajero).status_code == 204
    guardados = cliente.get("/api/v1/favoritos", headers=viajero).json()
    assert [f["titulo"] for f in guardados] == ["Complejo Caro"]

    assert cliente.delete(f"/api/v1/favoritos/{pid}", headers=viajero).status_code == 204
    assert cliente.get("/api/v1/favoritos", headers=viajero).json() == []


def test_guardar_dos_veces_no_duplica(cliente, viajero, oferta):
    pid = str(oferta["cara"].id)
    cliente.put(f"/api/v1/favoritos/{pid}", headers=viajero)
    cliente.put(f"/api/v1/favoritos/{pid}", headers=viajero)
    assert len(cliente.get("/api/v1/favoritos", headers=viajero).json()) == 1


def test_los_favoritos_son_de_cada_uno(cliente, db, viajero, oferta):
    cliente.put(f"/api/v1/favoritos/{oferta['cara'].id}", headers=viajero)
    otro = cuenta(cliente, db, "otra@ejemplo.com.ar")
    assert cliente.get("/api/v1/favoritos", headers=otro).json() == []


def test_sin_sesion_no_hay_favoritos(cliente, oferta):
    assert cliente.get("/api/v1/favoritos").status_code == 401


# --- Cobros del prestador ---


def test_los_cobros_muestran_cuanto_le_queda(cliente, db, viajero, oferta):
    reserva = reservar(cliente, viajero, oferta).json()
    codigo = reserva["codigo"]
    pago = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={}).json()
    from tests.test_api_reservas import notificar

    notificar(cliente, pago["id_externo"], codigo, total=reserva["total"])

    # El prestador de la oferta necesita una cuenta para entrar.
    prestador = db.scalar(select(Prestador).where(Prestador.id == oferta["prestador"].id))
    dueno = db.get(Usuario, prestador.usuario_id)
    dueno.hash_password = None
    db.commit()

    from app.core.security import crear_token

    cabecera = {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}
    r = cliente.get("/api/v1/mis-cobros", headers=cabecera)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["reservas"] == 1
    linea = cuerpo["lineas"][0]
    assert linea["codigo"] == codigo
    assert linea["pagado"] is True
    # Lo que le queda es su precio menos lo que absorbe de comisión.
    assert float(linea["te_queda"]) == float(linea["tu_precio"]) - float(
        cuerpo["comision"]
    )


def test_un_viajero_no_ve_los_cobros(cliente, viajero):
    assert cliente.get("/api/v1/mis-cobros", headers=viajero).status_code == 403


# --- Operador ---


def test_el_operador_ve_todas_las_reservas(cliente, db, viajero, jefe, oferta):
    reserva = reservar(cliente, viajero, oferta).json()
    r = cliente.get("/api/v1/admin/reservas", headers=jefe)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["reservas"] == 1
    assert cuerpo["lineas"][0]["codigo"] == reserva["codigo"]
    assert cuerpo["lineas"][0]["pagado"] is False


def test_el_operador_filtra_por_estado(cliente, viajero, jefe, oferta):
    reservar(cliente, viajero, oferta)
    con = cliente.get("/api/v1/admin/reservas?estado=confirmada", headers=jefe).json()
    sin = cliente.get("/api/v1/admin/reservas?estado=pendiente_pago", headers=jefe).json()
    assert con["reservas"] == 0
    assert sin["reservas"] == 1


def test_la_exportacion_sale_en_csv(cliente, viajero, jefe, oferta):
    reserva = reservar(cliente, viajero, oferta).json()
    r = cliente.get("/api/v1/admin/reservas.csv", headers=jefe)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    texto = r.text
    assert texto.startswith("﻿")  # BOM para que Excel lea los acentos
    assert "codigo;estado;creada" in texto
    assert reserva["codigo"] in texto


def test_el_resumen_de_comisiones_suma_los_snapshots(cliente, db, viajero, jefe, oferta):
    reserva = reservar(cliente, viajero, oferta).json()
    codigo = reserva["codigo"]
    pago = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={}).json()
    from tests.test_api_reservas import notificar

    notificar(cliente, pago["id_externo"], codigo, total=reserva["total"])

    r = cliente.get("/api/v1/admin/comisiones", headers=jefe).json()
    assert r["reservas"] == 1
    assert float(r["comision_total"]) == float(r["comision_neta"]) + float(r["iva"])
    assert float(r["comision_total"]) == float(r["la_paga_el_viajero"]) + float(
        r["la_absorbe_el_prestador"]
    )


def test_un_viajero_no_entra_al_panel_del_operador(cliente, viajero):
    assert cliente.get("/api/v1/admin/reservas", headers=viajero).status_code == 403
    assert cliente.get("/api/v1/admin/comisiones", headers=viajero).status_code == 403
    assert cliente.get("/api/v1/admin/reservas.csv", headers=viajero).status_code == 403


def test_sin_pagos_aprobados_no_hay_comision_contada(cliente, viajero, jefe, oferta):
    reservar(cliente, viajero, oferta)
    r = cliente.get("/api/v1/admin/comisiones", headers=jefe).json()
    assert r["reservas"] == 0  # todavía no está confirmada


def test_lo_que_espera_al_prestador_igual_cuenta_como_cobrado(cliente, db, viajero, jefe, oferta):
    """El viajero ya pagó: esa plata está capturada aunque falte la respuesta."""
    oferta["cara"].confirmacion_inmediata = False
    db.commit()

    reserva = reservar(cliente, viajero, oferta).json()
    codigo = reserva["codigo"]
    pago = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={}).json()
    from tests.test_api_reservas import notificar

    notificar(cliente, pago["id_externo"], codigo, total=reserva["total"])

    ficha = cliente.get(f"/api/v1/reservas/{codigo}", headers=viajero).json()
    assert ficha["estado"] == "pendiente_aprobacion"

    comisiones = cliente.get("/api/v1/admin/comisiones", headers=jefe).json()
    assert comisiones["reservas"] == 1


def test_una_reserva_rechazada_sale_de_los_totales(cliente, db, viajero, jefe, oferta):
    from app.core.security import crear_token

    oferta["cara"].confirmacion_inmediata = False
    db.commit()
    reserva = reservar(cliente, viajero, oferta).json()
    codigo = reserva["codigo"]
    pago = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero, json={}).json()
    from tests.test_api_reservas import notificar

    notificar(cliente, pago["id_externo"], codigo, total=reserva["total"])
    assert cliente.get("/api/v1/admin/comisiones", headers=jefe).json()["reservas"] == 1

    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    prestador = {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}
    cliente.post(
        f"/api/v1/mis-reservas/{codigo}/rechazar",
        headers=prestador,
        json={"motivo": "Tengo la casa en refacción"},
    )
    assert cliente.get("/api/v1/admin/comisiones", headers=jefe).json()["reservas"] == 0
