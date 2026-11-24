"""Excursiones, etapa 2 (docs/05): precio por tipo de pasajero, reserva con
retención de lugares, y lo que decide cada prestador —política, mínimo de
personas, reintegro si la salida no va—, nunca la plataforma."""

import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import CupoTomado, PoliticaCancelacion, PrecioPasajero, SalidaExcursion, Usuario
from app.models.enums import EstadoReserva, OrigenBloqueo
from app.services import politicas, reservas, salidas
from app.services import precios_excursion as px
from app.services import reservas_excursion as rx
from app.services.pagos.base import EstadoPago
from tests.test_api_reservas import viajero as viajero_api  # noqa: F401  (fixture)
from tests.test_excursiones import MARTES, _proximo, excursion  # noqa: F401  (fixture)


@pytest.fixture
def precios(db, excursion) -> dict:  # noqa: F811
    u = excursion["unidad"]
    adulto = PrecioPasajero(unidad_id=u.id, nombre="Adulto", precio=Decimal(30000), orden=0)
    menor = PrecioPasajero(
        unidad_id=u.id, nombre="Menor", descripcion="De 3 a 12 años", edad_desde=3,
        edad_hasta=12, precio=Decimal(15000), orden=1,
    )
    bebe = PrecioPasajero(
        unidad_id=u.id, nombre="Bebé en brazos", edad_hasta=2, precio=Decimal(0),
        ocupa_lugar=False, orden=2,
    )
    db.add_all([adulto, menor, bebe])
    db.flush()
    return {"adulto": adulto, "menor": menor, "bebe": bebe, **excursion}


@pytest.fixture
def viajero(db) -> Usuario:
    u = Usuario(
        email="viajera@ejemplo.com.ar", nombre="Ana", apellido="Pérez",
        email_verificado=True, telefono="+5492644123456",
    )
    db.add(u)
    db.flush()
    return u


def _reservar(db, viajero, precios, adultos=2, menores=0, bebes=0, fecha=None):
    pedido = {precios["adulto"].id: adultos, precios["menor"].id: menores,
              precios["bebe"].id: bebes}
    return rx.crear_excursion(
        db, viajero, precios["unidad"], fecha or _proximo(MARTES), pedido,
        turno_id=precios["turno"].id,
    )


def _salida(db, precios, fecha=None) -> SalidaExcursion:
    return db.scalar(
        select(SalidaExcursion).where(
            SalidaExcursion.turno_id == precios["turno"].id,
            SalidaExcursion.fecha == (fecha or _proximo(MARTES)),
        ).execution_options(populate_existing=True)
    )


def _pagar(db, reserva, id_pago="pago-1"):
    return reservas.registrar_pago(db, reserva, id_pago, "simulada", EstadoPago.APROBADO)


# --- Precio por tipo de pasajero (cuenta pura) ---


def _cats():
    a, m, b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    return [
        px.Categoria(a, "Adulto", Decimal(30000)),
        px.Categoria(m, "Menor", Decimal(15000)),
        px.Categoria(b, "Bebé", Decimal(0), ocupa_lugar=False),
    ], (a, m, b)


def test_el_precio_suma_cada_tipo_de_pasajero_en_el_orden_del_prestador():
    cats, (a, m, b) = _cats()
    p = px.calcular(cats, {b: 1, m: 2, a: 2}, maximo_por_reserva=8)
    assert [(ln.concepto, ln.cantidad, ln.monto) for ln in p.lineas] == [
        ("Adulto", 2, Decimal(60000)), ("Menor", 2, Decimal(30000)), ("Bebé", 1, Decimal(0)),
    ]
    assert (p.subtotal, p.personas, p.lugares) == (Decimal(90000), 5, 4)


