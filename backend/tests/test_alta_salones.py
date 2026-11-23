"""Alta y edición de salones por el propietario (docs/04, etapa 3)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    BloqueoHorario,
    Comodidad,
    PoliticaCancelacion,
    Prestador,
    SubtipoServicio,
    TipoServicio,
    Unidad,
)
from app.models.enums import ModoReserva, OrigenBloqueo
from tests.test_alta_publicaciones import (  # noqa: F401  (fixtures)
    _imagen,
    catalogo,
    media,
    prestador,
)


@pytest.fixture
def catalogo_salon(db, catalogo):  # noqa: F811
    tipo = TipoServicio(
        codigo="salon_eventos", nombre="Salón de eventos", modo_reserva=ModoReserva.HORAS
    )
    db.add(tipo)
    db.flush()
    subtipo = SubtipoServicio(tipo_id=tipo.id, codigo="quincho_eventos", nombre="Quincho")
    pista = Comodidad(codigo="pista", nombre="Pista de baile", tipos=[tipo])
    eventos = PoliticaCancelacion(
        codigo="eventos", nombre="Eventos",
        tramos=[{"dias_antes": 30, "porcentaje_reintegro": 90}],
    )
    db.add_all([subtipo, pista, eventos])
    db.commit()
    return {**catalogo, "tipo_salon": tipo, "subtipo_salon": subtipo, "eventos": eventos}


def _crear_salon(cliente, prestador, cat) -> dict:  # noqa: F811
    r = cliente.post(
        "/api/v1/mis-publicaciones",
        headers=prestador,
        json={
            "titulo": "Quincho Los Búhos",
            "localidad_id": str(cat["localidad"].id),
            "subtipo_servicio_id": str(cat["subtipo_salon"].id),
            "tipo": "salon_eventos",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _espacio(cliente, prestador, pid, **kw):  # noqa: F811
    datos = {"nombre": "Quincho", "capacidad": 150, "capacidad_sentados": 100}
    datos.update(kw)
    return cliente.post(f"/api/v1/mis-publicaciones/{pid}/unidades", headers=prestador, json=datos)


def _url(pid, uid, resto=""):
    return f"/api/v1/mis-publicaciones/{pid}/unidades/{uid}{resto}"


# --- Alta ---


def test_un_salon_nace_a_solicitud_y_con_la_politica_de_eventos(
    cliente, prestador, catalogo_salon  # noqa: F811
):
    p = _crear_salon(cliente, prestador, catalogo_salon)
    assert p["tipo"] == "salon_eventos"
    assert p["modo_reserva"] == "horas"
    assert p["confirmacion_inmediata"] is False
    assert p["politica_cancelacion_id"] == str(catalogo_salon["eventos"].id)


def test_un_salon_no_puede_ser_cabana(cliente, prestador, catalogo_salon):  # noqa: F811
    r = cliente.post(
        "/api/v1/mis-publicaciones",
        headers=prestador,
        json={
            "titulo": "Quincho", "localidad_id": str(catalogo_salon["localidad"].id),
            "subtipo_servicio_id": str(catalogo_salon["subtipo"].id), "tipo": "salon_eventos",
        },
    )
    assert r.status_code == 422


def test_lo_que_falta_es_lo_de_un_salon(cliente, prestador, catalogo_salon):  # noqa: F811
    p = _crear_salon(cliente, prestador, catalogo_salon)
    faltantes = " · ".join(p["faltantes"])
    assert "ingreso y salida" not in faltantes
    assert "al menos un espacio" in faltantes

    uid = _espacio(cliente, prestador, p["id"]).json()["unidades"][0]["id"]
    r = cliente.get(f"/api/v1/mis-publicaciones/{p['id']}", headers=prestador).json()
    assert any("Sin turnos ni precio por hora: Quincho" in f for f in r["faltantes"])

    cliente.post(
        _url(p["id"], uid, "/franjas"), headers=prestador,
        json={"nombre": "Noche", "hora_inicio": "21:00", "hora_fin": "05:00", "precio": "400000"},
    )
    r = cliente.get(f"/api/v1/mis-publicaciones/{p['id']}", headers=prestador).json()
    assert not any("Sin turnos" in f for f in r["faltantes"])


# --- Capacidad ---


def test_un_salon_admite_mas_de_30_y_una_cabana_no(
    cliente, prestador, catalogo_salon  # noqa: F811
):
    p = _crear_salon(cliente, prestador, catalogo_salon)
    r = _espacio(cliente, prestador, p["id"], capacidad=300, capacidad_sentados=200)
    assert r.status_code == 201, r.text
    u = r.json()["unidades"][0]
    assert (u["capacidad"], u["capacidad_sentados"]) == (300, 200)

    from tests.test_alta_publicaciones import _crear

    cabana = _crear(cliente, prestador, catalogo_salon)
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{cabana}/unidades", headers=prestador,
        json={"nombre": "Cabaña", "capacidad": 40},
    )
    assert r.status_code == 422
    assert "hasta 30" in r.json()["detail"]


def test_sentados_no_pueden_superar_la_capacidad(cliente, prestador, catalogo_salon):  # noqa: F811
    p = _crear_salon(cliente, prestador, catalogo_salon)
    r = _espacio(cliente, prestador, p["id"], capacidad=100, capacidad_sentados=120)
    assert r.status_code == 422


# --- Turnos, horas y adicionales ---


def test_turnos_precio_por_hora_y_adicionales(cliente, prestador, catalogo_salon):  # noqa: F811
    p = _crear_salon(cliente, prestador, catalogo_salon)
    uid = _espacio(cliente, prestador, p["id"]).json()["unidades"][0]["id"]

    r = cliente.post(
        _url(p["id"], uid, "/franjas"), headers=prestador,
        json={
            "nombre": "Noche", "hora_inicio": "21:00", "hora_fin": "05:00",
            "precio": "400000", "precios_dia_semana": {"5": "550000"},
        },
    )
    assert r.status_code == 201, r.text
    franja = r.json()["unidades"][0]["franjas"][0]
    assert franja["precios_dia_semana"] == {"5": "550000"}

    r = cliente.put(
        _url(p["id"], uid, "/tarifa-horaria"), headers=prestador,
        json={
            "precio_hora": "40000", "horas_minimas": 3,
            "hora_apertura": "10:00", "hora_cierre": "02:00",
            "recargo_nocturno_desde": "00:00", "recargo_nocturno_porcentaje": "20",
        },
    )
    assert r.status_code == 200, r.text
    # Guardarla de nuevo la reemplaza, no agrega otra.
    r = cliente.put(
        _url(p["id"], uid, "/tarifa-horaria"), headers=prestador,
        json={"precio_hora": "45000", "hora_apertura": "10:00", "hora_cierre": "02:00"},
    )
    assert r.json()["unidades"][0]["tarifa_horaria"]["precio_hora"] == "45000.00"

    r = cliente.post(
        _url(p["id"], uid, "/adicionales"), headers=prestador,
        json={"nombre": "Vajilla", "precio": "800", "por_persona": True},
    )
    adicional = r.json()["unidades"][0]["adicionales"][0]
    assert adicional["por_persona"] is True

    # Y se quitan.
    r = cliente.delete(_url(p["id"], uid, f"/franjas/{franja['id']}"), headers=prestador)
    assert r.json()["unidades"][0]["franjas"] == []
    r = cliente.delete(_url(p["id"], uid, "/tarifa-horaria"), headers=prestador)
    assert r.json()["unidades"][0]["tarifa_horaria"] is None
    r = cliente.delete(_url(p["id"], uid, f"/adicionales/{adicional['id']}"), headers=prestador)
    assert r.json()["unidades"][0]["adicionales"] == []


@pytest.mark.parametrize(
    "franja",
    [
        {"nombre": "X", "hora_inicio": "21:00", "hora_fin": "21:00", "precio": "1"},
        {"nombre": "X", "hora_inicio": "21:00", "hora_fin": "23:00", "precio": "0"},
        {"nombre": "X", "hora_inicio": "21:00", "hora_fin": "23:00", "precio": "1",
         "precios_dia_semana": {"8": "1"}},
    ],
)
def test_turnos_mal_cargados_se_rechazan(cliente, prestador, catalogo_salon, franja):  # noqa: F811
    p = _crear_salon(cliente, prestador, catalogo_salon)
    uid = _espacio(cliente, prestador, p["id"]).json()["unidades"][0]["id"]
    assert cliente.post(_url(p["id"], uid, "/franjas"), headers=prestador, json=franja
                        ).status_code == 422


def test_cada_tipo_se_cobra_a_su_manera(cliente, prestador, catalogo_salon):  # noqa: F811
    from tests.test_alta_publicaciones import _crear

    salon = _crear_salon(cliente, prestador, catalogo_salon)
    uid = _espacio(cliente, prestador, salon["id"]).json()["unidades"][0]["id"]
    r = cliente.post(
        _url(salon["id"], uid, "/tarifas"), headers=prestador,
        json={"nombre": "Base", "precio_noche": "1000"},
    )
    assert r.status_code == 409

    cabana = _crear(cliente, prestador, catalogo_salon)
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{cabana}/unidades", headers=prestador,
        json={"nombre": "Cabaña", "capacidad": 4},
    )
    cid = r.json()["unidades"][0]["id"]
    r = cliente.post(
        _url(cabana, cid, "/franjas"), headers=prestador,
        json={"nombre": "Noche", "hora_inicio": "21:00", "hora_fin": "05:00", "precio": "1"},
    )
    assert r.status_code == 409


# --- Seña ---


def test_la_sena_se_guarda_y_el_cero_es_sin_sena(cliente, prestador, catalogo_salon):  # noqa: F811
    p = _crear_salon(cliente, prestador, catalogo_salon)
    url = f"/api/v1/mis-publicaciones/{p['id']}"
    assert cliente.patch(url, headers=prestador, json={"porcentaje_sena": 30}).json()[
        "porcentaje_sena"
    ] == 30
    assert cliente.patch(url, headers=prestador, json={"porcentaje_sena": 0}).json()[
        "porcentaje_sena"
    ] is None
    assert cliente.patch(url, headers=prestador, json={"porcentaje_sena": 150}).status_code == 422


def test_la_base_rechaza_una_sena_fuera_de_rango(db, prestador):  # noqa: F811
    prest = db.scalar(select(Prestador))
    prest.porcentaje_sena = 150
    with pytest.raises(IntegrityError), db.begin_nested():
        db.flush()


# --- Borrar ---


def test_un_espacio_con_horas_tomadas_se_desactiva_no_se_borra(
    cliente, db, prestador, catalogo_salon  # noqa: F811
):
    from app.services import horarios
    from app.services.horarios import ZONA

    p = _crear_salon(cliente, prestador, catalogo_salon)
    uid = _espacio(cliente, prestador, p["id"]).json()["unidades"][0]["id"]
    unidad = db.get(Unidad, uid)
    inicio = datetime.now(ZONA).replace(minute=0, second=0, microsecond=0) + timedelta(days=10)
    horarios.bloquear(db, unidad, inicio, inicio + timedelta(hours=3), OrigenBloqueo.MANUAL)
    db.commit()

    r = cliente.delete(_url(p["id"], uid), headers=prestador)
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Unidad, uid).activa is False
    assert db.scalar(select(BloqueoHorario).where(BloqueoHorario.unidad_id == uid)) is not None


@pytest.mark.parametrize("valor", ["1e30", "inf", "NaN", "0", "-5", "12.345"])
def test_precios_por_dia_tienen_el_mismo_limite_que_el_base(
    cliente, prestador, catalogo_salon, valor  # noqa: F811
):
    """Un valor fuera de rango guardado rompería cada cotización de ese salón."""
    p = _crear_salon(cliente, prestador, catalogo_salon)
    uid = _espacio(cliente, prestador, p["id"]).json()["unidades"][0]["id"]
    r = cliente.post(
        _url(p["id"], uid, "/franjas"), headers=prestador,
        json={"nombre": "Noche", "hora_inicio": "21:00", "hora_fin": "05:00",
              "precio": "1000", "precios_dia_semana": {"5": valor}},
    )
    assert r.status_code == 422, r.text


def test_la_tarifa_por_noche_tampoco_acepta_cualquier_cosa(
    cliente, prestador, catalogo_salon  # noqa: F811
):
    from tests.test_alta_publicaciones import _crear

    cabana = _crear(cliente, prestador, catalogo_salon)
    uid = cliente.post(
        f"/api/v1/mis-publicaciones/{cabana}/unidades", headers=prestador,
        json={"nombre": "Cabaña", "capacidad": 4},
    ).json()["unidades"][0]["id"]
    url = _url(cabana, uid, "/tarifas")
    r = cliente.post(url, headers=prestador, json={
        "nombre": "Base", "precio_noche": "1000", "precios_dia_semana": {"5": "abc"}})
    assert r.status_code == 422
    r = cliente.post(url, headers=prestador, json={
        "nombre": "Base", "precio_noche": "1000", "precios_dia_semana": {"5": "1500"}})
    assert r.status_code == 201, r.text
