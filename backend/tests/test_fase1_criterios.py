"""Criterios de aceptación de la Fase 1 (docs/01 §5) que no tenían un test que
fallara al romperlos. Salieron de la revisión por mutación de noviembre 2026."""

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range

from app.models import BloqueoFecha, Pago
from app.models.enums import EstadoReserva, OrigenBloqueo
from app.services import busqueda, reservas
from app.services.pagos import MercadoPago
from app.services.pagos.base import EstadoPago, NotificacionInvalida
from tests.conftest import HOY, LLEGADA, SALIDA
from tests.test_api_reservas import notificar
from tests.test_api_reservas import reservar as reservar_api
from tests.test_api_reservas import viajero as viajero_api  # noqa: F401  (fixture)
from tests.test_reservas import reservar, unidad, viajero  # noqa: F401  (fixtures)

# --- R3: lo bloqueado en otra plataforma no se reserva acá ---


@pytest.mark.parametrize("origen", [OrigenBloqueo.ICAL, OrigenBloqueo.EXTERNA])
def test_una_fecha_tomada_en_otra_plataforma_no_se_reserva(db, viajero, unidad, origen):  # noqa: F811
    """Lo que trajo el calendario de Airbnb o Booking (iCal), o una venta cargada a
    mano (Despegar, WhatsApp), ocupa la noche igual que una reserva nuestra."""
    db.add(
        BloqueoFecha(
            unidad_id=unidad.id, rango=Range(LLEGADA, SALIDA, bounds="[)"), origen=origen
        )
    )
    db.flush()
    with pytest.raises(reservas.FechasTomadas):
        reservar(db, viajero, unidad)
    # Y la búsqueda tampoco la ofrece.
    filtros = busqueda.Filtros(
        fecha_inicio=LLEGADA, fecha_fin=SALIDA, personas=2, localidad="bariloche"
    )
    assert all(r.unidad.id != unidad.id for r in busqueda.buscar(db, filtros, hoy=HOY).resultados)


# --- R6: cada pago guarda lo del prestador, la comisión y su IVA ---


def _montos(pago: Pago) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return pago.monto, pago.monto_prestador, pago.monto_comision, pago.iva_comision


def test_el_pago_guarda_lo_del_prestador_la_comision_y_el_iva(cliente, db, viajero_api, oferta):  # noqa: F811
    """El circuito de la web: se pide el cobro (ahí se guarda el pago) y la
    pasarela lo confirma."""
    reserva = reservar_api(cliente, viajero_api, oferta).json()
    codigo = reserva["codigo"]
    pago = cliente.post(f"/api/v1/reservas/{codigo}/pagar", headers=viajero_api, json={}).json()
    notificar(cliente, pago["id_externo"], codigo, total=reserva["total"])

    r = reservas.traer(db, codigo)
    assert r.estado is EstadoReserva.CONFIRMADA
    (fila,) = db.scalars(select(Pago).where(Pago.reserva_id == r.id)).all()
    (item,) = r.items
    c = item.comision
    assert c.comision_neta > 0 and c.iva > 0
    # La comisión de la prueba la paga el prestador: del total, lo suyo más la
    # comisión más el IVA de la comisión.
    assert _montos(fila) == (
        r.total, item.subtotal - c.descuento_prestador, c.comision_neta, c.iva
    )
    assert fila.monto_prestador + fila.monto_comision + fila.iva_comision == fila.monto


def test_un_pago_sin_cobro_pedido_antes_guarda_lo_mismo(db, viajero, unidad):  # noqa: F811
    """Si la pasarela avisa de un pago que no se pidió desde la web, el pago se
    crea al recibir el aviso, con los mismos montos."""
    r = reservar(db, viajero, unidad)
    reservas.registrar_pago(db, r, "pago-x", "simulada", EstadoPago.APROBADO, monto=r.total)
    (fila,) = db.scalars(select(Pago).where(Pago.reserva_id == r.id)).all()
    (item,) = r.items
    c = item.comision
    assert _montos(fila) == (
        r.total, item.subtotal - c.descuento_prestador, c.comision_neta, c.iva
    )


# --- R6: la firma de Mercado Pago ---

SECRETO = "secreto-de-prueba"


def _firmar(id_pago: str, peticion: str = "req-1", ts: str = "1700000000",
            secreto: str = SECRETO) -> dict[str, str]:
    plantilla = f"id:{id_pago};request-id:{peticion};ts:{ts};"
    v1 = hmac.new(secreto.encode(), plantilla.encode(), hashlib.sha256).hexdigest()
    return {"x-signature": f"ts={ts},v1={v1}", "x-request-id": peticion}


def _cuerpo(id_pago: str) -> bytes:
    return json.dumps({"type": "payment", "data": {"id": id_pago}}).encode()


def test_la_firma_de_mercado_pago_se_verifica():
    mp = MercadoPago(token="TEST-x", secreto_webhook=SECRETO)
    assert mp._firma_valida(_cuerpo("123"), _firmar("123"))
    # Firmada para otro pago, con otro secreto, o sin firma: no.
    assert not mp._firma_valida(_cuerpo("124"), _firmar("123"))
    assert not mp._firma_valida(_cuerpo("123"), _firmar("123", secreto="otro"))
    assert not mp._firma_valida(_cuerpo("123"), {})
    # Sin secreto configurado no se puede verificar: se rechaza, no se confía.
    assert not MercadoPago(token="TEST-x", secreto_webhook="")._firma_valida(
        _cuerpo("123"), _firmar("123", secreto="")
    )


def test_una_notificacion_mal_firmada_no_llega_a_consultar_el_pago(monkeypatch):
    """Rechazada antes de ir a la red: una notificación falsa nunca da una reserva
    por pagada."""
    mp = MercadoPago(token="TEST-x", secreto_webhook=SECRETO)
    monkeypatch.setattr(mp, "consultar", lambda *_: pytest.fail("consultó un pago sin firma"))
    with pytest.raises(NotificacionInvalida):
        mp.leer_notificacion(_cuerpo("123"), _firmar("123", secreto="falso"))
