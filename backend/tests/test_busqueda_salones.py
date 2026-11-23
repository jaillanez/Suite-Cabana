"""Salones para el viajero (docs/04, etapa 4): buscar, ficha, y si hay lugar un día."""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest

from app.models import Unidad
from app.models.enums import OrigenBloqueo
from app.services import horarios
from app.services import salones as svc
from app.services.horarios import ZONA
from tests.test_api_salones import DIA, evento  # noqa: F401  (fixture)
from tests.test_salones import salon  # noqa: F401  (fixture)


def _h(hora: int, minuto: int = 0, dias: int = 0) -> datetime:
    d = DIA + timedelta(days=dias)
    return datetime(d.year, d.month, d.day, hora, minuto, tzinfo=ZONA)


def _tomar(db, unidad, inicio, fin):
    horarios.bloquear(db, unidad, inicio, fin, OrigenBloqueo.MANUAL)
    db.flush()


# --- Buscar ---


def test_sin_dia_aparece_con_su_precio_desde(cliente, evento):  # noqa: F811
    r = cliente.get("/api/v1/salones/buscar", params={"localidad": "bariloche"}).json()
    assert r["total"] == 1
    s = r["resultados"][0]
    assert s["titulo"] == "Salón Los Álamos"
    assert (s["capacidad_maxima"], s["sentados_maximo"]) == (120, 80)
    # Lo más barato: 3 h mínimas × 40.000 = 120.000 (el turno más barato sale 150.000).
    assert Decimal(s["precio_desde"]["monto"]) == Decimal(120000)
    assert s["precio_desde"]["detalle"] == "por 3 h"
    assert s["disponible"] is None
    assert s["lat"] == round(s["lat"], 2)


def test_mas_invitados_que_la_capacidad_no_aparece(cliente, evento):  # noqa: F811
    r = cliente.get(
        "/api/v1/salones/buscar", params={"localidad": "bariloche", "invitados": 121}
    ).json()
    assert r["total"] == 0


def test_con_dia_solo_lo_que_tiene_lugar(cliente, db, evento):  # noqa: F811
    params = {"localidad": "bariloche", "dia": DIA.isoformat()}
    assert cliente.get("/api/v1/salones/buscar", params=params).json()["total"] == 1
    # Todo el día tomado: turnos y horas.
    _tomar(db, evento["unidad"], _h(8), _h(6, dias=1))
    db.commit()
    assert cliente.get("/api/v1/salones/buscar", params=params).json()["total"] == 0


def test_los_salones_no_salen_en_la_busqueda_de_cabanas_ni_al_reves(cliente, evento):  # noqa: F811
    r = cliente.get("/api/v1/salones/buscar", params={"localidad": "bariloche"}).json()
    assert {x["titulo"] for x in r["resultados"]} == {"Salón Los Álamos"}


def test_un_dia_pasado_se_rechaza(cliente, evento):  # noqa: F811
    from datetime import date

    ayer = (date.today() - timedelta(days=1)).isoformat()
    r = cliente.get("/api/v1/salones/buscar", params={"dia": ayer})
    assert r.status_code == 422


def test_destinos_cuenta_solo_salones(cliente, evento):  # noqa: F811
    d = cliente.get("/api/v1/salones/destinos").json()
    assert [(x["slug"], x["salones"]) for x in d] == [("bariloche", 1)]


# --- Hay lugar por horas (sin turnos) ---


@pytest.fixture
def solo_horas(db, evento):  # noqa: F811
    for f in evento["unidad"].franjas:
        f.activa = False
    db.flush()
    return db.get(Unidad, evento["unidad"].id)


@pytest.mark.parametrize(
    ("ocupado", "hay"),
    [
        # Atiende de 10 a 2, mínimo 3 h, 1 h de preparación.
        ([], True),
        # 22:30 a 2: 3,5 h libres hasta el cierre (al cierre no hace falta preparar).
        ([(_h(10), _h(22, 30))], True),
        # 23:30 a 2: 2,5 h. No alcanza.
        ([(_h(10), _h(23, 30))], False),
        # Entre dos eventos hacen falta 3 h + 1 h de preparación antes del siguiente.
        ([(_h(10), _h(12)), (_h(15, 30), _h(2, dias=1))], False),
        ([(_h(10), _h(12)), (_h(16), _h(2, dias=1))], True),
    ],
)
def test_hay_lugar_busca_un_hueco_del_minimo(db, solo_horas, ocupado, hay):
    for inicio, fin in ocupado:
        _tomar(db, solo_horas, inicio, fin)
    assert svc.hay_lugar(db, solo_horas, DIA) is hay


