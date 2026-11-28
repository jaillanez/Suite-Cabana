"""Comisiones por tipo y subtipo de servicio (docs/00 §7, docs/02): el motor
elige la regla de cada servicio sin cambios estructurales, el operador las
administra con historial, y nadie más las ve."""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import crear_token
from app.models import ComisionAplicada, ReglaComision, Usuario
from app.models.enums import QuienPaga
from app.services import comisiones as motor
from app.services import reservas
from app.services import reservas_traslado as rt
from tests.test_excursiones import excursion  # noqa: F401  (fixture de precios)
from tests.test_reservas_excursion import _reservar as reservar_excursion
from tests.test_reservas_excursion import precios, viajero  # noqa: F401  (fixtures)
from tests.test_salones import salon  # noqa: F401  (fixture)
from tests.test_traslados import AHORA, _a_las, traslado  # noqa: F401  (fixture)

HOY = date(2027, 3, 1)


# --- El motor ---


def _regla(nombre, creada, **kw) -> motor.Regla:
    return motor.Regla(id=uuid4(), nombre=nombre, creada_en=creada, **kw)


def test_el_subtipo_gana_al_tipo_aunque_el_tipo_sea_mas_nuevo():
    """"Cabalgatas" es más específica que "Excursiones": antes valían lo mismo y
    ganaba la última creada."""
    tipo, sub = uuid4(), uuid4()
    reglas = [
        _regla("General", datetime(2026, 1, 1), porcentaje=Decimal(10)),
        _regla("Cabalgatas", datetime(2026, 2, 1), subtipo_servicio_id=sub,
               porcentaje=Decimal(12)),
        _regla("Excursiones", datetime(2026, 3, 1), tipo_servicio_id=tipo,
               porcentaje=Decimal(15)),
    ]
    ctx = motor.ContextoComision(
        monto=Decimal(1000), fecha_servicio=HOY, fecha_creacion=HOY,
        tipo_servicio_id=tipo, subtipo_servicio_id=sub,
    )
    assert motor.elegir_regla(reglas, ctx)[0].nombre == "Cabalgatas"
    # Otra excursión (no cabalgata) se queda con la del tipo.
    otra = motor.ContextoComision(
        monto=Decimal(1000), fecha_servicio=HOY, fecha_creacion=HOY,
        tipo_servicio_id=tipo, subtipo_servicio_id=uuid4(),
    )
    assert motor.elegir_regla(reglas, otra)[0].nombre == "Excursiones"


def test_la_localidad_gana_a_la_provincia():
    prov, loc = uuid4(), uuid4()
    reglas = [
        _regla("General", datetime(2026, 1, 1)),
        _regla("Bariloche", datetime(2026, 2, 1), localidad_id=loc),
        _regla("Río Negro", datetime(2026, 3, 1), provincia_id=prov),
    ]
    ctx = motor.ContextoComision(
        monto=Decimal(1000), fecha_servicio=HOY, fecha_creacion=HOY,
        provincia_id=prov, localidad_id=loc,
    )
    assert motor.elegir_regla(reglas, ctx)[0].nombre == "Bariloche"


# --- Cada servicio con su regla, de punta a punta ---


def _regla_bd(db, nombre, porcentaje, **kw) -> ReglaComision:
    r = ReglaComision(nombre=nombre, porcentaje=Decimal(porcentaje), **kw)
    db.add(r)
    db.flush()
    return r


def test_cada_tipo_de_servicio_resuelve_su_regla(db, oferta, salon, precios, traslado):  # noqa: F811
    """Alojamiento, salón, excursión y traslado pasan por el mismo motor."""
    publicaciones = {
        "alojamiento": oferta["cara"],
        "salon": salon["publicacion"],
        "excursion": precios["publicacion"],
        "traslado": traslado["publicacion"],
    }
    esperado = {}
    for i, (clave, p) in enumerate(publicaciones.items()):
        if clave == "alojamiento":
            continue  # se queda con la general (10 %, conftest)
        esperado[clave] = _regla_bd(
            db, f"Regla {clave}", 11 + i, tipo_servicio_id=p.tipo_servicio_id
        )
    for clave, p in publicaciones.items():
        c = reservas._comision(db, p, Decimal(10000), HOY, HOY)
        nombre = esperado[clave].nombre if clave in esperado else "Comisión general"
        assert c.regla.nombre == nombre, clave


