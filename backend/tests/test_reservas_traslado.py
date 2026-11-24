"""Traslados, etapa 2 (docs/06): reservar con retención, ida y vuelta como dos
ítems, los datos del viaje y quién los ve, pago, cancelación y comisión."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.security import crear_token
from app.models import (
    BloqueoHorario,
    ComisionAplicada,
    LugarTraslado,
    Reserva,
    Usuario,
)
from app.models.enums import EstadoReserva, OrigenBloqueo
from app.services import horarios, reservas
from app.services import precios_traslado as pt
from app.services import reservas_traslado as rt
from app.services.pagos.base import EstadoPago
from app.services.precios_eventos import ZONA
from tests.test_api_reservas import viajero as viajero_api  # noqa: F401  (fixture)
from tests.test_reservas_excursion import viajero  # noqa: F401  (fixture)
from tests.test_traslados import AHORA, _a_las, _punto, traslado  # noqa: F401  (fixture)

HOTEL = pt.Punto(-41.1380, -71.3050)  # a unos 12 km del aeropuerto, dentro del radio


def _pedido(t, inicio=None, **kw) -> rt.Pedido:
    datos = {
        "origen": rt.Extremo(lugar_id=t["aeropuerto"].id),
        "destino": rt.Extremo(lugar_id=t["centro"].id, direccion="Hotel Lago, Mitre 120"),
        "inicio": inicio or _a_las(14),
        "pasajeros": 3,
        "valijas": 2,
        "vuelo_ida": "AR1672",
        **kw,
    }
    return rt.Pedido(**datos)


def _reservar(db, viajero, t, **kw):  # noqa: F811
    return rt.crear_traslado(db, viajero, t["auto"], _pedido(t, **kw), ahora=AHORA)


def _bloqueos(db, t) -> list[BloqueoHorario]:
    return list(
        db.scalars(
            select(BloqueoHorario)
            .where(BloqueoHorario.unidad_id == t["auto"].id, BloqueoHorario.activo.is_(True))
            .order_by(BloqueoHorario.rango)
            .execution_options(populate_existing=True)
        )
    )


def _items(reserva):
    return sorted(reserva.items, key=lambda i: i.inicio_en)


# --- Reserva de un viaje ---


def test_reservar_por_tramo_retiene_el_vehiculo_mientras_se_paga(db, viajero, traslado):  # noqa: F811
    reserva = _reservar(db, viajero, traslado)
    assert reserva.estado is EstadoReserva.PENDIENTE_PAGO
    (item,) = reserva.items
    assert item.subtotal == Decimal(25000)
    assert (item.inicio_en, item.fin_en) == (_a_las(14), _a_las(14, 30))
    assert item.adultos == 3
    d = item.desglose
    assert (d["origen"], d["destino"], d["cobro"], d["sentido"], d["valijas"]) == (
        "Aeropuerto", "Centro", "tramo", "ida", 2,
    )
    assert item.datos_servicio["vuelo"] == "AR1672"
    assert item.datos_servicio["direccion_destino"] == "Hotel Lago, Mitre 120"

    (b,) = _bloqueos(db, traslado)
    assert b.origen is OrigenBloqueo.RETENCION and b.item_reserva_id == item.id
    # El viaje, la vuelta a la base y la preparación.
    assert (b.rango.lower, b.rango.upper) == (_a_las(14), _a_las(15, 10))
    assert b.vence_en == reserva.vence_pago_en


def test_la_reserva_guarda_su_comision_y_su_politica(db, viajero, traslado):  # noqa: F811
    # La política es del prestador: 100 % hasta 1 día antes, 50 % después.
    traslado["publicacion"].tramos_cancelacion = [
        {"dias_antes": 1, "porcentaje_reintegro": 100},
        {"dias_antes": 0, "porcentaje_reintegro": 50},
    ]
    db.flush()
    reserva = _reservar(db, viajero, traslado)
    (item,) = reserva.items
    c = db.scalar(select(ComisionAplicada).where(ComisionAplicada.item_reserva_id == item.id))
    assert c.base == Decimal(25000) and c.comision_neta == Decimal(2500)
    assert reserva.total == Decimal(25000)  # la comisión de la prueba la paga el prestador

    # Cambiar la política después no cambia lo reservado.
    traslado["publicacion"].tramos_cancelacion = [{"dias_antes": 0, "porcentaje_reintegro": 0}]
    db.flush()
    _pagar(db, reserva)
    assert reservas.calcular_reintegro(reserva, hoy=AHORA.date()).porcentaje == 100
    el_mismo_dia = _a_las(14).date()
    assert reservas.calcular_reintegro(reserva, hoy=el_mismo_dia).porcentaje == 50


def test_a_una_direccion_se_cobra_por_kilometro(db, viajero, traslado):  # noqa: F811
    destino = rt.Extremo(punto=HOTEL, direccion="Av. Bustillo km 2")
    reserva = _reservar(db, viajero, traslado, destino=destino)
    (item,) = reserva.items
    assert item.desglose["cobro"] == "km"
    assert item.desglose["destino"] == "Dirección elegida"
    km = Decimal(item.desglose["km"])
    assert item.subtotal == max(Decimal(10000), Decimal(2000) + km * 900)
    assert item.datos_servicio["punto_destino"] == {"lat": HOTEL.lat, "lon": HOTEL.lon}


def test_un_punto_sin_direccion_no_se_reserva(db, viajero, traslado):  # noqa: F811
    with pytest.raises(reservas.NoSePuedeReservar, match="dirección"):
        _reservar(db, viajero, traslado, destino=rt.Extremo(punto=HOTEL))


def test_un_lugar_de_otro_prestador_no_sirve(db, viajero, traslado, oferta):  # noqa: F811
    ajeno = LugarTraslado(
        publicacion_id=oferta["cara"].id, nombre="Otro", ubicacion=_punto(-41.14, -71.31)
    )
    db.add(ajeno)
    db.flush()
    with pytest.raises(reservas.NoSePuedeReservar, match="no es de este traslado"):
        _reservar(db, viajero, traslado, destino=rt.Extremo(lugar_id=ajeno.id))


def test_sin_tramo_ni_tarifa_por_km_no_se_reserva(db, viajero, traslado):  # noqa: F811
    traslado["tarifa"].precio_km = None
    traslado["tramo"].activo = False
    db.flush()
    with pytest.raises(reservas.NoSePuedeReservar, match="no hace ese recorrido"):
        _reservar(db, viajero, traslado)


def test_el_vehiculo_ocupado_no_se_reserva(db, viajero, traslado):  # noqa: F811
    _reservar(db, viajero, traslado)
    with pytest.raises(reservas.FechasTomadas):
        _reservar(db, viajero, traslado, inicio=_a_las(15))  # todavía vuelve a la base


def test_un_viaje_corto_sin_vuelta_se_puede_reservar(db, viajero, traslado):  # noqa: F811
    """15 minutos dentro de la ciudad, sin volver ni preparar: antes los bloqueos
    de horario pedían al menos 30 minutos."""
    traslado["tarifa"].vuelve_a_base = False
    traslado["tramo"].duracion_minutos = 15
    traslado["auto"].preparacion_minutos = 0
    db.flush()
    _reservar(db, viajero, traslado)
    (b,) = _bloqueos(db, traslado)
    assert b.rango.upper - b.rango.lower == timedelta(minutes=15)


# --- Ida y vuelta ---


def test_ida_y_vuelta_son_dos_items_de_la_misma_reserva(db, viajero, traslado):  # noqa: F811
    vuelta = _a_las(18, dias=5)
    reserva = _reservar(db, viajero, traslado, vuelta_inicio=vuelta, vuelo_vuelta="AR1673")
    ida, regreso = _items(reserva)
    assert (ida.desglose["sentido"], regreso.desglose["sentido"]) == ("ida", "vuelta")
    assert (regreso.desglose["origen"], regreso.desglose["destino"]) == ("Centro", "Aeropuerto")
    assert regreso.datos_servicio["vuelo"] == "AR1673"
    # La dirección del hotel es el origen de la vuelta.
    assert regreso.datos_servicio["direccion_origen"] == "Hotel Lago, Mitre 120"
    assert reserva.total == ida.subtotal + regreso.subtotal == Decimal(50000)
    assert all(i.comision is not None for i in reserva.items)
    assert [b.item_reserva_id for b in _bloqueos(db, traslado)] == [ida.id, regreso.id]


def test_si_la_vuelta_sale_enseguida_el_chofer_espera(db, viajero, traslado):  # noqa: F811
    """Llega 14:30 y la vuelta sale 14:45: no le da el tiempo de volver a la base
    (15:10). La ida queda tomada hasta que sale la vuelta, sin hueco ni choque."""
    reserva = _reservar(db, viajero, traslado, vuelta_inicio=_a_las(14, 45))
    ida, vuelta = _bloqueos(db, traslado)
    assert (ida.rango.lower, ida.rango.upper) == (_a_las(14), _a_las(14, 45))
    assert (vuelta.rango.lower, vuelta.rango.upper) == (_a_las(14, 45), _a_las(15, 55))
    assert len(reserva.items) == 2


def test_la_vuelta_no_puede_salir_antes_de_que_llegue_la_ida(db, viajero, traslado):  # noqa: F811
    with pytest.raises(reservas.NoSePuedeReservar, match="después de que llega"):
        _reservar(db, viajero, traslado, vuelta_inicio=_a_las(14, 20))


def test_si_la_vuelta_no_tiene_lugar_no_se_reserva_nada(db, viajero, traslado):  # noqa: F811
    db.commit()
    horarios.bloquear(
        db, traslado["auto"], _a_las(18, dias=5), _a_las(20, dias=5), OrigenBloqueo.MANUAL
    )
    db.commit()
    with pytest.raises(reservas.FechasTomadas, match="vuelta"):
        _reservar(db, viajero, traslado, vuelta_inicio=_a_las(18, dias=5))
    assert db.scalar(select(Reserva).where(Reserva.usuario_id == viajero.id)) is None
    assert [b.origen for b in _bloqueos(db, traslado)] == [OrigenBloqueo.MANUAL]


def test_la_vuelta_de_noche_lleva_su_recargo(db, viajero, traslado):  # noqa: F811
    reserva = _reservar(db, viajero, traslado, vuelta_inicio=_a_las(23, dias=5))
    ida, vuelta = _items(reserva)
    assert ida.subtotal == Decimal(25000)
    assert vuelta.subtotal == Decimal(30000)  # 20 % de recargo nocturno


# --- Pago, cancelación ---


def _pagar(db, reserva):
    return reservas.registrar_pago(db, reserva, "pago-1", "simulada", EstadoPago.APROBADO)


def test_el_pago_confirma_ida_y_vuelta(db, viajero, traslado):  # noqa: F811
    reserva = _reservar(db, viajero, traslado, vuelta_inicio=_a_las(18, dias=5))
    _pagar(db, reserva)
    assert reserva.estado is EstadoReserva.CONFIRMADA
    bloqueos = _bloqueos(db, traslado)
    assert [b.origen for b in bloqueos] == [OrigenBloqueo.RESERVA] * 2
    assert all(b.vence_en is None for b in bloqueos)


def test_un_pago_tardio_con_el_vehiculo_tomado_no_confirma(db, viajero, traslado):  # noqa: F811
    reserva = _reservar(db, viajero, traslado)
    # Venció la retención y otro tomó el vehículo a esa hora.
    for b in _bloqueos(db, traslado):
        b.vence_en = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()
    horarios.bloquear(db, traslado["auto"], _a_las(14), _a_las(15), OrigenBloqueo.MANUAL)
    _pagar(db, reserva)
    assert reserva.estado is EstadoReserva.CANCELADA
    assert reserva.pagos[0].estado == reservas.ESTADO_SIN_LUGAR


def test_cancelar_suelta_los_dos_viajes(db, viajero, traslado):  # noqa: F811
    reserva = _reservar(db, viajero, traslado, vuelta_inicio=_a_las(18, dias=5))
    _pagar(db, reserva)
    reservas.cancelar(db, reserva, "Cambié de planes", hoy=AHORA.date())
    assert reserva.estado is EstadoReserva.CANCELADA
    assert _bloqueos(db, traslado) == []


def test_sin_pagar_a_tiempo_se_suelta_el_vehiculo(db, viajero, traslado):  # noqa: F811
    reserva = _reservar(db, viajero, traslado)
    assert reservas.liberar_vencidas(db, reserva.vence_pago_en + timedelta(seconds=1)) == 1
    assert _bloqueos(db, traslado) == []


# --- Datos del viaje ---


def test_el_viajero_corrige_el_vuelo_de_los_viajes_que_no_salieron(db, viajero, traslado):  # noqa: F811
    reserva = _reservar(db, viajero, traslado, vuelta_inicio=_a_las(18, dias=5))
    rt.cambiar_datos(db, reserva, "AR1700", None, "Llevamos una silla de bebé", ahora=AHORA)
    ida, vuelta = _items(reserva)
    assert ida.datos_servicio["vuelo"] == "AR1700"
    assert vuelta.datos_servicio["vuelo"] is None  # no se tocó
    assert vuelta.datos_servicio["notas"] == "Llevamos una silla de bebé"

    # Pasada la ida, solo cambia la vuelta.
    rt.cambiar_datos(db, reserva, "XX1", "AR1800", None, ahora=_a_las(16))
    ida, vuelta = _items(reserva)
    assert (ida.datos_servicio["vuelo"], vuelta.datos_servicio["vuelo"]) == ("AR1700", "AR1800")

    with pytest.raises(reservas.TransicionInvalida, match="ya salieron"):
        rt.cambiar_datos(db, reserva, "X", "X", None, ahora=_a_las(19, dias=5))


def test_una_reserva_cancelada_no_cambia_sus_datos(db, viajero, traslado):  # noqa: F811
    reserva = _reservar(db, viajero, traslado)
    reservas.cancelar(db, reserva, "No viajo", hoy=AHORA.date())
    with pytest.raises(reservas.TransicionInvalida):
        rt.cambiar_datos(db, reserva, "AR1", None, None, ahora=AHORA)


def test_el_aviso_cuenta_el_recorrido_y_la_vuelta(db, viajero, traslado):  # noqa: F811
    reserva = _reservar(db, viajero, traslado, vuelta_inicio=_a_las(18, dias=5))
    datos = reservas._datos_para_aviso(reserva)
    assert datos["unidad"].startswith("Auto: Aeropuerto → Centro; vuelta Centro → Aeropuerto")
    assert datos["personas"] == "3 pasajeros"
    assert datos["desde"] == _a_las(14).strftime("%d/%m/%Y %H:%M")


# --- API ---


def _en(dias: int, hora: int) -> datetime:
    d = datetime.now(ZONA).date() + timedelta(days=dias)
    return datetime(d.year, d.month, d.day, hora, tzinfo=ZONA)


def _pedido_api(t, **kw) -> dict:
    return {
        "unidad_id": str(t["auto"].id),
        "origen": {"lugar_id": str(t["aeropuerto"].id)},
        "destino": {"lugar_id": str(t["centro"].id), "direccion": "Hotel Lago, Mitre 120"},
        "inicio": _en(3, 14).isoformat(),
        "pasajeros": 2,
        "vuelo_ida": "AR1672",
        **kw,
    }


def test_la_api_cotiza_ida_y_vuelta(cliente, traslado):  # noqa: F811
    r = cliente.post(
        "/api/v1/traslados/cotizacion",
        json=_pedido_api(traslado, vuelta_inicio=_en(6, 23).isoformat()),
    )
    assert r.status_code == 200, r.text
    c = r.json()
    assert [(v["sentido"], v["origen"], v["destino"]) for v in c["viajes"]] == [
        ("ida", "Aeropuerto", "Centro"), ("vuelta", "Centro", "Aeropuerto"),
    ]
    assert [ln["concepto"] for ln in c["viajes"][1]["lineas"]] == [
        "Traslado", "Recargo nocturno (20 %)",
    ]
    assert Decimal(c["total"]) == Decimal(55000)


def test_la_api_no_cotiza_un_alojamiento_como_traslado(cliente, traslado, oferta):  # noqa: F811
    r = cliente.post(
        "/api/v1/traslados/cotizacion",
        json=_pedido_api(traslado, unidad_id=str(oferta["u_cara"].id)),
    )
    assert r.status_code == 404


def test_la_api_rechaza_una_hora_sin_zona(cliente, traslado):  # noqa: F811
    sin_zona = _en(3, 14).replace(tzinfo=None).isoformat()
    r = cliente.post("/api/v1/traslados/cotizacion", json=_pedido_api(traslado, inicio=sin_zona))
    assert r.status_code == 422


def test_la_api_reserva_y_el_prestador_ve_los_datos_recien_pagada(
    cliente, db, traslado, viajero_api  # noqa: F811
):
    sin_terminos = cliente.post(
        "/api/v1/traslados/reservas", headers=viajero_api, json=_pedido_api(traslado)
    )
    assert sin_terminos.status_code == 422

    r = cliente.post(
        "/api/v1/traslados/reservas", headers=viajero_api,
        json={**_pedido_api(traslado), "acepta_terminos": True},
    )
    assert r.status_code == 201, r.text
    codigo = r.json()["codigo"]
    assert r.json()["items"][0]["datos_servicio"]["vuelo"] == "AR1672"

    dueno = db.get(Usuario, traslado["publicacion"].prestador.usuario_id)
    anfitrion = {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}

    def del_prestador():
        filas = cliente.get("/api/v1/mis-reservas", headers=anfitrion).json()
        return next(x for x in filas if x["codigo"] == codigo)

    # Sin pagar, el prestador no ve adónde ni qué vuelo.
    assert del_prestador()["items"][0]["datos_servicio"] is None
    _pagar(db, reservas.traer(db, codigo))
    db.commit()
    assert del_prestador()["items"][0]["datos_servicio"]["direccion_destino"] == (
        "Hotel Lago, Mitre 120"
    )

    r = cliente.patch(
        f"/api/v1/traslados/reservas/{codigo}/viaje", headers=viajero_api,
        json={"vuelo_ida": "AR1700"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["datos_servicio"]["vuelo"] == "AR1700"


def test_otro_viajero_no_cambia_los_datos_ajenos(cliente, db, traslado, viajero_api):  # noqa: F811
    otra = Usuario(
        email="otra@ejemplo.com.ar", nombre="Eva", apellido="Gómez", email_verificado=True
    )
    db.add(otra)
    db.flush()
    ajena = rt.crear_traslado(
        db, otra, traslado["auto"],
        rt.Pedido(
            origen=rt.Extremo(lugar_id=traslado["aeropuerto"].id),
            destino=rt.Extremo(lugar_id=traslado["centro"].id),
            inicio=_en(3, 14), pasajeros=1,
        ),
    )
    db.commit()
    r = cliente.patch(
        f"/api/v1/traslados/reservas/{ajena.codigo}/viaje", headers=viajero_api,
        json={"vuelo_ida": "AR1"},
    )
    assert r.status_code == 404
