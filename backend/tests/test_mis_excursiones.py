"""Excursiones, etapa 3 (docs/05): el prestador publica su actividad, carga turnos,
precios y sus propias reglas, y maneja sus salidas desde el panel."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    CupoTomado,
    PrecioPasajero,
    ReglaComision,
    SubtipoServicio,
    TipoServicio,
    TurnoExcursion,
    Usuario,
)
from app.models.enums import EstadoReserva, ModoReserva, OrigenBloqueo, QuienPaga
from app.services import reservas, salidas
from app.services import reservas_excursion as rx
from app.services.pagos.base import EstadoPago
from tests.test_alta_publicaciones import (  # noqa: F401  (fixtures)
    _cuenta,
    catalogo,
    media,
    prestador,
)
from tests.test_excursiones import MARTES, _proximo


@pytest.fixture
def catalogo_excursion(db, catalogo):  # noqa: F811
    tipo = TipoServicio(
        codigo="excursion", nombre="Excursión", modo_reserva=ModoReserva.TURNO_CUPO
    )
    db.add(tipo)
    db.flush()
    subtipo = SubtipoServicio(tipo_id=tipo.id, codigo="cabalgata", nombre="Cabalgata")
    db.add(subtipo)
    db.commit()
    return {**catalogo, "tipo_exc": tipo, "subtipo_exc": subtipo}


def _url(pid, uid="", resto=""):
    base = f"/api/v1/mis-publicaciones/{pid}"
    return f"{base}/unidades/{uid}{resto}" if uid else f"{base}{resto}"


@pytest.fixture
def actividad(cliente, prestador, catalogo_excursion):  # noqa: F811
    """Una cabalgata en borrador con su actividad, un turno martes y jueves y precios."""
    r = cliente.post(
        "/api/v1/mis-publicaciones", headers=prestador,
        json={
            "titulo": "Cabalgata al Dique", "tipo": "excursion",
            "localidad_id": str(catalogo_excursion["localidad"].id),
            "subtipo_servicio_id": str(catalogo_excursion["subtipo_exc"].id),
        },
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = cliente.post(
        _url(pid, resto="/unidades"), headers=prestador,
        json={"nombre": "Cabalgata", "capacidad": 8},
    )
    assert r.status_code == 201, r.text
    uid = r.json()["unidades"][0]["id"]
    return {"pid": pid, "uid": uid}


def _turno(cliente, prestador, a, **kw):  # noqa: F811
    datos = {
        "nombre": "Mañana", "dias_semana": [MARTES, 3], "hora_inicio": "09:00",
        "duracion_minutos": 180, "cupo": 10, **kw,
    }
    return cliente.post(_url(a["pid"], a["uid"], "/turnos"), headers=prestador, json=datos)


def _precio(cliente, prestador, a, **kw):  # noqa: F811
    datos = {"nombre": "Adulto", "precio": "30000", **kw}
    return cliente.post(
        _url(a["pid"], a["uid"], "/precios-pasajero"), headers=prestador, json=datos
    )


# --- Alta ---


def test_una_excursion_nace_sin_horarios_de_alojamiento_y_pide_lo_suyo(
    cliente, prestador, actividad  # noqa: F811
):
    p = cliente.get(_url(actividad["pid"]), headers=prestador).json()
    assert (p["tipo"], p["modo_reserva"]) == ("excursion", "turno_cupo")
    assert p["reintegro_si_no_sale"] == 100
    faltan = p["faltantes"]
    assert "Sin turnos ni salidas: Cabalgata" in faltan
    assert "Sin precios por pasajero: Cabalgata" in faltan
    assert not any("ingreso y salida" in f for f in faltan)

    _turno(cliente, prestador, actividad)
    _precio(cliente, prestador, actividad)
    faltan = cliente.get(_url(actividad["pid"]), headers=prestador).json()["faltantes"]
    assert not any(f.startswith(("Sin turnos", "Sin precios")) for f in faltan)


def test_los_tramos_propios_alcanzan_como_politica(cliente, prestador, actividad):  # noqa: F811
    r = cliente.patch(
        _url(actividad["pid"]), headers=prestador,
        json={"tramos_cancelacion": [
            {"dias_antes": 1, "porcentaje_reintegro": 50},
            {"dias_antes": 3, "porcentaje_reintegro": 100},
        ], "reintegro_si_no_sale": 90},
    )
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["tramos_cancelacion"][0] == {"dias_antes": 3, "porcentaje_reintegro": 100}
    assert p["reintegro_si_no_sale"] == 90
    assert "Falta elegir una política de cancelación" not in p["faltantes"]

    # Vacío vuelve a la plantilla.
    p = cliente.patch(
        _url(actividad["pid"]), headers=prestador, json={"tramos_cancelacion": []}
    ).json()
    assert p["tramos_cancelacion"] is None
    assert "Falta elegir una política de cancelación" in p["faltantes"]


@pytest.mark.parametrize(
    ("cambios", "codigo"),
    [
        ({"tramos_cancelacion": [{"dias_antes": 1, "porcentaje_reintegro": 150}]}, 422),
        ({"reintegro_si_no_sale": 101}, 422),
    ],
)
def test_parametros_fuera_de_rango_se_rechazan(cliente, prestador, actividad, cambios, codigo):  # noqa: F811
    r = cliente.patch(_url(actividad["pid"]), headers=prestador, json=cambios)
    assert r.status_code == codigo


def test_una_actividad_puede_tener_mas_de_30_por_reserva(cliente, prestador, actividad):  # noqa: F811
    r = cliente.post(
        _url(actividad["pid"], resto="/unidades"), headers=prestador,
        json={"nombre": "Grupo escolar", "capacidad": 45},
    )
    assert r.status_code == 201, r.text


# --- Turnos y precios ---


def test_el_turno_queda_con_su_minimo_y_se_puede_quitar(cliente, prestador, actividad):  # noqa: F811
    r = _turno(cliente, prestador, actividad, minimo_personas=4, aviso_minimo_horas=48)
    assert r.status_code == 201, r.text
    turno = r.json()["unidades"][0]["turnos"][0]
    assert (turno["dias_semana"], turno["minimo_personas"], turno["aviso_minimo_horas"]) == (
        [1, 3], 4, 48
    )
    r = cliente.delete(
        _url(actividad["pid"], actividad["uid"], f"/turnos/{turno['id']}"), headers=prestador
    )
    assert r.json()["unidades"][0]["turnos"] == []


def test_un_turno_con_minimo_mayor_que_el_cupo_se_rechaza(cliente, prestador, actividad):  # noqa: F811
    r = _turno(cliente, prestador, actividad, cupo=6, minimo_personas=8)
    assert r.status_code == 422
    assert "mínimo de personas" in r.json()["detail"]


def test_los_precios_llevan_edades_y_si_ocupan_lugar(cliente, prestador, actividad):  # noqa: F811
    _precio(cliente, prestador, actividad)
    r = _precio(
        cliente, prestador, actividad, nombre="Bebé en brazos", precio="0", edad_hasta=2,
        ocupa_lugar=False,
    )
    assert r.status_code == 201, r.text
    precios = r.json()["unidades"][0]["precios_pasajero"]
    assert [(x["nombre"], x["ocupa_lugar"]) for x in precios] == [
        ("Adulto", True), ("Bebé en brazos", False),
    ]
    assert _precio(cliente, prestador, actividad, nombre="adulto").status_code == 409
    assert _precio(
        cliente, prestador, actividad, nombre="Menor", edad_desde=12, edad_hasta=3
    ).status_code == 422


def test_un_salon_o_alojamiento_no_acepta_turnos_de_excursion(
    cliente, prestador, catalogo_excursion  # noqa: F811
):
    r = cliente.post(
        "/api/v1/mis-publicaciones", headers=prestador,
        json={"titulo": "Cabañas", "localidad_id": str(catalogo_excursion["localidad"].id)},
    )
    pid = r.json()["id"]
    uid = cliente.post(
        _url(pid, resto="/unidades"), headers=prestador, json={"nombre": "C1", "capacidad": 4}
    ).json()["unidades"][0]["id"]
    r = _turno(cliente, prestador, {"pid": pid, "uid": uid})
    assert r.status_code == 409


def test_otro_prestador_no_toca_mis_turnos(cliente, db, prestador, actividad):  # noqa: F811
    token = _cuenta(cliente, db, "otro@ejemplo.com.ar", habilitado=True)
    otro = {"Authorization": f"Bearer {token}"}
    assert _turno(cliente, otro, actividad).status_code == 404
    r = cliente.get(_url(actividad["pid"], actividad["uid"], "/salidas"), headers=otro)
    assert r.status_code == 404


# --- Panel de salidas ---


def _salidas(cliente, prestador, a, desde=None):  # noqa: F811
    desde = desde or _proximo(MARTES) - timedelta(days=1)
    r = cliente.get(
        _url(a["pid"], a["uid"], "/salidas"), headers=prestador,
        params={"desde": desde.isoformat(), "hasta": (desde + timedelta(days=6)).isoformat()},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _eleccion(salida):
    return {"fecha": salida["fecha"], "turno_id": salida["turno_id"]} if not salida[
        "salida_id"
    ] else {"fecha": salida["fecha"], "salida_id": salida["salida_id"]}


def test_el_panel_muestra_las_salidas_y_anota_ventas_por_fuera(cliente, prestador, actividad):  # noqa: F811
    _turno(cliente, prestador, actividad)
    martes, jueves = _salidas(cliente, prestador, actividad)
    assert (martes["cupo"], martes["libres"], martes["salida_id"]) == (10, 10, None)

    r = cliente.post(
        _url(actividad["pid"], actividad["uid"], "/salidas/anotar"), headers=prestador,
        json={**_eleccion(martes), "personas": 3, "nota": "Familia Gómez, por WhatsApp"},
    )
    assert r.status_code == 200, r.text
    s = r.json()
    assert (s["libres"], s["ocupados"]) == (7, 3)
    assert s["anotados"][0]["origen"] == "externa"
    assert s["anotados"][0]["nota"] == "Familia Gómez, por WhatsApp"

    r = cliente.post(
        _url(actividad["pid"], actividad["uid"], "/salidas/anotar"), headers=prestador,
        json={**_eleccion(s), "personas": 8},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "Quedan 7 lugares en esta salida"

    r = cliente.delete(
        _url(actividad["pid"], actividad["uid"], f"/salidas/anotados/{s['anotados'][0]['id']}"),
        headers=prestador,
    )
    assert r.json()["libres"] == 10


def test_el_cupo_de_una_salida_no_baja_del_minimo_ni_de_lo_tomado(
    cliente, prestador, actividad  # noqa: F811
):
    _turno(cliente, prestador, actividad, minimo_personas=4)
    martes = _salidas(cliente, prestador, actividad)[0]
    ruta = _url(actividad["pid"], actividad["uid"], "/salidas/cupo")
    r = cliente.post(ruta, headers=prestador, json={**_eleccion(martes), "cupo": 3})
    assert r.status_code == 422
    r = cliente.post(ruta, headers=prestador, json={**_eleccion(martes), "cupo": 14})
    assert r.json()["cupo"] == 14


def test_suspender_cancela_las_reservas_con_el_reintegro_del_prestador(
    cliente, db, prestador, actividad  # noqa: F811
):
    _turno(cliente, prestador, actividad)
    _precio(cliente, prestador, actividad)
    cliente.patch(_url(actividad["pid"]), headers=prestador, json={"reintegro_si_no_sale": 80})
    # Aprobada a mano: la revisión del operador no es lo que se prueba acá.
    from app.models import Publicacion, Unidad
    from app.models.enums import EstadoPublicacion

    unidad = db.get(Unidad, actividad["uid"])
    db.get(Publicacion, actividad["pid"]).estado = EstadoPublicacion.APROBADA
    db.add(ReglaComision(nombre="General", es_default=True, activa=True,
                         porcentaje=Decimal(10), quien_paga=QuienPaga.PRESTADOR))
    viajero = Usuario(email="v@ejemplo.com.ar", nombre="Vera", apellido="L",
                      email_verificado=True, telefono="+5492644123456")
    db.add(viajero)
    db.flush()
    adulto = db.scalar(select(PrecioPasajero).where(PrecioPasajero.unidad_id == unidad.id))
    martes = _proximo(MARTES)
    turno_id = uuid.UUID(_salidas(cliente, prestador, actividad)[0]["turno_id"])
    reserva = rx.crear_excursion(db, viajero, unidad, martes, {adulto.id: 2}, turno_id=turno_id)
    reservas.registrar_pago(db, reserva, "p-1", "simulada", EstadoPago.APROBADO)
    db.commit()

    s = _salidas(cliente, prestador, actividad)[0]
    assert s["anotados"][0]["viajero"] == "Vera"  # confirmada: se ve el nombre
    assert s["anotados"][0]["reserva"] == reserva.codigo

    r = cliente.delete(
        _url(actividad["pid"], actividad["uid"], f"/salidas/anotados/{s['anotados'][0]['id']}"),
        headers=prestador,
    )
    assert r.status_code == 409  # una reserva nuestra se cancela desde la reserva

    r = cliente.post(
        _url(actividad["pid"], actividad["uid"], "/salidas/suspender"), headers=prestador,
        json={**_eleccion(s), "motivo": "Alerta por viento Zonda"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["reservas_canceladas"] == 1
    assert Decimal(d["a_devolver"]) == (reserva.total * Decimal("0.8")).quantize(Decimal("0.01"))
    assert d["salida"]["suspendida"] is True
    assert d["salida"]["motivo"] == "Alerta por viento Zonda"
    db.refresh(reserva)
    assert reserva.estado is EstadoReserva.CANCELADA

    r = cliente.post(
        _url(actividad["pid"], actividad["uid"], "/salidas/reanudar"), headers=prestador,
        json=_eleccion(d["salida"]),
    )
    assert r.json()["suspendida"] is False


def test_el_nombre_del_viajero_no_se_ve_antes_de_confirmar(cliente, db, prestador, actividad):  # noqa: F811
    _turno(cliente, prestador, actividad)
    martes = _salidas(cliente, prestador, actividad)[0]
    fila = salidas.materializar(db, db.get(TurnoExcursion, martes["turno_id"]), _proximo(MARTES))
    salidas.tomar(db, fila, 2, OrigenBloqueo.RETENCION)
    db.commit()
    anotado = _salidas(cliente, prestador, actividad)[0]["anotados"][0]
    assert (anotado["origen"], anotado["viajero"]) == ("retencion", None)
    assert db.scalar(select(CupoTomado.id)) is not None


def test_una_salida_especial_aparece_en_el_panel(cliente, prestador, actividad):  # noqa: F811
    lunes = _proximo(0)
    r = cliente.post(
        _url(actividad["pid"], actividad["uid"], "/salidas"), headers=prestador,
        json={"fecha": lunes.isoformat(), "hora_inicio": "19:00", "duracion_minutos": 120,
              "cupo": 6, "nombre": "Luna llena"},
    )
    assert r.status_code == 201, r.text
    assert (r.json()["nombre"], r.json()["cupo"]) == ("Salida especial", 6)
    assert _salidas(cliente, prestador, actividad, desde=lunes)[0]["fecha"] == lunes.isoformat()


def test_las_salidas_especiales_tienen_tope(cliente, prestador, actividad, monkeypatch):  # noqa: F811
    from app.api.v1 import mis_excursiones

    monkeypatch.setattr(mis_excursiones, "MAX_SALIDAS_ESPECIALES", 2)
    ruta = _url(actividad["pid"], actividad["uid"], "/salidas")
    for n in range(3):
        r = cliente.post(
            ruta, headers=prestador,
            json={"fecha": (_proximo(0) + timedelta(days=n)).isoformat(),
                  "hora_inicio": "19:00", "duracion_minutos": 120, "cupo": 6},
        )
        assert r.status_code == (201 if n < 2 else 409), r.text
    assert "cargalas como turno" in r.json()["detail"]
