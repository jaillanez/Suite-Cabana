"""Traslados, etapa 3 (docs/06): el prestador publica un traslado y carga sus
vehículos, lugares, tramos, tarifa y reglas; y ve la agenda de cada vehículo."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.security import crear_token
from app.models import Prestador, TipoServicio, Usuario
from app.models.enums import ModoReserva
from app.services import precios_traslado as pt
from app.services import traslados
from tests.test_traslados import AEROPUERTO, AHORA, CENTRO, _a_las, traslado  # noqa: F401

BASE = "/api/v1/mis-publicaciones"


@pytest.fixture
def anfitrion(db, oferta):
    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    return {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}


def _pub(cliente, anfitrion, t):  # noqa: F811
    r = cliente.get(f"{BASE}/{t['publicacion'].id}", headers=anfitrion)
    assert r.status_code == 200, r.text
    return r.json()


def _ok(r, codigo=200):
    assert r.status_code == codigo, r.text
    return r.json()


def _lugar(cliente, anfitrion, t, nombre, punto, **kw):  # noqa: F811
    return cliente.post(
        f"{BASE}/{t['publicacion'].id}/lugares-traslado", headers=anfitrion,
        json={"nombre": nombre, "lat": punto[0], "lon": punto[1], **kw},
    )


def _tramo(cliente, anfitrion, t, origen, destino, **kw):  # noqa: F811
    return cliente.post(
        f"{BASE}/{t['publicacion'].id}/unidades/{t['auto'].id}/tramos-traslado",
        headers=anfitrion,
        json={"origen_id": str(origen), "destino_id": str(destino), "precio": "18000",
              "duracion_minutos": 40, **kw},
    )


# --- Alta ---


def test_se_crea_un_traslado_y_dice_que_le_falta(cliente, db, oferta, anfitrion):
    db.add(TipoServicio(codigo="traslado", nombre="Traslado", modo_reserva=ModoReserva.TRAMO))
    db.flush()
    p = _ok(
        cliente.post(
            BASE, headers=anfitrion,
            json={"titulo": "Traslados del Sol", "localidad_id": str(oferta["cara"].localidad_id),
                  "tipo": "traslado"},
        ),
        201,
    )
    assert p["modo_reserva"] == "tramo"
    assert p["confirmacion_inmediata"] is True
    assert "Falta elegir el tipo de traslado" in p["faltantes"]
    assert "Falta cargar al menos un vehículo" in p["faltantes"]

    # Un micro de 45 pasajeros sí; uno de 90, no. El tope de 30 es de alojamiento.
    url = f"{BASE}/{p['id']}/unidades"
    p = _ok(
        cliente.post(url, headers=anfitrion,
                     json={"nombre": "Combi", "capacidad": 45, "equipaje": 30}),
        201,
    )
    (v,) = p["unidades"]
    assert (v["capacidad"], v["equipaje"], v["tramos_traslado"], v["tarifa_traslado"]) == (
        45, 30, [], None,
    )
    assert "Sin tramos ni precio por km: Combi" in p["faltantes"]
    r = cliente.post(url, headers=anfitrion, json={"nombre": "Micro", "capacidad": 90})
    assert r.status_code == 422


def test_un_alojamiento_no_tiene_lugares_de_traslado(cliente, oferta, anfitrion):
    r = cliente.post(
        f"{BASE}/{oferta['cara'].id}/lugares-traslado", headers=anfitrion,
        json={"nombre": "Aeropuerto", "lat": -41.1, "lon": -71.1},
    )
    assert r.status_code == 409


def test_otro_prestador_no_toca_los_lugares(cliente, db, traslado):  # noqa: F811
    otro = Usuario(email="otro@ejemplo.com.ar", nombre="O", apellido="O", email_verificado=True)
    db.add(otro)
    db.flush()
    db.add(Prestador(usuario_id=otro.id, razon_social="Otro", fecha_alta=date.today()))
    db.flush()
    ajeno = {"Authorization": f"Bearer {crear_token(str(otro.id))}"}
    assert _lugar(cliente, ajeno, traslado, "Terminal", CENTRO).status_code == 404


# --- Lugares ---


def test_los_lugares_tienen_una_sola_base(cliente, anfitrion, traslado):  # noqa: F811
    _ok(_lugar(cliente, anfitrion, traslado, "Terminal", CENTRO, es_base=True), 201)
    p = _ok(_lugar(cliente, anfitrion, traslado, "Garage", AEROPUERTO, es_base=True), 201)
    bases = [x["nombre"] for x in p["lugares_traslado"] if x["es_base"]]
    assert bases == ["Garage"]
    assert p["lugares_traslado"][0]["nombre"] == "Garage"  # la base primero


def test_no_se_repite_un_lugar_aunque_cambie_la_mayuscula(cliente, anfitrion, traslado):  # noqa: F811
    r = _lugar(cliente, anfitrion, traslado, "aeropuerto", AEROPUERTO)
    assert r.status_code == 409


def test_quitar_un_lugar_quita_sus_tramos_y_volver_a_cargarlo_lo_reactiva(
    cliente, db, anfitrion, traslado  # noqa: F811
):
    pid = traslado["publicacion"].id
    aeropuerto = traslado["aeropuerto"]
    p = _ok(cliente.delete(f"{BASE}/{pid}/lugares-traslado/{aeropuerto.id}", headers=anfitrion))
    assert [x["nombre"] for x in p["lugares_traslado"]] == ["Centro"]
    (v,) = p["unidades"]
    assert v["tramos_traslado"] == []

    p = _ok(_lugar(cliente, anfitrion, traslado, "Aeropuerto", AEROPUERTO), 201)
    assert str(aeropuerto.id) in {x["id"] for x in p["lugares_traslado"]}  # el mismo, reactivado


def test_mover_un_lugar_cambia_el_precio_por_km(cliente, db, anfitrion, traslado):  # noqa: F811
    pid, centro = traslado["publicacion"].id, traslado["centro"]
    antes = traslados.punto(db, centro)
    _ok(
        cliente.patch(
            f"{BASE}/{pid}/lugares-traslado/{centro.id}", headers=anfitrion,
            json={"lat": -41.1300, "lon": -71.4000, "nombre": "Centro cívico"},
        )
    )
    db.expire_all()
    despues = traslados.punto(db, centro)
    assert despues != antes and centro.nombre == "Centro cívico"


# --- Tramos ---


def test_un_tramo_se_carga_una_vez_por_sentido(cliente, anfitrion, traslado):  # noqa: F811
    t = traslado
    # El fixture ya tiene Aeropuerto → Centro.
    r = _tramo(cliente, anfitrion, t, t["aeropuerto"].id, t["centro"].id)
    assert r.status_code == 409
    p = _ok(
        _tramo(cliente, anfitrion, t, t["centro"].id, t["aeropuerto"].id, por_persona=True,
               precio="9000"),
        201,
    )
    (v,) = p["unidades"]
    assert [(x["origen"], x["destino"], x["por_persona"]) for x in v["tramos_traslado"]] == [
        ("Aeropuerto", "Centro", False), ("Centro", "Aeropuerto", True),
    ]


def test_un_tramo_quitado_se_vuelve_a_cargar_con_otro_precio(cliente, db, anfitrion, traslado):  # noqa: F811
    t = traslado
    url = f"{BASE}/{t['publicacion'].id}/unidades/{t['auto'].id}/tramos-traslado"
    _ok(cliente.delete(f"{url}/{t['tramo'].id}", headers=anfitrion))
    p = _ok(_tramo(cliente, anfitrion, t, t["aeropuerto"].id, t["centro"].id, precio="31000"), 201)
    (x,) = p["unidades"][0]["tramos_traslado"]
    assert x["id"] == str(t["tramo"].id) and Decimal(x["precio"]) == Decimal(31000)
    # Y la cotización usa el precio nuevo.
    db.expire_all()
    precio = traslados.cotizar_tramo(
        db, t["auto"], t["aeropuerto"].id, t["centro"].id, _a_las(14), 2, ahora=AHORA
    )
    assert precio.subtotal == Decimal(31000)


@pytest.mark.parametrize(
    "caso, codigo",
    [("precio_cero", 422), ("muy_corto", 422), ("mismo_lugar", 422), ("lugar_ajeno", 404)],
)
def test_tramos_mal_cargados_se_rechazan(cliente, anfitrion, traslado, caso, codigo):  # noqa: F811
    import uuid

    t = traslado
    origen, destino, extra = t["centro"].id, t["aeropuerto"].id, {}
    if caso == "precio_cero":
        extra = {"precio": "0"}
    elif caso == "muy_corto":
        extra = {"duracion_minutos": 3}
    elif caso == "mismo_lugar":
        destino = origen
    else:
        destino = uuid.uuid4()
    assert _tramo(cliente, anfitrion, t, origen, destino, **extra).status_code == codigo


# --- Tarifa y reglas ---


def _tarifa(cliente, anfitrion, t, **kw):  # noqa: F811
    return cliente.put(
        f"{BASE}/{t['publicacion'].id}/unidades/{t['auto'].id}/tarifa-traslado",
        headers=anfitrion, json=kw,
    )


def test_la_tarifa_y_las_reglas_mandan_en_la_cotizacion(cliente, db, anfitrion, traslado):  # noqa: F811
    t = traslado
    p = _ok(
        _tarifa(cliente, anfitrion, t, precio_km="1200", bajada="3000", minimo="8000",
                factor_ruta="1.5", vuelve_a_base=False, anticipacion_minima_horas=2)
    )
    tarifa = p["unidades"][0]["tarifa_traslado"]
    assert (Decimal(tarifa["precio_km"]), tarifa["vuelve_a_base"]) == (Decimal(1200), False)
    assert tarifa["recargo_nocturno_desde"] is None  # se reemplaza todo junto

    db.expire_all()
    reglas = traslados.reglas(db, t["auto"])
    assert reglas.anticipacion_minima_horas == 2 and reglas.factor_ruta == Decimal("1.5")
    # Con 2 h de anticipación, a 3 h ya se puede.
    precio = traslados.cotizar_tramo(
        db, t["auto"], t["aeropuerto"].id, t["centro"].id, AHORA + timedelta(hours=3), 1,
        ahora=AHORA,
    )
    assert precio.ocupado_hasta == precio.llegada + timedelta(minutes=10)  # sin vuelta


@pytest.mark.parametrize(
    "datos",
    [
        {"recargo_nocturno_porcentaje": "20"},
        {"recargo_nocturno_porcentaje": "20", "recargo_nocturno_desde": "22:00",
         "recargo_nocturno_hasta": "22:00"},
        {"factor_ruta": "0.8"},
        {"velocidad_kmh": 300},
        {"precio_km": "0"},
    ],
)
def test_reglas_mal_cargadas_se_rechazan(cliente, anfitrion, traslado, datos):  # noqa: F811
    assert _tarifa(cliente, anfitrion, traslado, **datos).status_code == 422


def test_solo_con_tarifa_por_km_ya_se_puede_publicar(cliente, db, anfitrion, traslado):  # noqa: F811
    t = traslado
    url = f"{BASE}/{t['publicacion'].id}/unidades/{t['auto'].id}/tramos-traslado"
    p = _ok(_tarifa(cliente, anfitrion, t))  # sin precio por km
    p = _ok(cliente.delete(f"{url}/{t['tramo'].id}", headers=anfitrion))
    assert "Sin tramos ni precio por km: Auto" in p["faltantes"]
    p = _ok(_tarifa(cliente, anfitrion, t, precio_km="900"))
    assert not any("Sin tramos" in f for f in p["faltantes"])


def test_un_tramo_a_un_lugar_quitado_no_cuenta_como_precio(cliente, db, anfitrion, traslado):  # noqa: F811
    t = traslado
    """Aunque el tramo siga activo: la reserva rechaza un lugar dado de baja, y lo
    que falta para publicar tiene que decir lo mismo."""
    _ok(_tarifa(cliente, anfitrion, t))
    t["centro"].activo = False
    db.commit()
    assert t["tramo"].activo
    assert "Sin tramos ni precio por km: Auto" in _pub(cliente, anfitrion, t)["faltantes"]


# --- Agenda del vehículo ---


def test_la_agenda_del_vehiculo_muestra_viajes_y_acepta_bloqueos(cliente, db, anfitrion, traslado):  # noqa: F811
    t = traslado
    url = f"{BASE}/{t['publicacion'].id}/unidades/{t['auto'].id}"
    manana = date.today() + timedelta(days=1)
    a = _ok(
        cliente.post(
            f"{url}/bloqueos-horarios", headers=anfitrion,
            json={"dia": manana.isoformat(), "hora_desde": "08:00", "hora_hasta": "08:20",
                  "nota": "Service"},
        ),
        201,
    )
    (b,) = a["tramos"]
    assert (b["etiqueta"], b["nota"], b["editable"]) == ("Bloqueado a mano", "Service", True)
    # Un viaje que se pisa con el bloqueo no se puede tomar.
    inicio = datetime.fromisoformat(b["inicio"])
    precio = pt.PrecioTraslado(
        inicio=inicio, llegada=inicio + timedelta(minutes=10),
        ocupado_hasta=inicio + timedelta(minutes=10), km=None,
    )
    assert not traslados.libre(db, t["auto"], precio)
    agenda = _ok(cliente.get(f"{url}/agenda-horaria", headers=anfitrion,
                             params={"desde": manana.isoformat()}))
    assert len(agenda["tramos"]) == 1
