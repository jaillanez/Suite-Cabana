from datetime import timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from app.models import Tarifa
from app.services import precios
from app.services import publicaciones as fichas
from tests.conftest import HOY, LLEGADA, SALIDA


def test_ficha_sin_fechas_no_inventa_precio(db, oferta):
    """Sin fechas no se sabe qué está libre ni cuánto sale: se muestra la tarifa base."""
    f = fichas.obtener(db, "caro", hoy=HOY)
    assert f.noches is None
    assert len(f.unidades) == 2
    for u in f.unidades:
        assert u.disponible is None
        assert u.precio is None
        assert u.tarifa_base is not None


def test_ficha_con_fechas_calcula_precio_por_unidad(db, oferta):
    f = fichas.obtener(db, "caro", desde=LLEGADA, hasta=SALIDA, personas=2, hoy=HOY)
    assert f.noches == 3
    disponibles = [u for u in f.unidades if u.disponible]
    assert len(disponibles) == 2
    chica = next(u for u in f.unidades if u.nombre == "Cabaña chica")
    assert chica.precio is not None
    assert chica.precio.precio.cantidad_noches == 3
    assert chica.precio.total == D("120000.00")  # 3 noches x 40000, sin cargos


def test_unidad_ocupada_dice_por_que(db, oferta):
    """La unidad barata está bloqueada justo en esas fechas."""
    f = fichas.obtener(db, "baratas", desde=LLEGADA, hasta=SALIDA, hoy=HOY)
    unidad = f.unidades[0]
    assert unidad.disponible is False
    assert "reservada" in unidad.motivo.lower()
    assert unidad.precio is None


def test_unidad_que_no_entra_la_gente_dice_por_que(db, oferta):
    f = fichas.obtener(db, "caro", desde=LLEGADA, hasta=SALIDA, personas=6, hoy=HOY)
    chica = next(u for u in f.unidades if u.nombre == "Cabaña chica")
    assert chica.disponible is False
    assert chica.motivo == precios.MENSAJES[precios.MotivoNoDisponible.CAPACIDAD_INSUFICIENTE]
    grande = next(u for u in f.unidades if u.nombre == "Cabaña 1")
    assert grande.disponible is True


def test_la_ficha_trae_todo_lo_que_la_pantalla_necesita(db, oferta):
    f = fichas.obtener(db, "caro", hoy=HOY)
    p = f.publicacion
    assert p.titulo == "Complejo Caro"
    assert p.localidad.nombre == "San Carlos de Bariloche"
    assert p.localidad.provincia.nombre == "Río Negro"
    assert p.prestador.razon_social == "Prestador de prueba"
    assert {c.codigo for c in p.comodidades} == {"wifi", "pileta"}
    assert len(p.fotos) == 1
    assert f.lat is not None and f.lon is not None


def test_publicacion_inexistente(db, oferta):
    with pytest.raises(fichas.NoEncontrada):
        fichas.obtener(db, "no-existe", hoy=HOY)


def test_publicacion_no_aprobada_no_tiene_ficha(db, oferta):
    """Un borrador no es visible ni entrando por la URL directa."""
    with pytest.raises(fichas.NoEncontrada):
        fichas.obtener(db, "sin-aprobar", hoy=HOY)


def test_rango_de_fechas_invalido(db, oferta):
    with pytest.raises(precios.NoDisponible):
        fichas.obtener(db, "caro", desde=SALIDA, hasta=LLEGADA, hoy=HOY)


def test_listado_por_destino_no_depende_de_fechas(db, oferta):
    p = fichas.listar_por_destino(db, "bariloche")
    assert p.total == 3  # baratas, caro y solicitud; el borrador no cuenta
    assert p.localidad.nombre == "San Carlos de Bariloche"
    titulos = [r.publicacion.titulo for r in p.publicaciones]
    assert "Sin Aprobar" not in titulos
    assert "Cabañas del Bolsón" not in titulos


def test_listado_por_destino_trae_capacidad_y_tarifa_minima(db, oferta):
    p = fichas.listar_por_destino(db, "bariloche")
    caro = next(r for r in p.publicaciones if r.publicacion.titulo == "Complejo Caro")
    assert caro.capacidad_maxima == 6
    assert caro.tarifa_desde == D("40000.00")  # la unidad chica


def test_listado_por_destino_pagina(db, oferta):
    p1 = fichas.listar_por_destino(db, "bariloche", pagina=1, por_pagina=2)
    p2 = fichas.listar_por_destino(db, "bariloche", pagina=2, por_pagina=2)
    assert p1.paginas == 2
    assert len(p1.publicaciones) == 2
    assert len(p2.publicaciones) == 1
    assert {r.publicacion.id for r in p1.publicaciones} & {
        r.publicacion.id for r in p2.publicaciones
    } == set()


def test_destino_inexistente(db, oferta):
    with pytest.raises(fichas.NoEncontrada):
        fichas.listar_por_destino(db, "narnia")


def test_destinos_con_oferta_ordena_por_cantidad(db, oferta):
    destinos = fichas.destinos_con_oferta(db)
    nombres = [loc.nombre for loc, _, _ in destinos]
    assert nombres[0] == "San Carlos de Bariloche"
    assert "El Bolsón" in nombres
    cantidades = [n for _, _, n in destinos]
    assert cantidades == sorted(cantidades, reverse=True)


def test_estadia_minima_se_respeta_en_la_ficha(db, oferta):
    """Una noche sola cuando la tarifa pide más: la ficha lo dice, no lo esconde."""
    tarifa = db.scalar(select(Tarifa).where(Tarifa.unidad_id == oferta["u_cara"].id))
    tarifa.estadia_minima = 4
    db.flush()
    f = fichas.obtener(db, "caro", desde=LLEGADA, hasta=LLEGADA + timedelta(days=1), hoy=HOY)
    grande = next(u for u in f.unidades if u.nombre == "Cabaña 1")
    assert grande.disponible is False
    assert grande.motivo == precios.MENSAJES[precios.MotivoNoDisponible.ESTADIA_CORTA]


def test_la_ficha_dice_el_maximo_de_noches(db, oferta):
    """Sin máximo propio, el de la plataforma; con uno, el de la unidad."""
    tarifa = db.scalar(select(Tarifa).where(Tarifa.unidad_id == oferta["u_cara"].id))
    f = fichas.obtener(db, "caro", hoy=HOY)
    assert next(u for u in f.unidades if u.nombre == "Cabaña 1").estadia_maxima == 365
    tarifa.estadia_maxima = 14
    db.flush()
    f = fichas.obtener(db, "caro", hoy=HOY)
    assert next(u for u in f.unidades if u.nombre == "Cabaña 1").estadia_maxima == 14
