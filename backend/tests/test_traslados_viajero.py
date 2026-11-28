"""Traslados, etapa 4 (docs/06): el viajero busca, ve la ficha, compara vehículos
para su viaje y lo ofrecemos desde la ficha de un alojamiento."""

from datetime import datetime, timedelta
from decimal import Decimal

from app.models import Publicacion, TarifaTraslado, TramoTraslado, Unidad
from app.models.enums import EstadoPublicacion, OrigenBloqueo
from app.services import horarios
from app.services.precios_eventos import ZONA
from tests.test_traslados import traslado  # noqa: F401  (fixture)

BUSCAR = "/api/v1/traslados/buscar"


def _titulos(r) -> list[str]:
    assert r.status_code == 200, r.text
    return [x["titulo"] for x in r.json()["resultados"]]


def _en(dias: int, hora: int) -> datetime:
    d = datetime.now(ZONA).date() + timedelta(days=dias)
    return datetime(d.year, d.month, d.day, hora, tzinfo=ZONA)


# --- Buscar ---


def test_aparece_con_sus_recorridos_y_precio_desde(cliente, traslado):  # noqa: F811
    r = cliente.get(BUSCAR, params={"localidad": "bariloche"})
    assert _titulos(r) == ["Traslados del Lago"]
    x = r.json()["resultados"][0]
    assert (x["precio_desde"]["monto"], x["precio_desde"]["detalle"]) == ("25000.00", "por viaje")
    assert x["recorridos"] == ["Aeropuerto ↔ Centro"]
    assert (x["pasajeros_maximo"], x["valijas_maximo"], x["por_km"]) == (4, 3, True)


def test_solo_si_entran_los_pasajeros_y_las_valijas(cliente, traslado):  # noqa: F811
    assert _titulos(cliente.get(BUSCAR, params={"pasajeros": 4, "valijas": 3})) != []
    assert _titulos(cliente.get(BUSCAR, params={"pasajeros": 5})) == []
    assert _titulos(cliente.get(BUSCAR, params={"valijas": 4})) == []


def test_buscar_por_un_lugar(cliente, traslado):  # noqa: F811
    assert _titulos(cliente.get(BUSCAR, params={"lugar": "aeropu"})) == ["Traslados del Lago"]
    assert _titulos(cliente.get(BUSCAR, params={"lugar": "terminal"})) == []
    # Un comodín del viajero se busca como texto.
    assert _titulos(cliente.get(BUSCAR, params={"lugar": "%"})) == []


def test_sin_forma_de_cobrar_no_aparece(cliente, db, traslado):  # noqa: F811
    traslado["tramo"].activo = False
    traslado["tarifa"].precio_km = None
    db.flush()
    assert _titulos(cliente.get(BUSCAR)) == []


def test_solo_por_km_el_desde_es_el_minimo(cliente, db, traslado):  # noqa: F811
    traslado["tramo"].activo = False
    db.flush()
    x = cliente.get(BUSCAR).json()["resultados"][0]
    assert (x["precio_desde"]["monto"], x["precio_desde"]["detalle"]) == (
        "10000.00", "por viaje (mínimo)",
    )


def test_un_borrador_no_aparece_ni_tiene_ficha(cliente, traslado):  # noqa: F811
    traslado["publicacion"].estado = EstadoPublicacion.BORRADOR
    assert _titulos(cliente.get(BUSCAR)) == []
    assert cliente.get("/api/v1/traslados/ficha/traslados-del-lago").status_code == 404


def test_los_destinos_cuentan_solo_traslados(cliente, traslado):  # noqa: F811
    d = cliente.get("/api/v1/traslados/destinos").json()
    assert [(x["slug"], x["traslados"]) for x in d] == [("bariloche", 1)]


