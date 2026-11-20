from datetime import date
from decimal import Decimal as D

import pytest

from app.services.precios import (
    MotivoNoDisponible,
    NoDisponible,
    Tarifa,
    Unidad,
    calcular,
    tarifa_de_la_noche,
)

BASE = Tarifa(precio_noche=D("60000"))
UNIDAD = Unidad(capacidad=4)


def test_precio_simple_por_noches():
    p = calcular(UNIDAD, [BASE], date(2026, 10, 12), date(2026, 10, 15))
    assert p.cantidad_noches == 3
    assert p.alojamiento == D("180000.00")
    assert p.subtotal == D("180000.00")
    assert p.promedio_noche == D("60000.00")


def test_rango_invalido():
    with pytest.raises(NoDisponible) as e:
        calcular(UNIDAD, [BASE], date(2026, 10, 12), date(2026, 10, 12))
    assert e.value.motivo is MotivoNoDisponible.RANGO_INVALIDO


def test_capacidad_insuficiente():
    with pytest.raises(NoDisponible) as e:
        calcular(UNIDAD, [BASE], date(2026, 10, 12), date(2026, 10, 15), personas=6)
    assert e.value.motivo is MotivoNoDisponible.CAPACIDAD_INSUFICIENTE


def test_sin_tarifa_para_alguna_noche():
    temporada = Tarifa(
        precio_noche=D("90000"), fecha_desde=date(2026, 10, 1), fecha_hasta=date(2026, 10, 13)
    )
    with pytest.raises(NoDisponible) as e:
        calcular(UNIDAD, [temporada], date(2026, 10, 12), date(2026, 10, 15))
    assert e.value.motivo is MotivoNoDisponible.SIN_TARIFA


def test_temporada_gana_por_prioridad():
    alta = Tarifa(
        precio_noche=D("95000"),
        fecha_desde=date(2026, 12, 15),
        fecha_hasta=date(2027, 2, 28),
        prioridad=10,
    )
    p = calcular(UNIDAD, [BASE, alta], date(2026, 12, 20), date(2026, 12, 22))
    assert p.alojamiento == D("190000.00")


def test_a_igual_prioridad_gana_la_de_temporada():
    temporada = Tarifa(
        precio_noche=D("95000"), fecha_desde=date(2026, 12, 15), fecha_hasta=date(2027, 2, 28)
    )
    elegida = tarifa_de_la_noche([BASE, temporada], date(2026, 12, 20))
    assert elegida is temporada


def test_precio_por_dia_de_semana_sobrescribe():
    # 2026-10-16 es viernes (weekday 4), 2026-10-17 sábado (5).
    findes = Tarifa(precio_noche=D("60000"), precios_dia_semana={"4": "80000", "5": "85000"})
    p = calcular(UNIDAD, [findes], date(2026, 10, 15), date(2026, 10, 18))
    assert [n.precio for n in p.noches] == [D("60000.00"), D("80000.00"), D("85000.00")]
    assert p.alojamiento == D("225000.00")


def test_estadia_minima_y_maxima():
    t = Tarifa(precio_noche=D("60000"), estadia_minima=3, estadia_maxima=10)
    with pytest.raises(NoDisponible) as corta:
        calcular(UNIDAD, [t], date(2026, 10, 12), date(2026, 10, 14))
    assert corta.value.motivo is MotivoNoDisponible.ESTADIA_CORTA
    with pytest.raises(NoDisponible) as larga:
        calcular(UNIDAD, [t], date(2026, 10, 1), date(2026, 10, 15))
    assert larga.value.motivo is MotivoNoDisponible.ESTADIA_LARGA


def test_anticipacion_minima():
    t = Tarifa(precio_noche=D("60000"), anticipacion_minima_dias=5)
    with pytest.raises(NoDisponible) as e:
        calcular(UNIDAD, [t], date(2026, 10, 12), date(2026, 10, 15), hoy=date(2026, 10, 10))
    assert e.value.motivo is MotivoNoDisponible.ANTICIPACION_INSUFICIENTE
    p = calcular(UNIDAD, [t], date(2026, 10, 20), date(2026, 10, 22), hoy=date(2026, 10, 10))
    assert p.cantidad_noches == 2


def test_limpieza_una_vez_y_persona_extra_por_noche():
    u = Unidad(
        capacidad=6,
        capacidad_base=4,
        cargo_limpieza=D("15000"),
        cargo_persona_extra=D("8000"),
    )
    p = calcular(u, [BASE], date(2026, 10, 12), date(2026, 10, 15), personas=6)
    assert p.limpieza == D("15000.00")
    assert p.personas_extra == D("48000.00")  # 2 personas x 8000 x 3 noches
    assert p.subtotal == D("243000.00")


def test_mascota_se_cobra_una_vez_por_estadia():
    u = Unidad(capacidad=4, cargo_mascota=D("12000"))
    p = calcular(u, [BASE], date(2026, 10, 12), date(2026, 10, 15), mascotas=2)
    assert p.mascotas == D("24000.00")


def test_descuento_semanal_solo_sobre_alojamiento():
    u = Unidad(capacidad=4, cargo_limpieza=D("15000"), descuento_semanal=D(10))
    p = calcular(u, [BASE], date(2026, 10, 1), date(2026, 10, 8))
    assert p.alojamiento == D("420000.00")
    assert p.descuento == D("42000.00")
    assert p.subtotal == D("393000.00")  # 420000 - 42000 + 15000


def test_descuento_mensual_desde_28_noches():
    u = Unidad(capacidad=4, descuento_semanal=D(10), descuento_mensual=D(25))
    p = calcular(u, [BASE], date(2026, 10, 1), date(2026, 10, 29))
    assert p.cantidad_noches == 28
    assert p.porcentaje_descuento == D(25)


def test_desglose_es_serializable():
    p = calcular(UNIDAD, [BASE], date(2026, 10, 12), date(2026, 10, 15))
    d = p.desglose()
    assert d["subtotal"] == "180000.00"
    assert len(d["noches"]) == 3
    assert d["noches"][0] == {"fecha": "2026-10-12", "precio": "60000.00"}