@pytest.mark.parametrize(
    ("pedido", "mensaje"),
    [
        ({"otro": 1}, "no existe"),
        ({"b": 2}, "al menos una persona que ocupe lugar"),
        ({"a": 9}, "hasta 8 personas"),
        ({"a": -1}, "negativa"),
        ({}, "al menos una persona"),
    ],
)
def test_un_pedido_que_no_se_puede_cotizar_se_rechaza(pedido, mensaje):
    cats, (a, m, b) = _cats()
    ids = {"a": a, "m": m, "b": b, "otro": uuid.uuid4()}
    with pytest.raises(px.PrecioInvalido, match=mensaje):
        px.calcular(cats, {ids[k]: v for k, v in pedido.items()}, maximo_por_reserva=8)


def test_sin_precios_cargados_no_se_cotiza():
    with pytest.raises(px.PrecioInvalido, match="todavía no tiene precios"):
        px.calcular([], {uuid.uuid4(): 1}, maximo_por_reserva=8)


# --- Política: la elige cada prestador ---


def test_los_tramos_propios_se_normalizan():
    assert politicas.validar_tramos(
        [{"dias_antes": "1", "porcentaje_reintegro": 50},
         {"dias_antes": 7, "porcentaje_reintegro": "100"}]
    ) == [{"dias_antes": 7, "porcentaje_reintegro": 100},
          {"dias_antes": 1, "porcentaje_reintegro": 50}]


@pytest.mark.parametrize(
    ("tramos", "mensaje"),
    [
        ([], "al menos un tramo"),
        ([{"dias_antes": 1}], "días de anticipación y porcentaje"),
        ([{"dias_antes": 1, "porcentaje_reintegro": 101}], "de 0 a 100"),
        ([{"dias_antes": 400, "porcentaje_reintegro": 10}], "de 0 a 365"),
        ([{"dias_antes": 2, "porcentaje_reintegro": 10},
          {"dias_antes": 2, "porcentaje_reintegro": 50}], "mismos días"),
        ([{"dias_antes": n, "porcentaje_reintegro": 10} for n in range(6)], "Hasta 5"),
    ],
)
def test_tramos_mal_cargados_se_rechazan(tramos, mensaje):
    with pytest.raises(politicas.TramosInvalidos, match=mensaje):
        politicas.validar_tramos(tramos)


def test_los_tramos_del_prestador_mandan_sobre_la_plantilla(db, precios):
    pub = precios["publicacion"]
    plantilla = PoliticaCancelacion(
        codigo="flexible", nombre="Flexible", descripcion="Texto de la plantilla",
        tramos=[{"dias_antes": 1, "porcentaje_reintegro": 100}],
    )
    db.add(plantilla)
    db.flush()
    pub.politica_cancelacion = plantilla
    pub.reintegro_si_no_sale = 90
    assert politicas.vigente(pub)["codigo"] == "flexible"

    pub.tramos_cancelacion = [{"dias_antes": 3, "porcentaje_reintegro": 70}]
    assert politicas.snapshot(pub) == {
        "codigo": "propia", "nombre": "Propia del prestador",
        "tramos": [{"dias_antes": 3, "porcentaje_reintegro": 70}],
        "reintegro_si_no_sale": 90,
    }


def test_un_alojamiento_no_lleva_reintegro_si_no_sale(db, oferta):
    assert "reintegro_si_no_sale" not in (politicas.vigente(oferta["cara"]) or {})


# --- Reservar ---


def test_reservar_retiene_los_lugares_de_quienes_ocupan(db, viajero, precios):
    reserva = _reservar(db, viajero, precios, adultos=2, menores=1, bebes=1)
    item = reserva.items[0]
    assert reserva.estado is EstadoReserva.PENDIENTE_PAGO
    assert item.subtotal == Decimal(75000)
    assert item.adultos == 4  # todos los que van
    assert item.inicio_en.hour == 9
    assert item.desglose["lugares"] == 3
    assert reserva.total == item.subtotal + item.comision.cargo_viajero

    salida = _salida(db, precios)
    assert salida.ocupados == 3  # el bebé no ocupa cupo
    tomado = db.scalar(select(CupoTomado).where(CupoTomado.item_reserva_id == item.id))
    assert (tomado.origen, tomado.vence_en) == (OrigenBloqueo.RETENCION, reserva.vence_pago_en)
    assert item.politica_cancelacion["reintegro_si_no_sale"] == 100