def test_la_excursion_guarda_la_regla_de_su_subtipo(db, viajero, precios):  # noqa: F811
    tipo = precios["publicacion"].tipo_servicio_id
    _regla_bd(db, "Excursiones", 15, tipo_servicio_id=tipo)
    sub = _regla_bd(
        db, "Cabalgatas", 12, subtipo_servicio_id=precios["publicacion"].subtipo_servicio_id
    )
    reserva = reservar_excursion(db, viajero, precios)
    (item,) = reserva.items
    c = db.scalar(select(ComisionAplicada).where(ComisionAplicada.item_reserva_id == item.id))
    assert c.regla_id == sub.id
    assert c.comision_neta == (item.subtotal * Decimal("0.12")).quantize(Decimal("0.01"))


def test_ida_y_vuelta_aplican_la_regla_de_traslados_en_cada_viaje(db, viajero, traslado):  # noqa: F811
    regla = _regla_bd(
        db, "Traslados", 8, tipo_servicio_id=traslado["publicacion"].tipo_servicio_id,
        quien_paga=QuienPaga.VIAJERO,
    )
    pedido = rt.Pedido(
        origen=rt.Extremo(lugar_id=traslado["aeropuerto"].id),
        destino=rt.Extremo(lugar_id=traslado["centro"].id),
        inicio=_a_las(14), pasajeros=2, vuelta_inicio=_a_las(18, dias=5),
    )
    reserva = rt.crear_traslado(db, viajero, traslado["auto"], pedido, ahora=AHORA)
    comisiones = [i.comision for i in reserva.items]
    assert [c.regla_id for c in comisiones] == [regla.id, regla.id]
    # La paga el viajero: el total suma el cargo de los dos viajes.
    cargo = sum((c.cargo_viajero for c in comisiones), Decimal(0))
    assert cargo > 0 and reserva.total == Decimal(50000) + cargo


# --- El panel del operador ---


@pytest.fixture
def operador(db):
    u = Usuario(email="operador@ejemplo.com.ar", nombre="Op", apellido="Era",
                email_verificado=True, es_operador=True)
    db.add(u)
    db.flush()
    return {"Authorization": f"Bearer {crear_token(str(u.id))}"}


def _nueva(salon, **kw) -> dict:  # noqa: F811
    tipo = str(salon["tipo"].id)
    return {"nombre": "Salones", "porcentaje": "12", "tipo_servicio_id": tipo, **kw}


def test_solo_el_operador_ve_y_toca_las_reglas(cliente, db, oferta, salon):  # noqa: F811
    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    anfitrion = {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}
    caso = {"monto": "1000", "fecha_servicio": "2027-03-01"}
    for cabeceras, codigo in (({}, 401), (anfitrion, 403)):
        assert cliente.get("/api/v1/comisiones/reglas", headers=cabeceras).status_code == codigo
        assert cliente.post("/api/v1/comisiones/simular", headers=cabeceras,
                            json=caso).status_code == codigo
        assert cliente.post("/api/v1/comisiones/reglas", headers=cabeceras,
                            json=_nueva(salon)).status_code == codigo


def test_el_operador_crea_una_regla_y_el_simulador_la_aplica(cliente, operador, salon):  # noqa: F811
    r = cliente.post("/api/v1/comisiones/reglas", headers=operador, json=_nueva(salon))
    assert r.status_code == 201, r.text
    assert r.json()["tipo_servicio"] == "Salón de eventos"
    # El simulador deduce el tipo del subtipo: con "Quincho" ya sabe que es salón.
    s = cliente.post(
        "/api/v1/comisiones/simular", headers=operador,
        json={"monto": "100000", "fecha_servicio": "2027-03-01",
              "subtipo_servicio_id": str(salon["subtipo"].id)},
    )
    assert s.status_code == 200, s.text
    assert s.json()["regla_nombre"] == "Salones"
    assert Decimal(s.json()["comision_neta"]) == Decimal(12000)


