"""Paquete salón + cabañas del mismo anfitrión (docs/04 §5 S11, etapa 6).

Una reserva, varios ítems, un solo pago: o se retiene todo o nada, cada ítem con
su comisión y su política, y el anfitrión aprueba o rechaza el paquete entero.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range

from app.models import (
    BloqueoFecha,
    BloqueoHorario,
    Notificacion,
    PoliticaCancelacion,
    Prestador,
    Publicacion,
    Reserva,
    Unidad,
    Usuario,
)
from app.models.enums import OrigenBloqueo
from app.services import reservas
from tests.test_agenda_salon import anfitrion  # noqa: F401  (fixture)
from tests.test_api_reservas import notificar, viajero  # noqa: F401  (fixture)
from tests.test_api_salones import DIA, _pedido, evento  # noqa: F401  (fixture)
from tests.test_salones import salon  # noqa: F401  (fixture)

NOCHE = {"desde": DIA.isoformat(), "hasta": (DIA + timedelta(days=1)).isoformat()}


def _r(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _cabana(oferta, clave="u_cara", **kw):
    return {"unidad_id": str(oferta[clave].id), **NOCHE, **kw}


def _cotizar(cliente, evento, *alojamientos):  # noqa: F811
    return cliente.post(
        "/api/v1/salones/cotizacion",
        json=_pedido(
            evento, franja_id=str(evento["noche"].id), alojamientos=list(alojamientos)
        ),
    )


def _paquete(cliente, viajero, evento, *alojamientos):  # noqa: F811
    return cliente.post(
        "/api/v1/salones/reservas", headers=viajero,
        json={
            **_pedido(evento, franja_id=str(evento["noche"].id), alojamientos=list(alojamientos)),
            "acepta_terminos": True,
        },
    )


def _pagar_sena(cliente, viajero, reserva):  # noqa: F811
    pago = cliente.post(
        f"/api/v1/reservas/{reserva['codigo']}/pagar", headers=viajero, json={}
    ).json()
    return pago, notificar(cliente, pago["id_externo"], reserva["codigo"], total=pago["total"])


def _salon_libre(cliente, evento) -> bool:  # noqa: F811
    d = cliente.get(
        f"/api/v1/salones/unidades/{evento['unidad'].id}/disponibilidad",
        params={"dia": DIA.isoformat()},
    ).json()
    return {f["nombre"]: f["libre"] for f in d["franjas"]}["Noche"]


# --- Cotizar ---


def test_la_cotizacion_suma_las_cabanas_y_sena_sobre_el_total(cliente, evento, oferta):  # noqa: F811
    solo = _cotizar(cliente, evento).json()
    assert solo["alojamientos"] == []
    assert solo["total"] == solo["total_evento"]

    c = _cotizar(cliente, evento, _cabana(oferta), _cabana(oferta, "u_chica")).json()
    assert [a["unidad"] for a in c["alojamientos"]] == ["Cabaña 1", "Cabaña chica"]
    cabanas = sum(Decimal(a["total"]) for a in c["alojamientos"])
    assert cabanas == Decimal(90000 + 40000)  # una noche cada una, comisión a cargo del anfitrión
    assert Decimal(c["total"]) == Decimal(c["total_evento"]) + cabanas
    # La seña del salón (30 %) es sobre todo el paquete.
    assert Decimal(c["sena"]) == _r(Decimal(c["total"]) * Decimal("0.3"))
    assert Decimal(c["saldo_con_anfitrion"]) == Decimal(c["total"]) - Decimal(c["sena"])


def test_no_se_suma_una_cabana_de_otro_anfitrion(cliente, db, evento, oferta):  # noqa: F811
    otro = Usuario(email="otro@demo.test", nombre="O", apellido="T", es_prestador=True)
    db.add(otro)
    db.flush()
    ajeno = Prestador(usuario_id=otro.id, razon_social="Otro", fecha_alta=DIA - timedelta(days=500))
    db.add(ajeno)
    db.flush()
    oferta["barata"].prestador_id = ajeno.id
    db.commit()
    r = _cotizar(cliente, evento, _cabana(oferta, "u_barata"))
    assert r.status_code == 422
    assert "mismo anfitrión" in r.json()["detail"]


def test_la_estadia_tiene_que_tocar_el_evento(cliente, evento, oferta):  # noqa: F811
    lejos = {"desde": (DIA + timedelta(days=5)).isoformat(),
             "hasta": (DIA + timedelta(days=6)).isoformat()}
    r = _cotizar(cliente, evento, {**_cabana(oferta), **lejos})
    assert r.status_code == 422
    assert "coincidir con el evento" in r.json()["detail"]
    # Llegar la noche anterior y quedarse hasta el día siguiente, sí.
    vispera = {"desde": (DIA - timedelta(days=1)).isoformat(),
               "hasta": (DIA + timedelta(days=1)).isoformat()}
    assert _cotizar(cliente, evento, {**_cabana(oferta), **vispera}).status_code == 200


def test_la_misma_cabana_dos_veces_no(cliente, evento, oferta):  # noqa: F811
    r = _cotizar(cliente, evento, _cabana(oferta), _cabana(oferta))
    assert r.status_code == 422


def test_un_salon_no_se_suma_como_alojamiento(cliente, evento):  # noqa: F811
    r = _cotizar(cliente, evento, {"unidad_id": str(evento["unidad"].id), **NOCHE})
    assert r.status_code == 422
    assert "por noches" in r.json()["detail"]


# --- Reservar: todo o nada ---


def test_reservar_el_paquete_retiene_todo_con_su_comision(cliente, db, viajero, evento, oferta):  # noqa: F811
    r = _paquete(cliente, viajero, evento, _cabana(oferta), _cabana(oferta, "u_chica"))
    assert r.status_code == 201, r.text
    reserva = r.json()
    assert len(reserva["items"]) == 3
    assert reserva["items"][0]["inicio_en"]  # el evento primero
    ficha = reservas.traer(db, reserva["codigo"])
    assert all(i.comision is not None for i in ficha.items)
    assert Decimal(reserva["total"]) == sum(
        (i.subtotal + i.comision.cargo_viajero for i in ficha.items), Decimal(0)
    )
    # Cada ítem con su política: el salón con la de eventos, las cabañas sin.
    politicas = {i.unidad.nombre: i.politica_cancelacion for i in ficha.items}
    assert politicas["Salón"]["codigo"] == "eventos"
    assert politicas["Cabaña 1"] is None
    assert not _salon_libre(cliente, evento)
    ids = [i.id for i in ficha.items]
    fechas = db.scalars(select(BloqueoFecha).where(BloqueoFecha.item_reserva_id.in_(ids))).all()
    assert len(fechas) == 2


def test_si_una_cabana_esta_ocupada_no_se_reserva_nada(cliente, db, viajero, evento, oferta):  # noqa: F811
    db.add(BloqueoFecha(
        unidad_id=oferta["u_chica"].id, rango=Range(DIA, DIA + timedelta(days=1), bounds="[)"),
        origen=OrigenBloqueo.MANUAL, activo=True,
    ))
    db.commit()
    r = _paquete(cliente, viajero, evento, _cabana(oferta), _cabana(oferta, "u_chica"))
    assert r.status_code == 409
    assert "Cabaña chica" in r.json()["detail"]
    assert db.scalar(select(Reserva.id)) is None
    assert _salon_libre(cliente, evento)


def test_si_la_base_rechaza_una_cabana_se_deshace_el_salon(  # noqa: F811
    cliente, db, viajero, evento, oferta, monkeypatch  # noqa: F811
):
    """Otro se adelantó entre el chequeo y la inserción: decide la restricción."""
    db.add(BloqueoFecha(
        unidad_id=oferta["u_chica"].id, rango=Range(DIA, DIA + timedelta(days=1), bounds="[)"),
        origen=OrigenBloqueo.MANUAL, activo=True,
    ))
    db.commit()
    monkeypatch.setattr(reservas, "_libre", lambda *a, **k: True)
    r = _paquete(cliente, viajero, evento, _cabana(oferta), _cabana(oferta, "u_chica"))
    assert r.status_code == 409
    monkeypatch.undo()
    assert db.scalar(select(Reserva.id)) is None
    retenido = select(BloqueoHorario.id).where(BloqueoHorario.item_reserva_id.is_not(None))
    assert db.scalar(retenido) is None
    assert _salon_libre(cliente, evento)


# --- Pagar, confirmar, aprobar ---


def test_la_sena_del_paquete_confirma_todo(cliente, db, viajero, anfitrion, evento, oferta):  # noqa: F811
    reserva = _paquete(cliente, viajero, evento, _cabana(oferta)).json()
    pago, r = _pagar_sena(cliente, viajero, reserva)
    assert Decimal(pago["total"]) == Decimal(reserva["monto_sena"])
    # El salón es a solicitud: el paquete entero espera la respuesta del anfitrión.
    assert r.json()["resultado"] == "pendiente_aprobacion"
    ficha = reservas.traer(db, reserva["codigo"])
    ids = [i.id for i in ficha.items]
    bloqueos = [
        *db.scalars(select(BloqueoFecha).where(BloqueoFecha.item_reserva_id.in_(ids))),
        *db.scalars(select(BloqueoHorario).where(BloqueoHorario.item_reserva_id.in_(ids))),
    ]
    assert len(bloqueos) == 2
    assert all(b.origen is OrigenBloqueo.RESERVA and b.vence_en is None for b in bloqueos)

    r = cliente.post(f"/api/v1/mis-reservas/{reserva['codigo']}/aprobar", headers=anfitrion)
    assert r.json()["estado"] == "confirmada"
    # El aviso al anfitrión nombra todo lo reservado.
    aviso = db.scalar(select(Notificacion).where(Notificacion.evento == "nueva_reserva"))
    assert "Cabaña 1 de Complejo Caro" in aviso.datos["unidad"]


def test_una_parte_a_solicitud_hace_esperar_todo(cliente, db, viajero, evento, oferta):  # noqa: F811
    evento["publicacion"].confirmacion_inmediata = True
    suite = db.scalar(
        select(Unidad).join(Publicacion).where(Publicacion.slug == "solicitud")
    )
    db.commit()
    reserva = _paquete(
        cliente, viajero, evento, {"unidad_id": str(suite.id), **NOCHE}
    ).json()
    _, r = _pagar_sena(cliente, viajero, reserva)
    assert r.json()["resultado"] == "pendiente_aprobacion"

    solo = cliente.post(
        "/api/v1/salones/reservas", headers=viajero,
        json={**_pedido(evento, franja_id=str(evento["manana"].id)), "acepta_terminos": True},
    ).json()
    _, r = _pagar_sena(cliente, viajero, solo)
    assert r.json()["resultado"] == "confirmada"


def test_rechazar_el_paquete_suelta_todo(cliente, db, viajero, anfitrion, evento, oferta):  # noqa: F811
    reserva = _paquete(cliente, viajero, evento, _cabana(oferta)).json()
    _pagar_sena(cliente, viajero, reserva)
    r = cliente.post(
        f"/api/v1/mis-reservas/{reserva['codigo']}/rechazar", headers=anfitrion,
        json={"motivo": "Ese fin de semana no abrimos"},
    )
    assert r.json()["estado"] == "cancelada"
    assert _salon_libre(cliente, evento)
    cabana = select(BloqueoFecha.id).where(BloqueoFecha.unidad_id == oferta["u_cara"].id)
    assert db.scalar(cabana) is None


def test_pago_tardio_sin_lugar_en_una_cabana_no_confirma_nada(  # noqa: F811
    cliente, db, viajero, evento, oferta  # noqa: F811
):
    reserva = _paquete(cliente, viajero, evento, _cabana(oferta)).json()
    # La retención de la cabaña venció y otro tomó esa noche.
    retencion = db.scalar(
        select(BloqueoFecha).where(BloqueoFecha.unidad_id == oferta["u_cara"].id)
    )
    retencion.activo = False
    db.flush()
    db.add(BloqueoFecha(
        unidad_id=oferta["u_cara"].id, rango=Range(DIA, DIA + timedelta(days=1), bounds="[)"),
        origen=OrigenBloqueo.MANUAL, activo=True,
    ))
    db.commit()

    _, r = _pagar_sena(cliente, viajero, reserva)
    assert r.json()["resultado"] == "cancelada"
    ficha = reservas.traer(db, reserva["codigo"])
    assert ficha.pagos[0].estado == reservas.ESTADO_SIN_LUGAR
    assert _salon_libre(cliente, evento)  # el salón no quedó tomado a medias


# --- Cancelar ---


def test_cancelar_el_paquete_reintegra_cada_parte_con_su_politica(  # noqa: F811
    cliente, db, viajero, evento, oferta  # noqa: F811
):
    flexible = PoliticaCancelacion(
        codigo="flexible", nombre="Flexible",
        tramos=[{"dias_antes": 2, "porcentaje_reintegro": 100}],
    )
    db.add(flexible)
    db.flush()
    oferta["cara"].politica_cancelacion_id = flexible.id
    db.commit()

    reserva = _paquete(cliente, viajero, evento, _cabana(oferta)).json()
    _pagar_sena(cliente, viajero, reserva)
    ficha = reservas.traer(db, reserva["codigo"])
    salon_item = next(i for i in ficha.items if i.inicio_en)
    sena = Decimal(reserva["monto_sena"])
    total = Decimal(reserva["total"])
    parte_salon = _r(sena * (salon_item.subtotal + salon_item.comision.cargo_viajero) / total)
    # A 40 días: el salón devuelve el 90 % de su parte, la cabaña el 100 % de la suya.
    esperado = _r(parte_salon * Decimal("0.9")) + (sena - parte_salon)

    vista = cliente.get(f"/api/v1/reservas/{reserva['codigo']}", headers=viajero).json()
    assert Decimal(vista["reintegro_si_cancela"]["monto"]) == esperado
    assert "Salón 90 %" in vista["reintegro_si_cancela"]["motivo"]
    assert "Cabaña 1 100 %" in vista["reintegro_si_cancela"]["motivo"]

    r = cliente.post(
        f"/api/v1/reservas/{reserva['codigo']}/cancelar", headers=viajero,
        json={"motivo": "Se suspendió la fiesta"},
    )
    assert r.status_code == 200
    assert _salon_libre(cliente, evento)


@pytest.mark.parametrize("dias", [20, 5])
def test_el_reintegro_mira_la_fecha_de_cada_parte(db, viajero, evento, oferta, cliente, dias):  # noqa: F811
    """Faltando 20 días el salón devuelve 50 %; faltando 5, nada. La cabaña sin
    política, nada: el total es la parte del salón."""
    reserva = _paquete(cliente, viajero, evento, _cabana(oferta)).json()
    ficha = reservas.traer(db, reserva["codigo"])
    hoy = DIA - timedelta(days=dias)
    porcentaje = 50 if dias == 20 else 0
    base = Decimal(reserva["monto_sena"])  # sin pagar: sobre lo que tendría que pagar
    salon_item = next(i for i in ficha.items if i.inicio_en)
    parte = _r(base * (salon_item.subtotal + salon_item.comision.cargo_viajero)
               / Decimal(reserva["total"]))
    assert reservas.calcular_reintegro(ficha, hoy).monto == _r(parte * porcentaje / 100)


# --- Qué cabañas se pueden sumar ---


def test_las_cabanas_sumables_traen_precio_y_si_estan_libres(cliente, db, evento, oferta):  # noqa: F811
    db.add(BloqueoFecha(
        unidad_id=oferta["u_chica"].id, rango=Range(DIA, DIA + timedelta(days=1), bounds="[)"),
        origen=OrigenBloqueo.MANUAL, activo=True,
    ))
    db.commit()
    r = cliente.get(
        f"/api/v1/salones/unidades/{evento['unidad'].id}/alojamientos", params=NOCHE
    )
    assert r.status_code == 200, r.text
    por_nombre = {(x["publicacion"], x["unidad"]): x for x in r.json()}
    assert ("Sin Aprobar", "Cabaña 1") not in por_nombre
    cara = por_nombre[("Complejo Caro", "Cabaña 1")]
    assert (cara["libre"], Decimal(cara["total"])) == (True, Decimal(90000))
    chica = por_nombre[("Complejo Caro", "Cabaña chica")]
    assert (chica["libre"], chica["total"], chica["motivo"]) == (
        False, None, "Ocupada esas noches"
    )


def test_cabanas_sumables_con_fechas_raras(cliente, evento):  # noqa: F811
    base = f"/api/v1/salones/unidades/{evento['unidad'].id}/alojamientos"
    d = DIA.isoformat()
    assert cliente.get(base, params={"desde": d, "hasta": d}).status_code == 422
    largo = (DIA + timedelta(days=30)).isoformat()
    assert cliente.get(base, params={"desde": d, "hasta": largo}).status_code == 422


def test_cada_item_dice_cuanto_suma(cliente, viajero, evento, oferta):  # noqa: F811
    reserva = _paquete(cliente, viajero, evento, _cabana(oferta)).json()
    assert sum(Decimal(i["total"]) for i in reserva["items"]) == Decimal(reserva["total"])


def test_al_anfitrion_le_queda_lo_de_todo_el_paquete(cliente, viajero, anfitrion, evento, oferta):  # noqa: F811
    _paquete(cliente, viajero, evento, _cabana(oferta))
    r = cliente.get("/api/v1/mis-reservas", headers=anfitrion).json()[0]
    # Comisión del 10 % + IVA a cargo del anfitrión, sobre cada ítem.
    subtotales = sum(Decimal(i["subtotal"]) for i in r["items"])
    assert Decimal(r["comision_prestador"]) == sum(
        Decimal(i["comision"]["descuento_prestador"]) for i in r["items"]
    )
    assert Decimal(r["comision_prestador"]) == _r(subtotales * Decimal("0.1") * Decimal("1.21"))
    assert Decimal(r["neto_prestador"]) == subtotales - Decimal(r["comision_prestador"])


# --- Revisión de seguridad ---


def test_una_cabana_no_se_retiene_por_meses(cliente, evento, oferta):  # noqa: F811
    """Sin tope, un solo pedido tendría seis cabañas tomadas por meses mientras paga."""
    largo = {"desde": DIA.isoformat(), "hasta": (DIA + timedelta(days=15)).isoformat()}
    r = _cotizar(cliente, evento, {**_cabana(oferta), **largo})
    assert r.status_code == 422
    assert "14 noches" in r.json()["detail"]


def test_de_una_cabana_ajena_no_se_dice_el_nombre(cliente, db, evento, oferta):  # noqa: F811
    otro = Usuario(email="ajeno@demo.test", nombre="A", apellido="J", es_prestador=True)
    db.add(otro)
    db.flush()
    ajeno = Prestador(usuario_id=otro.id, razon_social="Ajeno", fecha_alta=DIA - timedelta(days=9))
    db.add(ajeno)
    db.flush()
    oferta["barata"].prestador_id = ajeno.id
    db.commit()
    # Aun repetida (el chequeo de duplicados nombra la unidad), no se nombra.
    r = _cotizar(cliente, evento, _cabana(oferta, "u_barata"), _cabana(oferta, "u_barata"))
    assert r.status_code == 422
    assert "Cabañas Baratas" not in r.text


def test_las_cabanas_sumables_tienen_tope(cliente, db, evento, oferta, monkeypatch):  # noqa: F811
    from app.api.v1 import salones as api_salones

    monkeypatch.setattr(api_salones, "TOPE_SUMABLES", 2)
    r = cliente.get(
        f"/api/v1/salones/unidades/{evento['unidad'].id}/alojamientos", params=NOCHE
    )
    assert r.status_code == 200
    assert len(r.json()) == 2