def test_no_se_reservan_mas_lugares_que_los_libres(db, viajero, precios):
    _reservar(db, viajero, precios, adultos=8)
    with pytest.raises(reservas.NoSePuedeReservar, match="^Quedan 2 lugares en esta salida$"):
        _reservar(db, viajero, precios, adultos=3)


def test_no_se_reserva_una_salida_que_no_existe(db, viajero, precios):
    with pytest.raises(reservas.NoSePuedeReservar, match="no está disponible"):
        _reservar(db, viajero, precios, fecha=_proximo(MARTES) + timedelta(days=1))


def test_el_pago_confirma_y_los_lugares_quedan_firmes(db, viajero, precios):
    reserva = _reservar(db, viajero, precios)
    _pagar(db, reserva)
    assert reserva.estado is EstadoReserva.CONFIRMADA
    tomado = db.scalar(select(CupoTomado).where(CupoTomado.item_reserva_id == reserva.items[0].id))
    assert (tomado.origen, tomado.vence_en) == (OrigenBloqueo.RESERVA, None)


def test_un_pago_tardio_vuelve_a_pedir_los_lugares_si_hay(db, viajero, precios):
    reserva = _reservar(db, viajero, precios, adultos=3)
    salidas.soltar_vencidos(db, datetime.now(UTC) + timedelta(hours=2))
    assert _salida(db, precios).ocupados == 0

    _pagar(db, reserva)
    assert reserva.estado is EstadoReserva.CONFIRMADA
    assert _salida(db, precios).ocupados == 3


def test_un_pago_tardio_sin_lugar_no_confirma(db, viajero, precios):
    reserva = _reservar(db, viajero, precios, adultos=3)
    salidas.soltar_vencidos(db, datetime.now(UTC) + timedelta(hours=2))
    salidas.tomar(db, _salida(db, precios), 8, OrigenBloqueo.EXTERNA)  # otro se los llevó

    _pagar(db, reserva)
    assert reserva.estado is EstadoReserva.CANCELADA
    assert reserva.pagos[0].estado == reservas.ESTADO_SIN_LUGAR
    assert _salida(db, precios).ocupados == 8


def test_cancelar_devuelve_los_lugares_y_aplica_los_tramos_propios(db, viajero, precios):
    precios["publicacion"].tramos_cancelacion = [{"dias_antes": 2, "porcentaje_reintegro": 80}]
    reserva = _reservar(db, viajero, precios, adultos=4)
    _pagar(db, reserva)

    reintegro = reservas.cancelar(db, reserva, "No puedo ir")
    assert reintegro.porcentaje == 80
    assert reintegro.monto == (reserva.total * Decimal("0.8")).quantize(Decimal("0.01"))
    assert _salida(db, precios).ocupados == 0


def test_una_reserva_sin_pagar_a_tiempo_suelta_los_lugares(db, viajero, precios):
    reserva = _reservar(db, viajero, precios, adultos=4)
    assert reservas.liberar_vencidas(db, datetime.now(UTC) + timedelta(hours=2)) == 1
    assert reserva.estado is EstadoReserva.CANCELADA
    assert _salida(db, precios).ocupados == 0


# --- Si la salida no va ---


def test_si_el_prestador_suspende_se_devuelve_lo_que_el_eligio(db, viajero, precios):
    precios["publicacion"].reintegro_si_no_sale = 80
    pagada = _reservar(db, viajero, precios, adultos=2)
    _pagar(db, pagada)
    sin_pagar = _reservar(db, viajero, precios, adultos=1)
    salida = _salida(db, precios)
    salidas.tomar(db, salida, 2, OrigenBloqueo.EXTERNA, nota="Vendidos por teléfono")

    resultado = dict(
        (r.codigo, ri) for r, ri in rx.no_sale(db, salida, "Pronóstico de tormenta")
    )
    assert resultado[pagada.codigo].porcentaje == 80
    assert resultado[pagada.codigo].monto == (pagada.total * Decimal("0.8")).quantize(
        Decimal("0.01")
    )
    assert resultado[sin_pagar.codigo].monto == 0  # no entró plata
    assert pagada.estado is sin_pagar.estado is EstadoReserva.CANCELADA
    assert pagada.motivo_cancelacion == (
        "Pronóstico de tormenta. Corresponde devolver el 80 % de lo pagado"
    )
    salida = _salida(db, precios)
    assert (salida.suspendida, salida.ocupados) == (True, 0)


