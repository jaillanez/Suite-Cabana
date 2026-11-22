"""Motor de precios de salones (docs/04 §4): reglas puras, sin base."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app.services import precios_eventos as pe

SABADO = date(2027, 3, 13)  # weekday() == 5
assert SABADO.weekday() == 5
SALON = pe.Salon(capacidad=120, capacidad_base=80, cargo_persona_extra=Decimal(5000))
NOCHE = pe.Franja(
    id="n", nombre="Noche", hora_inicio=time(21), hora_fin=time(5),
    precio=Decimal(400000), precios_dia_semana={"5": 550000},
)
MANANA = pe.Franja(
    id="m", nombre="Mañana", hora_inicio=time(9), hora_fin=time(14), precio=Decimal(150000)
)
HORAS = pe.TarifaHoras(
    precio_hora=Decimal(40000),
    hora_apertura=time(10),
    hora_cierre=time(2),
    horas_minimas=3,
    recargo_nocturno_desde=time(0),
    recargo_nocturno_porcentaje=Decimal(20),
)


def _h(dia: date, hora: int) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, tzinfo=pe.ZONA)


# --- Franjas ---


def test_la_franja_toma_el_precio_del_dia_del_evento():
    viernes = SABADO - timedelta(days=1)
    assert pe.por_franja(SALON, NOCHE, viernes, 50, []).subtotal == Decimal("400000.00")
    assert pe.por_franja(SALON, NOCHE, SABADO, 50, []).subtotal == Decimal("550000.00")


def test_la_noche_termina_al_dia_siguiente():
    p = pe.por_franja(SALON, NOCHE, SABADO, 50, [])
    assert p.inicio == _h(SABADO, 21)
    assert p.fin == _h(SABADO + timedelta(days=1), 5)
    assert p.horas == 8


def test_una_franja_de_dia_no_cruza():
    p = pe.por_franja(SALON, MANANA, SABADO, 50, [])
    assert (p.inicio, p.fin) == (_h(SABADO, 9), _h(SABADO, 14))


# --- Por horas ---


def test_por_horas_cobra_precio_por_hora():
    p = pe.por_horas(SALON, HORAS, SABADO, time(15), 3, 40, [])
    assert p.alquiler == Decimal("120000.00")
    assert (p.inicio, p.fin) == (_h(SABADO, 15), _h(SABADO, 18))
    assert p.lineas == []


def test_menos_del_minimo_no_se_puede():
    with pytest.raises(pe.EventoNoDisponible, match="mínimo es de 3"):
        pe.por_horas(SALON, HORAS, SABADO, time(15), 2, 40, [])


def test_antes_de_abrir_no_se_puede():
    with pytest.raises(pe.EventoNoDisponible, match="horario de atención"):
        pe.por_horas(SALON, HORAS, SABADO, time(8), 3, 40, [])


def test_se_puede_pasar_la_medianoche_hasta_el_cierre():
    p = pe.por_horas(SALON, HORAS, SABADO, time(23), 3, 40, [])
    assert p.fin == _h(SABADO + timedelta(days=1), 2)


def test_pasarse_del_cierre_no_se_puede():
    with pytest.raises(pe.EventoNoDisponible, match="cierra a las 02:00"):
        pe.por_horas(SALON, HORAS, SABADO, time(23), 4, 40, [])


def test_la_una_de_la_manana_es_del_dia_siguiente():
    """Atiende de 10 a 2: pedir "1:00" del sábado es la madrugada del domingo."""
    tarifa = pe.TarifaHoras(
        precio_hora=Decimal(1000), hora_apertura=time(10), hora_cierre=time(4), horas_minimas=1
    )
    p = pe.por_horas(SALON, tarifa, SABADO, time(1), 2, 10, [])
    assert p.inicio == _h(SABADO + timedelta(days=1), 1)


def test_el_recargo_nocturno_solo_va_en_las_horas_nocturnas():
    # 22 a 01: la hora que empieza a las 0 lleva recargo; 22 y 23, no.
    p = pe.por_horas(SALON, HORAS, SABADO, time(22), 3, 40, [])
    assert p.alquiler == Decimal("120000.00")
    assert len(p.lineas) == 1
    assert p.lineas[0].monto == Decimal("8000.00")  # 20 % de una hora
    assert "1 h" in p.lineas[0].concepto


def test_el_inicio_va_en_punto_o_y_media():
    pe.por_horas(SALON, HORAS, SABADO, time(15, 30), 3, 40, [])
    with pytest.raises(pe.EventoNoDisponible, match="en punto"):
        pe.por_horas(SALON, HORAS, SABADO, time(15, 15), 3, 40, [])


# --- Invitados y adicionales ---


def test_invitados_sobre_la_base_pagan_extra_una_vez():
    p = pe.por_franja(SALON, MANANA, SABADO, 90, [])
    assert p.subtotal == Decimal("150000") + Decimal(5000) * 10


def test_mas_invitados_que_la_capacidad_no():
    with pytest.raises(pe.EventoNoDisponible, match="hasta 120"):
        pe.por_franja(SALON, MANANA, SABADO, 121, [])


def test_adicionales_por_evento_y_por_persona():
    vajilla = pe.Adicional(id="v", nombre="Vajilla", precio=Decimal(800), por_persona=True)
    sonido = pe.Adicional(id="s", nombre="Sonido", precio=Decimal(60000))
    p = pe.por_franja(SALON, MANANA, SABADO, 50, [vajilla, sonido])
    assert p.subtotal == Decimal("150000") + Decimal(800) * 50 + Decimal(60000)
    assert all(isinstance(ln.monto, Decimal) for ln in p.lineas)


def test_lo_ocupado_incluye_la_preparacion():
    salon = pe.Salon(capacidad=100, preparacion_minutos=90)
    p = pe.por_franja(salon, MANANA, SABADO, 50, [])
    assert pe.rango_ocupado(p, salon) == (_h(SABADO, 9), _h(SABADO, 15) + timedelta(minutes=30))


def test_el_desglose_es_serializable_y_cuadra():
    p = pe.por_horas(SALON, HORAS, SABADO, time(22), 3, 90, [])
    d = p.desglose()
    assert d["modo"] == "horario" and d["invitados"] == 90
    assert Decimal(d["subtotal"]) == Decimal(d["alquiler"]) + sum(
        Decimal(x["monto"]) for x in d["lineas"]
    )
