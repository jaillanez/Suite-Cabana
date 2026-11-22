"""Salones por la API, de punta a punta (docs/04, etapa 2): disponibilidad del
día, cotización, reserva con seña, choques entre turnos y horas, preparación y
cancelación con la política de eventos."""

from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Adicional, FranjaHoraria, Notificacion, PoliticaCancelacion, TarifaHoraria
from app.services import reservas
from tests.test_api_reservas import notificar, viajero  # noqa: F401  (fixture)
from tests.test_salones import salon  # noqa: F401  (fixture)

DIA = date.today() + timedelta(days=40)


@pytest.fixture
def evento(db, salon):  # noqa: F811
    u = salon["unidad"]
    u.capacidad_base = 80
    u.cargo_persona_extra = Decimal(5000)
    u.preparacion_minutos = 60
    politica = PoliticaCancelacion(
        codigo="eventos", nombre="Eventos",
        tramos=[
            {"dias_antes": 30, "porcentaje_reintegro": 90},
            {"dias_antes": 15, "porcentaje_reintegro": 50},
        ],
    )
    db.add(politica)
    db.flush()
    salon["publicacion"].politica_cancelacion_id = politica.id
    salon["publicacion"].porcentaje_sena = 30
    manana = FranjaHoraria(
        unidad_id=u.id, nombre="Mañana", hora_inicio=time(9), hora_fin=time(14),
        precio=Decimal(150000),
    )
    noche = FranjaHoraria(
        unidad_id=u.id, nombre="Noche", hora_inicio=time(21), hora_fin=time(5),
        precio=Decimal(400000),
    )
    horas = TarifaHoraria(
        unidad_id=u.id, precio_hora=Decimal(40000), horas_minimas=3,
        hora_apertura=time(10), hora_cierre=time(2),
    )
    vajilla = Adicional(unidad_id=u.id, nombre="Vajilla", precio=Decimal(800), por_persona=True)
    db.add_all([manana, noche, horas, vajilla])
    db.commit()
    return {**salon, "manana": manana, "noche": noche, "vajilla": vajilla}


def _pedido(evento, **kw):
    datos = {"unidad_id": str(evento["unidad"].id), "dia": DIA.isoformat(), "invitados": 50}
    datos.update(kw)
    return datos


def _reservar(cliente, viajero, evento, **kw):  # noqa: F811
    return cliente.post(
        "/api/v1/salones/reservas", headers=viajero,
        json={**_pedido(evento, **kw), "acepta_terminos": True},
    )


# --- Disponibilidad y cotización ---