def test_cambiar_el_reintegro_despues_no_cambia_lo_reservado(db, viajero, precios):
    reserva = _reservar(db, viajero, precios)
    _pagar(db, reserva)
    precios["publicacion"].reintegro_si_no_sale = 0
    ((_, reintegro),) = rx.no_sale(db, _salida(db, precios), "Sin guía")
    assert reintegro.porcentaje == 100


# --- Mínimo de personas: lo decide cada prestador ---


def _con_minimo(precios, minimo=4, aviso=24):
    precios["turno"].minimo_personas = minimo
    precios["turno"].aviso_minimo_horas = aviso


def _hora_de_decidir(precios, fecha=None):
    f = fecha or _proximo(MARTES)
    inicio = datetime.combine(f, time(9), tzinfo=salidas.ZONA)
    return inicio - timedelta(hours=precios["turno"].aviso_minimo_horas)


def test_la_salida_copia_el_minimo_del_turno(db, viajero, precios):
    _con_minimo(precios, minimo=4, aviso=48)
    _reservar(db, viajero, precios)
    precios["turno"].minimo_personas = 2
    salida = _salida(db, precios)
    assert (salida.minimo_personas, salida.aviso_minimo_horas) == (4, 48)


def test_sin_llegar_al_minimo_la_salida_se_cancela_sola(db, viajero, precios):
    _con_minimo(precios, minimo=4)
    reserva = _reservar(db, viajero, precios, adultos=3)
    _pagar(db, reserva)

    antes = _hora_de_decidir(precios) - timedelta(minutes=1)
    assert rx.revisar_minimos(db, antes) == {"salidas_confirmadas": 0, "salidas_canceladas": 0}
    assert rx.revisar_minimos(db, _hora_de_decidir(precios)) == {
        "salidas_confirmadas": 0, "salidas_canceladas": 1,
    }
    assert reserva.estado is EstadoReserva.CANCELADA
    assert reserva.motivo_cancelacion.startswith("No se llegó al mínimo de 4 personas")
    assert _salida(db, precios).suspendida


def test_quien_esta_pagando_no_cuenta_para_el_minimo(db, viajero, precios):
    _con_minimo(precios, minimo=4)
    pagada = _reservar(db, viajero, precios, adultos=2)
    _pagar(db, pagada)
    pagando = _reservar(db, viajero, precios, adultos=2)
    rx.revisar_minimos(db, _hora_de_decidir(precios))
    assert pagada.estado is pagando.estado is EstadoReserva.CANCELADA


def test_llegando_al_minimo_la_salida_va_aunque_despues_alguien_cancele(db, viajero, precios):
    _con_minimo(precios, minimo=4)
    a = _reservar(db, viajero, precios, adultos=2)
    b = _reservar(db, viajero, precios, adultos=2)
    _pagar(db, a, "p-a")
    _pagar(db, b, "p-b")
    assert rx.revisar_minimos(db, _hora_de_decidir(precios))["salidas_confirmadas"] == 1

    reservas.cancelar(db, a, "No puedo ir")
    assert rx.revisar_minimos(db, _hora_de_decidir(precios) + timedelta(hours=1)) == {
        "salidas_confirmadas": 0, "salidas_canceladas": 0,
    }
    assert b.estado is EstadoReserva.CONFIRMADA
    assert not _salida(db, precios).suspendida


