from datetime import date, datetime
from decimal import Decimal as D
from uuid import uuid4

import pytest

from app.models.enums import QuienPaga
from app.services.comisiones import ContextoComision, Regla, SinReglaAplicable, resolver

IVA = D("0.21")
ALOJ, EXCUR = uuid4(), uuid4()
SAN_JUAN, MENDOZA = uuid4(), uuid4()
PRESTADOR = uuid4()


def regla(nombre, creada=datetime(2026, 1, 1), **kw):
    return Regla(id=uuid4(), nombre=nombre, creada_en=creada, **kw)


def ctx(**kw):
    base = dict(
        monto=D("100000"),
        fecha_servicio=date(2026, 12, 20),
        fecha_creacion=date(2026, 10, 1),
        tipo_servicio_id=ALOJ,
        provincia_id=SAN_JUAN,
        prestador_id=PRESTADOR,
        antiguedad_prestador_meses=12,
    )
    base.update(kw)
    return ContextoComision(**base)


DEFAULT = regla("Default", porcentaje=D(10))


def test_default_aplica_si_no_hay_otra():
    r = resolver([DEFAULT], ctx(), IVA)
    assert r.regla is DEFAULT
    assert r.comision_neta == D("10000.00")
    assert r.iva == D("2100.00")
    assert r.comision_total == D("12100.00")
    assert r.descuento_prestador == D("12100.00")
    assert r.neto_prestador == D("87900.00")


def test_sin_default_falla():
    otra = regla("Solo Mendoza", provincia_id=MENDOZA, porcentaje=D(5))
    with pytest.raises(SinReglaAplicable):
        resolver([otra], ctx(), IVA)


def test_gana_la_mas_especifica():
    prov = regla("San Juan", provincia_id=SAN_JUAN, porcentaje=D(8))
    prov_tipo = regla(
        "San Juan aloj", provincia_id=SAN_JUAN, tipo_servicio_id=ALOJ, porcentaje=D(7), prioridad=-5
    )
    r = resolver([DEFAULT, prov, prov_tipo], ctx(), IVA)
    assert r.regla is prov_tipo


def test_empate_por_prioridad_y_luego_reciente():
    a = regla("A", provincia_id=SAN_JUAN, porcentaje=D(8), prioridad=1)
    b = regla("B", tipo_servicio_id=ALOJ, porcentaje=D(9), prioridad=2)
    assert resolver([DEFAULT, a, b], ctx(), IVA).regla is b

    c = regla("C", provincia_id=SAN_JUAN, porcentaje=D(6), prioridad=2, creada=datetime(2026, 5, 1))
    assert resolver([DEFAULT, a, b, c], ctx(), IVA).regla is c


def test_no_coincide_tipo_de_servicio():
    exc = regla("Excursiones", tipo_servicio_id=EXCUR, porcentaje=D(15))
    assert resolver([DEFAULT, exc], ctx(), IVA).regla is DEFAULT


def test_primeros_3_meses_sin_comision():
    nuevo = regla("Bienvenida", antiguedad_meses_hasta=3, porcentaje=D(0))
    assert resolver([DEFAULT, nuevo], ctx(antiguedad_prestador_meses=2), IVA).regla is nuevo
    assert resolver([DEFAULT, nuevo], ctx(antiguedad_prestador_meses=4), IVA).regla is DEFAULT
    r = resolver([DEFAULT, nuevo], ctx(antiguedad_prestador_meses=2), IVA)
    assert r.comision_total == 0


def test_temporada_y_vigencia():
    verano = regla(
        "Verano",
        servicio_desde=date(2026, 12, 15),
        servicio_hasta=date(2027, 3, 1),
        porcentaje=D(12),
    )
    assert resolver([DEFAULT, verano], ctx(), IVA).regla is verano
    assert resolver([DEFAULT, verano], ctx(fecha_servicio=date(2026, 11, 1)), IVA).regla is DEFAULT

    vencida = regla("Vieja", provincia_id=SAN_JUAN, vigente_hasta=date(2026, 9, 1), porcentaje=D(1))
    assert resolver([DEFAULT, vencida], ctx(), IVA).regla is DEFAULT

    inactiva = regla("Off", provincia_id=SAN_JUAN, activa=False, porcentaje=D(1))
    assert resolver([DEFAULT, inactiva], ctx(), IVA).regla is DEFAULT


def test_minimo_y_maximo():
    r = regla("Min", porcentaje=D(10), minimo=D(5000))
    assert resolver([r], ctx(monto=D(20000)), IVA).comision_neta == D("5000.00")
    r = regla("Max", porcentaje=D(10), maximo=D(8000))
    assert resolver([r], ctx(), IVA).comision_neta == D("8000.00")


def test_iva_incluido():
    r = regla("Incl", porcentaje=D("12.1"), iva_incluido=True)
    res = resolver([r], ctx(), IVA)
    assert res.comision_total == D("12100.00")
    assert res.comision_neta == D("10000.00")
    assert res.iva == D("2100.00")


def test_paga_viajero_y_dividido():
    v = regla("Viajero", porcentaje=D(10), quien_paga=QuienPaga.VIAJERO)
    res = resolver([v], ctx(), IVA)
    assert res.cargo_viajero == D("12100.00")
    assert res.descuento_prestador == 0
    assert res.total_viajero == D("112100.00")
    assert res.neto_prestador == D("100000")

    d = regla(
        "Mitad", porcentaje=D(10), quien_paga=QuienPaga.DIVIDIDO, porcentaje_viajero=D("33.33")
    )
    res = resolver([d], ctx(), IVA)
    assert res.cargo_viajero + res.descuento_prestador == res.comision_total


def test_explicacion_para_simulador():
    exc = regla("Excursiones", tipo_servicio_id=EXCUR, porcentaje=D(15))
    res = resolver([DEFAULT, exc], ctx(), IVA)
    assert any("Excursiones" in e and "✗" in e for e in res.explicacion)
    assert res.explicacion[-1] == "→ Aplica: Default"