def test_la_disponibilidad_muestra_turnos_horas_y_adicionales(cliente, evento):
    r = cliente.get(
        f"/api/v1/salones/unidades/{evento['unidad'].id}/disponibilidad",
        params={"dia": DIA.isoformat()},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert [f["nombre"] for f in d["franjas"]] == ["Mañana", "Noche"]
    assert all(f["libre"] for f in d["franjas"])
    assert d["por_horas"]["horas_minimas"] == 3
    assert d["adicionales"][0]["nombre"] == "Vajilla"
    assert d["capacidad_sentados"] == 80
    assert d["ocupado"] == []


def test_una_cabana_no_tiene_disponibilidad_de_salon(cliente, oferta):
    r = cliente.get(
        f"/api/v1/salones/unidades/{oferta['u_cara'].id}/disponibilidad",
        params={"dia": DIA.isoformat()},
    )
    assert r.status_code == 404


def test_la_cotizacion_dice_cuanto_se_sena_y_cuanto_queda(cliente, evento):
    r = cliente.post(
        "/api/v1/salones/cotizacion",
        json=_pedido(
            evento, franja_id=str(evento["noche"].id), invitados=90,
            adicionales=[str(evento["vajilla"].id)],
        ),
    )
    assert r.status_code == 200, r.text
    c = r.json()
    # 400.000 + 10 invitados extra × 5.000 + vajilla 90 × 800
    assert Decimal(c["subtotal"]) == Decimal(400000 + 50000 + 72000)
    assert Decimal(c["sena"]) == (Decimal(c["total"]) * Decimal("0.3")).quantize(Decimal("0.01"))
    assert Decimal(c["a_pagar_ahora"]) == Decimal(c["sena"])
    assert Decimal(c["saldo_con_anfitrion"]) == Decimal(c["total"]) - Decimal(c["sena"])


AYER = (date.today() - timedelta(days=1)).isoformat()
NULO = "00000000-0000-0000-0000-000000000000"


@pytest.mark.parametrize(
    ("caso", "motivo"),
    [
        ({"hora_inicio": "15:00", "horas": 2}, "mínimo"),
        ({"franja": "manana", "invitados": 500}, "hasta 120"),
        ({}, "Elegí un turno"),
        ({"franja": "manana", "adicionales": [NULO]}, "adicionales"),
        ({"franja": "manana", "dia": AYER}, "ya pasó"),
    ],
)
def test_pedidos_imposibles_se_explican(cliente, evento, caso, motivo):
    caso = dict(caso)
    if franja := caso.pop("franja", None):
        caso["franja_id"] = str(evento[franja].id)
    r = cliente.post("/api/v1/salones/cotizacion", json=_pedido(evento, **caso))
    assert r.status_code == 422, r.text
    assert motivo in r.json()["detail"]


# --- Reservar y señar ---


def test_reservar_con_sena_cobra_solo_la_sena(cliente, db, viajero, evento):  # noqa: F811
    r = _reservar(cliente, viajero, evento, franja_id=str(evento["noche"].id))
    assert r.status_code == 201, r.text
    reserva = r.json()
    item = reserva["items"][0]
    assert item["inicio_en"] and item["fin_en"]
    sena = Decimal(reserva["monto_sena"])
    assert Decimal(reserva["saldo_con_anfitrion"]) == Decimal(reserva["total"]) - sena

    pago = cliente.post(
        f"/api/v1/reservas/{reserva['codigo']}/pagar", headers=viajero, json={}
    ).json()
    assert Decimal(pago["total"]) == sena

    # Con la seña aprobada, la reserva sigue el circuito (a solicitud: el anfitrión aprueba).
    r = notificar(cliente, pago["id_externo"], reserva["codigo"], total=str(sena))
    assert r.json()["resultado"] == "pendiente_aprobacion"
    ficha = reservas.traer(db, reserva["codigo"])
    assert ficha.pagos[0].tipo.value == "sena"
    # La comisión es sobre el total del evento, no sobre la seña.
    assert ficha.items[0].comision.base == ficha.items[0].subtotal


def test_una_sena_por_menos_no_confirma(cliente, viajero, evento):  # noqa: F811
    reserva = _reservar(cliente, viajero, evento, franja_id=str(evento["noche"].id)).json()
    pago = cliente.post(
        f"/api/v1/reservas/{reserva['codigo']}/pagar", headers=viajero, json={}
    ).json()
    r = notificar(cliente, pago["id_externo"], reserva["codigo"], total="1000")
    assert r.json()["resultado"] == "pendiente_pago"


def test_el_mismo_turno_no_se_reserva_dos_veces(cliente, viajero, evento):  # noqa: F811
    assert _reservar(cliente, viajero, evento, franja_id=str(evento["noche"].id)).status_code == 201
    r = _reservar(cliente, viajero, evento, franja_id=str(evento["noche"].id))
    assert r.status_code == 409


def test_turnos_y_horas_comparten_disponibilidad(cliente, viajero, evento):  # noqa: F811
    manana = str(evento["manana"].id)
    assert _reservar(cliente, viajero, evento, franja_id=manana).status_code == 201
    # Mañana es de 9 a 14: de 13 a 16 se pisa.
    assert _reservar(cliente, viajero, evento, hora_inicio="13:00", horas=3).status_code == 409


def test_la_preparacion_separa_un_evento_del_siguiente(cliente, viajero, evento):  # noqa: F811
    manana = str(evento["manana"].id)
    assert _reservar(cliente, viajero, evento, franja_id=manana).status_code == 201
    # Termina a las 14 y hay 1 h de preparación: a las 14 no, a las 15 sí.
    assert _reservar(cliente, viajero, evento, hora_inicio="14:00", horas=3).status_code == 409
    assert _reservar(cliente, viajero, evento, hora_inicio="15:00", horas=3).status_code == 201


def test_lo_reservado_aparece_ocupado(cliente, viajero, evento):  # noqa: F811
    _reservar(cliente, viajero, evento, franja_id=str(evento["noche"].id))
    d = cliente.get(
        f"/api/v1/salones/unidades/{evento['unidad'].id}/disponibilidad",
        params={"dia": DIA.isoformat()},
    ).json()
    libres = {f["nombre"]: f["libre"] for f in d["franjas"]}
    assert libres == {"Mañana": True, "Noche": False}
    assert len(d["ocupado"]) == 1


def test_sin_aceptar_terminos_no_se_reserva(cliente, viajero, evento):  # noqa: F811
    r = cliente.post(
        "/api/v1/salones/reservas", headers=viajero,
        json=_pedido(evento, franja_id=str(evento["noche"].id)),
    )
    assert r.status_code == 422


# --- Cancelar ---


def test_cancelar_con_tiempo_devuelve_el_90_de_lo_pagado(cliente, db, viajero, evento):  # noqa: F811
    reserva = _reservar(cliente, viajero, evento, franja_id=str(evento["noche"].id)).json()
    pago = cliente.post(
        f"/api/v1/reservas/{reserva['codigo']}/pagar", headers=viajero, json={}
    ).json()
    notificar(cliente, pago["id_externo"], reserva["codigo"], total=reserva["monto_sena"])

    ficha = cliente.get(f"/api/v1/reservas/{reserva['codigo']}", headers=viajero).json()
    reintegro = ficha["reintegro_si_cancela"]
    assert reintegro["porcentaje"] == 90
    assert Decimal(reintegro["monto"]) == (
        Decimal(reserva["monto_sena"]) * Decimal("0.9")
    ).quantize(Decimal("0.01"))

    r = cliente.post(
        f"/api/v1/reservas/{reserva['codigo']}/cancelar", headers=viajero,
        json={"motivo": "Cambio de planes"},
    )
    assert r.status_code == 200
    # Y el turno vuelve a estar libre.
    d = cliente.get(
        f"/api/v1/salones/unidades/{evento['unidad'].id}/disponibilidad",
        params={"dia": DIA.isoformat()},
    ).json()
    assert all(f["libre"] for f in d["franjas"])


def test_el_aviso_habla_de_horario_e_invitados(cliente, db, viajero, evento):  # noqa: F811
    reserva = _reservar(
        cliente, viajero, evento, franja_id=str(evento["noche"].id), invitados=60
    ).json()
    aviso = db.scalars(
        select(Notificacion).where(Notificacion.evento == "reserva_creada")
    ).all()[-1]
    assert reserva["codigo"] in aviso.asunto
    assert "21:00" in aviso.cuerpo and "05:00 h" in aviso.cuerpo