def test_pasada_la_hora_de_decidir_sin_confirmar_no_se_vende(db, viajero, precios):
    _con_minimo(precios, minimo=4)
    _reservar(db, viajero, precios, adultos=1)  # guardada, sin llegar
    martes = _proximo(MARTES)
    jueves = martes + timedelta(days=2)
    ahora = _hora_de_decidir(precios, jueves) + timedelta(minutes=1)
    # Ni la guardada (martes) ni la calculada (jueves): las dos pasaron la hora.
    assert salidas.salidas(db, precios["unidad"], martes, jueves, ahora=ahora) == []
    with pytest.raises(salidas.SalidaInvalida, match="ya no recibe reservas"):
        salidas.tomar(
            db, _salida(db, precios), 1, OrigenBloqueo.RESERVA,
            ahora=_hora_de_decidir(precios, martes) + timedelta(minutes=1),
        )


def test_sin_minimo_la_salida_se_vende_hasta_la_hora(db, viajero, precios):
    martes = _proximo(MARTES)
    ahora = datetime.combine(martes, time(8, 55), tzinfo=salidas.ZONA)
    lista = salidas.salidas(db, precios["unidad"], martes, martes, ahora=ahora)
    assert [s.fecha for s in lista] == [martes]


def test_un_minimo_mayor_que_el_cupo_se_rechaza(db, precios):
    with pytest.raises(salidas.SalidaInvalida, match="mínimo de personas"):
        salidas.crear_turno(
            db, precios["unidad"], nombre="Tarde", dias_semana=[5], hora_inicio=time(16),
            duracion_minutos=120, cupo=6, minimo_personas=7,
        )


# --- API ---


def _pedido_api(precios, **kw):
    return {
        "unidad_id": str(precios["unidad"].id),
        "fecha": _proximo(MARTES).isoformat(),
        "turno_id": str(precios["turno"].id),
        "pasajeros": [{"categoria_id": str(precios["adulto"].id), "cantidad": 2},
                      {"categoria_id": str(precios["menor"].id), "cantidad": 1}],
        **kw,
    }


def test_la_api_muestra_salidas_precios_y_politica(cliente, precios):
    r = cliente.get(
        f"/api/v1/excursiones/unidades/{precios['unidad'].id}/salidas",
        params={"desde": (_proximo(MARTES) - timedelta(days=1)).isoformat()},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert [p["nombre"] for p in d["precios"]] == ["Adulto", "Menor", "Bebé en brazos"]
    assert d["precios"][1]["descripcion"] == "De 3 a 12 años"
    assert d["salidas"][0]["fecha"] == _proximo(MARTES).isoformat()
    assert d["salidas"][0]["libres"] == 10
    assert (d["maximo_por_reserva"], d["reintegro_si_no_sale"]) == (8, 100)


def test_la_api_no_abre_un_alojamiento_como_excursion(cliente, oferta):
    r = cliente.get(
        f"/api/v1/excursiones/unidades/{oferta['u_cara'].id}/salidas",
        params={"desde": _proximo(MARTES).isoformat()},
    )
    assert r.status_code == 404


def test_la_api_cotiza_y_reserva(cliente, db, precios, viajero_api):  # noqa: F811
    r = cliente.post("/api/v1/excursiones/cotizacion", json=_pedido_api(precios))
    assert r.status_code == 200, r.text
    cot = r.json()
    assert [(ln["concepto"], ln["cantidad"]) for ln in cot["lineas"]] == [
        ("Adulto", 2), ("Menor", 1),
    ]
    assert Decimal(cot["subtotal"]) == Decimal(75000)

    sin_terminos = cliente.post(
        "/api/v1/excursiones/reservas", headers=viajero_api, json=_pedido_api(precios)
    )
    assert sin_terminos.status_code == 422

    r = cliente.post(
        "/api/v1/excursiones/reservas", headers=viajero_api,
        json={**_pedido_api(precios), "acepta_terminos": True},
    )
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["total"]) == Decimal(cot["total"])
    assert _salida(db, precios).ocupados == 3


def test_la_api_rechaza_una_salida_ambigua(cliente, precios):
    r = cliente.post(
        "/api/v1/excursiones/cotizacion", json=_pedido_api(precios, turno_id=None)
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "Elegí una salida"