def _clonar(db, t, n):  # noqa: F811
    base = t["publicacion"]
    for i in range(n):
        p = Publicacion(
            prestador_id=base.prestador_id, tipo_servicio_id=base.tipo_servicio_id,
            titulo=f"Remises {i}", slug=f"remises-{i}", descripcion="x",
            estado=EstadoPublicacion.APROBADA, localidad_id=base.localidad_id,
        )
        db.add(p)
        db.flush()
        u = Unidad(publicacion_id=p.id, nombre="Auto", capacidad=4)
        db.add(u)
        db.flush()
        db.add(TarifaTraslado(unidad_id=u.id, precio_km=Decimal(800), minimo=Decimal(5000)))
        db.add(
            TramoTraslado(
                unidad_id=u.id, origen_id=t["aeropuerto"].id, destino_id=t["centro"].id,
                precio=Decimal(20000), duracion_minutos=30,
            )
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


def test_la_busqueda_no_hace_mas_consultas_por_cada_traslado(cliente, db, traslado):  # noqa: F811
    pocas = _consultas(db, cliente, {})
    _clonar(db, traslado, 6)
    assert len(_titulos(cliente.get(BUSCAR))) == 7
    assert _consultas(db, cliente, {}) == pocas


# --- Ficha ---


def test_la_ficha_muestra_lugares_vehiculos_y_reglas(cliente, traslado):  # noqa: F811
    r = cliente.get("/api/v1/traslados/ficha/traslados-del-lago")
    assert r.status_code == 200, r.text
    f = r.json()
    # Solo el nombre de cada lugar: el punto de la base puede ser la casa del prestador.
    assert f["lugares"] == [
        {"id": str(traslado["aeropuerto"].id), "nombre": "Aeropuerto"},
        {"id": str(traslado["centro"].id), "nombre": "Centro"},
    ]
    (v,) = f["vehiculos"]
    assert (v["nombre"], v["pasajeros"], v["valijas"]) == ("Auto", 4, 3)
    assert v["recorridos"][0]["origen"] == "Aeropuerto"
    assert v["por_km"]["precio_km"] == "900.00" and v["por_km"]["radio_km"] == 50
    assert v["recargo_nocturno"] == {"desde": "22:00", "hasta": "06:00", "porcentaje": "20.00"}


def test_un_alojamiento_no_abre_como_traslado(cliente, oferta):
    assert cliente.get("/api/v1/traslados/ficha/caro").status_code == 404


def test_la_ficha_del_alojamiento_ofrece_los_traslados_de_la_zona(cliente, traslado):  # noqa: F811
    r = cliente.get("/api/v1/publicaciones/caro")
    assert r.status_code == 200, r.text
    assert r.json()["traslados_cerca"] == [
        {"titulo": "Traslados del Lago", "slug": "traslados-del-lago"}
    ]


# --- Opciones para un viaje ---


def _combi(db, t):  # noqa: F811
    """Una combi de 12 que solo cobra por km, más cara que el auto por tramo."""
    combi = Unidad(publicacion_id=t["publicacion"].id, nombre="Combi", capacidad=12)
    db.add(combi)
    db.flush()
    db.add(TarifaTraslado(unidad_id=combi.id, precio_km=Decimal(3000), minimo=Decimal(40000)))
    db.flush()
    return combi


def _viaje(t, pasajeros=3, **kw) -> dict:  # noqa: F811
    return {
        "publicacion_id": str(t["publicacion"].id),
        "origen": {"lugar_id": str(t["aeropuerto"].id)},
        "destino": {"lugar_id": str(t["centro"].id)},
        "inicio": _en(3, 14).isoformat(),
        "pasajeros": pasajeros,
        **kw,
    }


def _opciones(cliente, datos) -> list[dict]:
    r = cliente.post("/api/v1/traslados/opciones", json=datos)
    assert r.status_code == 200, r.text
    return r.json()


def test_opciones_del_mas_barato_al_mas_caro(cliente, db, traslado):  # noqa: F811
    _combi(db, traslado)
    o = _opciones(cliente, _viaje(traslado))
    assert [(x["nombre"], x["disponible"]) for x in o] == [("Auto", True), ("Combi", True)]
    assert Decimal(o[0]["cotizacion"]["total"]) == Decimal(25000)
    assert o[1]["cotizacion"]["viajes"][0]["cobro"] == "km"


def test_si_no_entran_dice_por_que(cliente, db, traslado):  # noqa: F811
    _combi(db, traslado)
    o = _opciones(cliente, _viaje(traslado, pasajeros=6))
    assert [(x["nombre"], x["disponible"]) for x in o] == [("Combi", True), ("Auto", False)]
    assert o[1]["motivo"] == "En este vehículo entran hasta 4 pasajeros"
    assert o[1]["cotizacion"] is None


def test_un_vehiculo_ocupado_no_se_ofrece_como_libre(cliente, db, traslado):  # noqa: F811
    horarios.bloquear(db, traslado["auto"], _en(3, 14), _en(3, 15), OrigenBloqueo.MANUAL)
    db.flush()
    (auto,) = _opciones(cliente, _viaje(traslado))
    assert (auto["disponible"], auto["motivo"]) == (False, "Ya tiene un viaje a esa hora")
    # Igual se muestra cuánto saldría: puede probar otra hora.
    assert auto["cotizacion"] is not None


def test_la_vuelta_ocupada_tambien_cuenta(cliente, db, traslado):  # noqa: F811
    horarios.bloquear(db, traslado["auto"], _en(6, 18), _en(6, 20), OrigenBloqueo.MANUAL)
    db.flush()
    (auto,) = _opciones(cliente, _viaje(traslado, vuelta_inicio=_en(6, 18).isoformat()))
    assert auto["disponible"] is False


def test_opciones_de_un_traslado_sin_aprobar_es_404(cliente, traslado):  # noqa: F811
    traslado["publicacion"].estado = EstadoPublicacion.PAUSADA
    r = cliente.post("/api/v1/traslados/opciones", json=_viaje(traslado))
    assert r.status_code == 404


def test_un_recorrido_a_un_lugar_quitado_no_se_ofrece(cliente, db, traslado):  # noqa: F811
    """La reserva rechaza un lugar dado de baja: la ficha y la búsqueda no lo ofrecen."""
    traslado["centro"].activo = False
    db.flush()
    (v,) = cliente.get("/api/v1/traslados/ficha/traslados-del-lago").json()["vehiculos"]
    assert v["recorridos"] == []
    x = cliente.get(BUSCAR).json()["resultados"][0]
    assert x["recorridos"] == [] and x["precio_desde"]["detalle"] == "por viaje (mínimo)"
