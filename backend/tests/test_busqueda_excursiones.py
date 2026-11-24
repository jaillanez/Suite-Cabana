"""Excursiones, etapa 4 (docs/05): buscar, ver la ficha y la venta cruzada con
los alojamientos de la zona."""

from datetime import timedelta

from app.models import PrecioPasajero
from app.models.enums import EstadoPublicacion, OrigenBloqueo
from app.services import salidas
from tests.test_excursiones import JUEVES, MARTES, _proximo, excursion  # noqa: F401
from tests.test_reservas_excursion import precios  # noqa: F401  (fixture)

BUSCAR = "/api/v1/excursiones/buscar"


def _titulos(r) -> list[str]:
    assert r.status_code == 200, r.text
    return [x["titulo"] for x in r.json()["resultados"]]


def test_sin_fecha_aparece_con_su_proxima_salida_y_precio_desde(cliente, precios):  # noqa: F811
    r = cliente.get(BUSCAR, params={"localidad": "bariloche"})
    assert _titulos(r) == ["Cabalgata al Dique"]
    x = r.json()["resultados"][0]
    # "Desde" es el adulto: el bebé gratis no es el precio de la excursión.
    assert (x["precio_desde"]["monto"], x["precio_desde"]["detalle"]) == ("30000.00", "por persona")
    assert x["proxima_salida"] is not None
    assert x["maximo_por_reserva"] == 8


def test_con_fecha_solo_las_que_salen_ese_dia_con_lugar(cliente, db, precios):  # noqa: F811
    martes = _proximo(MARTES)
    assert _titulos(cliente.get(BUSCAR, params={"fecha": martes.isoformat()})) == [
        "Cabalgata al Dique"
    ]
    # Un lunes no sale.
    lunes = martes - timedelta(days=1)
    assert _titulos(cliente.get(BUSCAR, params={"fecha": lunes.isoformat()})) == []

    # Con 8 lugares tomados, para 3 personas ya no hay; para 2 sí.
    salida = salidas.materializar(db, precios["turno"], martes)
    salidas.tomar(db, salida, 8, OrigenBloqueo.EXTERNA)
    db.flush()
    params = {"fecha": martes.isoformat()}
    assert _titulos(cliente.get(BUSCAR, params={**params, "personas": 3})) == []
    assert _titulos(cliente.get(BUSCAR, params={**params, "personas": 2})) == [
        "Cabalgata al Dique"
    ]


def test_mas_personas_que_el_maximo_por_reserva_no_aparece(cliente, precios):  # noqa: F811
    assert _titulos(cliente.get(BUSCAR, params={"personas": 9})) == []


def test_sin_precios_no_aparece(cliente, db, precios):  # noqa: F811
    for c in db.query(PrecioPasajero).all():
        c.activo = False
    db.flush()
    assert _titulos(cliente.get(BUSCAR)) == []


def test_una_fecha_pasada_o_lejana_se_rechaza(cliente, precios):  # noqa: F811
    ayer = salidas.hoy() - timedelta(days=1)
    assert cliente.get(BUSCAR, params={"fecha": ayer.isoformat()}).status_code == 422
    lejos = salidas.hoy() + timedelta(days=400)
    assert cliente.get(BUSCAR, params={"fecha": lejos.isoformat()}).status_code == 422


def test_los_destinos_cuentan_solo_excursiones(cliente, precios):  # noqa: F811
    d = cliente.get("/api/v1/excursiones/destinos").json()
    assert [(x["slug"], x["excursiones"]) for x in d] == [("bariloche", 1)]


def test_la_ficha_muestra_actividades_precios_turnos_y_reglas(cliente, precios):  # noqa: F811
    r = cliente.get("/api/v1/excursiones/ficha/cabalgata-al-dique")
    assert r.status_code == 200, r.text
    f = r.json()
    (actividad,) = f["actividades"]
    assert [p["nombre"] for p in actividad["precios"]] == ["Adulto", "Menor", "Bebé en brazos"]
    assert actividad["turnos"][0]["dias_semana"] == [MARTES, JUEVES]
    assert actividad["turnos"][0]["hora_inicio"] == "09:00"
    assert f["reintegro_si_no_sale"] == 100
    # El anfitrión también tiene cabañas: se ofrecen.
    assert {a["slug"] for a in f["alojamientos_del_anfitrion"]} >= {"caro"}


def test_una_excursion_sin_aprobar_no_tiene_ficha(cliente, precios):  # noqa: F811
    precios["publicacion"].estado = EstadoPublicacion.BORRADOR
    assert cliente.get("/api/v1/excursiones/ficha/cabalgata-al-dique").status_code == 404
    assert _titulos(cliente.get(BUSCAR)) == []


def test_la_ficha_de_un_alojamiento_no_abre_como_excursion(cliente, oferta):
    assert cliente.get("/api/v1/excursiones/ficha/caro").status_code == 404


def test_la_ficha_del_alojamiento_ofrece_las_excursiones_de_la_zona(cliente, precios):  # noqa: F811
    r = cliente.get("/api/v1/publicaciones/caro")
    assert r.status_code == 200, r.text
    assert r.json()["excursiones_cerca"] == [
        {"titulo": "Cabalgata al Dique", "slug": "cabalgata-al-dique"}
    ]


def _clonar(db, precios, n):  # noqa: F811
    """n excursiones más como la del fixture, cada una con su turno y su precio."""
    from datetime import time
    from decimal import Decimal

    from app.models import Publicacion, Unidad

    base = precios["publicacion"]
    for i in range(n):
        p = Publicacion(
            prestador_id=base.prestador_id, tipo_servicio_id=base.tipo_servicio_id,
            titulo=f"Trekking {i}", slug=f"trekking-{i}", descripcion="x",
            estado=EstadoPublicacion.APROBADA, localidad_id=base.localidad_id,
        )
        db.add(p)
        db.flush()
        u = Unidad(publicacion_id=p.id, nombre="Trekking", capacidad=8)
        db.add(u)
        db.flush()
        db.add(PrecioPasajero(unidad_id=u.id, nombre="Adulto", precio=Decimal(1000)))
        salidas.crear_turno(
            db, u, nombre="Mañana", dias_semana=[MARTES], hora_inicio=time(9),
            duracion_minutos=60, cupo=10,
        )
    db.flush()


def _consultas(db, cliente, params) -> int:
    from sqlalchemy import event

    cuenta = [0]

    def contar(*_):
        cuenta[0] += 1

    motor = db.get_bind()
    event.listen(motor, "before_cursor_execute", contar)
    try:
        assert cliente.get(BUSCAR, params=params).status_code == 200
    finally:
        event.remove(motor, "before_cursor_execute", contar)
    return cuenta[0]


def test_la_busqueda_no_hace_mas_consultas_por_cada_excursion(cliente, db, precios):  # noqa: F811
    """Con cientos de candidatas, dos consultas por actividad tiraban la base."""
    con_dia = {"fecha": _proximo(MARTES).isoformat()}
    pocas_con, pocas_sin = _consultas(db, cliente, con_dia), _consultas(db, cliente, {})
    _clonar(db, precios, 6)
    assert len(_titulos(cliente.get(BUSCAR, params=con_dia))) == 7
    assert _consultas(db, cliente, con_dia) == pocas_con
    assert _consultas(db, cliente, {}) == pocas_sin