@pytest.mark.parametrize(
    "cambio, mensaje",
    [
        ({"tipo_servicio_id": None}, "al menos un tipo"),
        ({"subtipo_servicio_id": "ajeno"}, "no es de ese tipo"),
        ({"quien_paga": "dividido"}, "qué parte paga el viajero"),
        ({"minimo": "500", "maximo": "100"}, "máximo no puede ser menor"),
        ({"servicio_desde": "2027-03-10", "servicio_hasta": "2027-03-01"}, "temporada termina"),
    ],
)
def test_reglas_mal_cargadas_se_rechazan(cliente, operador, salon, traslado, cambio, mensaje):  # noqa: F811
    if cambio.get("subtipo_servicio_id") == "ajeno":
        cambio = {"subtipo_servicio_id": str(traslado["publicacion"].subtipo_servicio_id)}
    r = cliente.post("/api/v1/comisiones/reglas", headers=operador, json=_nueva(salon, **cambio))
    assert r.status_code == 422
    assert mensaje in str(r.json()["detail"])


def test_la_general_no_se_desactiva_ni_se_le_pone_tipo(cliente, db, operador, oferta, salon):  # noqa: F811
    general = db.scalar(select(ReglaComision).where(ReglaComision.es_default))
    url = f"/api/v1/comisiones/reglas/{general.id}"
    assert cliente.post(f"{url}/desactivar", headers=operador).status_code == 409
    r = cliente.put(url, headers=operador, json=_nueva(salon, nombre="General"))
    assert r.status_code == 422
    # Sus valores sí se editan.
    r = cliente.put(url, headers=operador,
                    json={"nombre": "Comisión general", "porcentaje": "9"})
    assert r.status_code == 200 and Decimal(r.json()["porcentaje"]) == Decimal(9)


def test_cambiar_una_regla_no_toca_lo_reservado_y_queda_en_el_historial(
    cliente, db, operador, viajero, precios  # noqa: F811
):
    r = cliente.post(
        "/api/v1/comisiones/reglas", headers=operador,
        json={"nombre": "Excursiones", "porcentaje": "15",
              "tipo_servicio_id": str(precios["publicacion"].tipo_servicio_id)},
    )
    regla = r.json()
    reserva = reservar_excursion(db, viajero, precios)
    db.commit()
    (item,) = reserva.items
    antes = item.comision.comision_neta

    url = f"/api/v1/comisiones/reglas/{regla['id']}"
    r = cliente.put(url, headers=operador, json={
        "nombre": "Excursiones", "porcentaje": "20",
        "tipo_servicio_id": str(precios["publicacion"].tipo_servicio_id),
    })
    assert r.status_code == 200 and r.json()["reservas"] == 1
    assert cliente.post(f"{url}/desactivar", headers=operador).json()["activa"] is False

    db.expire_all()
    assert db.get(ComisionAplicada, item.comision.id).comision_neta == antes
    h = cliente.get(f"{url}/historial", headers=operador).json()
    assert [x["accion"] for x in h] == ["baja", "edicion", "alta"]
    assert Decimal(h[1]["antes"]["porcentaje"]) == 15
    assert Decimal(h[1]["despues"]["porcentaje"]) == 20
    assert h[0]["usuario"] == "operador@ejemplo.com.ar"


def test_una_regla_desactivada_ya_no_aplica(cliente, db, operador, salon):  # noqa: F811
    r = cliente.post("/api/v1/comisiones/reglas", headers=operador, json=_nueva(salon)).json()
    cliente.post(f"/api/v1/comisiones/reglas/{r['id']}/desactivar", headers=operador)
    db.expire_all()
    c = reservas._comision(db, salon["publicacion"], Decimal(1000), HOY, HOY)
    assert c.regla.nombre == "Comisión general"