# --- Ficha ---


def test_la_ficha_trae_espacios_turnos_y_sena(cliente, db, evento, oferta):  # noqa: F811
    evento["oferta_cara_titulo"] = oferta["cara"].titulo
    evento["publicacion"].direccion = "Ruta 40 km 3"
    db.commit()
    r = cliente.get(f"/api/v1/salones/ficha/{evento['publicacion'].slug}")
    assert r.status_code == 200, r.text
    f = r.json()
    assert "Ruta 40" not in r.text  # la dirección, solo con la reserva confirmada
    assert f["porcentaje_sena"] == 30
    espacio = f["espacios"][0]
    assert [x["nombre"] for x in espacio["franjas"]] == ["Mañana", "Noche"]
    assert espacio["franjas"][1]["termina_al_dia_siguiente"] is True
    assert espacio["por_horas"]["horas_minimas"] == 3
    assert espacio["adicionales"][0]["nombre"] == "Vajilla"
    # Las cabañas del mismo anfitrión, para ofrecer dormir ahí (solo las aprobadas).
    assert evento["oferta_cara_titulo"] in {x["titulo"] for x in f["alojamientos_del_anfitrion"]}
    assert "Sin Aprobar" not in {x["titulo"] for x in f["alojamientos_del_anfitrion"]}


def test_la_ficha_de_cabana_avisa_que_hay_salon(cliente, evento, oferta):  # noqa: F811
    r = cliente.get(f"/api/v1/publicaciones/{oferta['cara'].slug}").json()
    assert {"titulo": "Salón Los Álamos", "slug": "salon-los-alamos"} in r[
        "salones_del_anfitrion"
    ]


def test_una_cabana_no_tiene_ficha_de_salon(cliente, evento, oferta):  # noqa: F811
    assert cliente.get(f"/api/v1/salones/ficha/{oferta['cara'].slug}").status_code == 404


def test_un_salon_sin_precio_no_muestra_ese_espacio(cliente, db, evento):  # noqa: F811
    db.add(Unidad(publicacion_id=evento["publicacion"].id, nombre="Galpón", capacidad=300))
    db.commit()
    f = cliente.get(f"/api/v1/salones/ficha/{evento['publicacion'].slug}").json()
    assert [e["nombre"] for e in f["espacios"]] == ["Salón"]


def test_con_dia_la_agenda_se_consulta_una_sola_vez(db, evento):  # noqa: F811
    """El endpoint es público: el costo no puede crecer con la cantidad de salones."""
    from sqlalchemy import event

    from app.models import FranjaHoraria, Publicacion

    base = evento["publicacion"]
    for i in range(4):
        otra = Publicacion(
            prestador_id=base.prestador_id, tipo_servicio_id=base.tipo_servicio_id,
            titulo=f"Salón {i}", slug=f"salon-extra-{i}", descripcion="x",
            estado=base.estado, localidad_id=base.localidad_id, ubicacion=base.ubicacion,
        )
        db.add(otra)
        db.flush()
        u = Unidad(publicacion_id=otra.id, nombre="Salón", capacidad=100)
        db.add(u)
        db.flush()
        db.add(FranjaHoraria(unidad_id=u.id, nombre="Noche", hora_inicio=time(21),
                             hora_fin=time(5), precio=Decimal(1000)))
    db.flush()

    consultas: list[str] = []

    def contar(conn, cursor, sql, *a):
        if "bloqueo_horario" in sql:
            consultas.append(sql)

    conexion = db.connection()
    event.listen(conexion, "before_cursor_execute", contar)
    try:
        pagina = svc.buscar(db, dia=DIA)
    finally:
        event.remove(conexion, "before_cursor_execute", contar)
    assert pagina.total == 5
    assert len(consultas) == 1
