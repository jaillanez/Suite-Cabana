from datetime import date, timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range

from app.models import BloqueoFecha, ReglaComision
from app.models.enums import OrigenBloqueo, QuienPaga
from app.services import busqueda
from tests.conftest import HOY, LLEGADA, SALIDA


def filtros(**kw) -> busqueda.Filtros:
    base = dict(fecha_inicio=LLEGADA, fecha_fin=SALIDA, personas=2, localidad="bariloche")
    base.update(kw)
    return busqueda.Filtros(**base)


def titulos(pagina: busqueda.Pagina) -> list[str]:
    return [r.titulo for r in pagina.resultados]


def test_solo_publicaciones_aprobadas(db, oferta):
    r = busqueda.buscar(db, filtros(), hoy=HOY)
    assert "Sin Aprobar" not in titulos(r)


def test_no_muestra_unidades_con_fechas_tomadas(db, oferta):
    """La unidad barata está bloqueada en esas fechas: su ficha no puede aparecer."""
    r = busqueda.buscar(db, filtros(), hoy=HOY)
    assert "Cabañas Baratas" not in titulos(r)
    # Una semana después sí está libre.
    libre = busqueda.buscar(
        db, filtros(fecha_inicio=SALIDA + timedelta(days=7), fecha_fin=SALIDA + timedelta(days=9)),
        hoy=HOY,
    )
    assert "Cabañas Baratas" in titulos(libre)


def test_retencion_vencida_no_bloquea(db, oferta):
    """Una retención de pago vencida ya no ocupa la fecha."""
    db.add(
        BloqueoFecha(
            unidad_id=oferta["u_cara"].id,
            rango=Range(LLEGADA, SALIDA, bounds="[)"),
            origen=OrigenBloqueo.RETENCION,
            activo=True,
            vence_en=date(2026, 9, 1),
        )
    )
    db.flush()
    r = busqueda.buscar(db, filtros(), hoy=HOY)
    assert "Complejo Caro" in titulos(r)


def test_filtra_por_capacidad(db, oferta):
    r = busqueda.buscar(db, filtros(personas=6), hoy=HOY)
    assert titulos(r) == ["Complejo Caro"]
    assert r.resultados[0].unidad.nombre == "Cabaña 1"


def test_muestra_la_unidad_mas_barata_de_la_ficha(db, oferta):
    """El Complejo Caro tiene dos unidades; para 2 personas gana la chica."""
    r = busqueda.buscar(db, filtros(personas=2), hoy=HOY)
    caro = next(x for x in r.resultados if x.titulo == "Complejo Caro")
    assert caro.unidad.nombre == "Cabaña chica"
    assert caro.unidades_disponibles == 2


def test_solo_la_localidad_pedida(db, oferta):
    r = busqueda.buscar(db, filtros(), hoy=HOY)
    assert "Cabañas del Bolsón" not in titulos(r)
    assert r.destino.localidad == "San Carlos de Bariloche"


def test_destino_desconocido(db, oferta):
    with pytest.raises(busqueda.DestinoDesconocido):
        busqueda.buscar(db, filtros(localidad="villa-inexistente"), hoy=HOY)


def test_filtra_por_comodidades_todas(db, oferta):
    r = busqueda.buscar(db, filtros(comodidades=("wifi", "pileta")), hoy=HOY)
    assert titulos(r) == ["Complejo Caro"]


def test_filtra_por_confirmacion_inmediata(db, oferta):
    r = busqueda.buscar(db, filtros(confirmacion_inmediata=False), hoy=HOY)
    assert titulos(r) == ["Posada A Solicitud"]


def test_orden_por_precio(db, oferta):
    asc = busqueda.buscar(db, filtros(orden=busqueda.Orden.PRECIO_ASC), hoy=HOY)
    desc = busqueda.buscar(db, filtros(orden=busqueda.Orden.PRECIO_DESC), hoy=HOY)
    precios_asc = [r.unidad.precio.total for r in asc.resultados]
    assert precios_asc == sorted(precios_asc)
    assert titulos(desc) == list(reversed(titulos(asc)))


def test_orden_por_distancia(db, oferta):
    r = busqueda.buscar(db, filtros(orden=busqueda.Orden.DISTANCIA), hoy=HOY)
    distancias = [x.distancia_km for x in r.resultados]
    assert distancias == sorted(distancias)
    assert all(d is not None for d in distancias)


def test_relevancia_pone_primero_la_confirmacion_inmediata(db, oferta):
    r = busqueda.buscar(db, filtros(), hoy=HOY)
    assert r.resultados[0].confirmacion_inmediata is True
    assert r.resultados[-1].titulo == "Posada A Solicitud"


def test_filtra_por_rango_de_precio(db, oferta):
    todos = busqueda.buscar(db, filtros(), hoy=HOY)
    mas_caro = max(r.unidad.precio.total for r in todos.resultados)
    r = busqueda.buscar(db, filtros(precio_min=mas_caro), hoy=HOY)
    assert len(r.resultados) == 1


def test_paginado(db, oferta):
    p1 = busqueda.buscar(db, filtros(por_pagina=1, pagina=1), hoy=HOY)
    p2 = busqueda.buscar(db, filtros(por_pagina=1, pagina=2), hoy=HOY)
    assert p1.total == p2.total >= 2
    assert p1.paginas == p1.total
    assert titulos(p1) != titulos(p2)


def test_pagina_fuera_de_rango_devuelve_la_ultima(db, oferta):
    r = busqueda.buscar(db, filtros(por_pagina=1, pagina=999), hoy=HOY)
    assert r.pagina == r.paginas


def test_rango_de_fechas_invalido(db, oferta):
    from app.services import precios

    with pytest.raises(precios.NoDisponible):
        busqueda.buscar(db, filtros(fecha_fin=LLEGADA), hoy=HOY)


def test_busqueda_por_punto_y_radio(db, oferta):
    cerca = busqueda.buscar(
        db, filtros(localidad=None, lat=-41.1335, lon=-71.3103, radio_km=15), hoy=HOY
    )
    assert "Cabañas del Bolsón" not in titulos(cerca)
    assert len(cerca.resultados) >= 1


def test_el_cargo_de_servicio_sigue_la_regla_de_comision(db, oferta):
    """Quién paga la comisión es configuración, no código."""
    regla = db.scalar(select(ReglaComision).where(ReglaComision.es_default))

    regla.quien_paga = QuienPaga.PRESTADOR
    db.flush()
    absorbe = busqueda.buscar(db, filtros(), hoy=HOY).resultados[0]
    assert absorbe.unidad.precio.cargo_servicio == D("0.00")
    assert absorbe.unidad.precio.total == absorbe.unidad.precio.precio.subtotal

    regla.quien_paga = QuienPaga.VIAJERO
    db.flush()
    cobra = busqueda.buscar(db, filtros(), hoy=HOY).resultados[0]
    assert cobra.unidad.precio.cargo_servicio > 0
    assert cobra.unidad.precio.total == (
        cobra.unidad.precio.precio.subtotal + cobra.unidad.precio.cargo_servicio
    )

    regla.porcentaje = D(0)
    db.flush()
    sin_comision = busqueda.buscar(db, filtros(), hoy=HOY).resultados[0]
    assert sin_comision.unidad.precio.cargo_servicio == D("0.00")


def test_el_total_siempre_es_la_suma_del_desglose(db, oferta):
    for r in busqueda.buscar(db, filtros(), hoy=HOY).resultados:
        p = r.unidad.precio.precio
        assert p.subtotal == (
            p.alojamiento - p.descuento + p.limpieza + p.personas_extra + p.mascotas
        )
        assert r.unidad.precio.total == p.subtotal + r.unidad.precio.cargo_servicio


# --- Explorar sin fechas (docs/01 §5 R4) ---
#
# Quien entra a buscar y todavía no sabe cuándo viaja tiene que ver que existe
# oferta. Mandarlo a una pantalla en blanco hasta que cargue un calendario es
# perderlo antes de que vea nada.


def test_explorar_muestra_lo_publicado_sin_pedir_fechas(cliente, oferta):
    r = cliente.get("/api/v1/publicaciones/explorar")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["total"] >= 3
    titulos = {p["titulo"] for p in cuerpo["publicaciones"]}
    assert "Cabañas Baratas" in titulos
    assert "Complejo Caro" in titulos


def test_explorar_no_muestra_lo_que_no_esta_aprobado(cliente, oferta):
    titulos = {
        p["titulo"] for p in cliente.get("/api/v1/publicaciones/explorar").json()["publicaciones"]
    }
    assert "Sin Aprobar" not in titulos


def test_explorar_da_la_tarifa_base_y_nunca_un_total(cliente, oferta):
    """Sin fechas no hay estadía: un total sería un número inventado."""
    p = next(
        x
        for x in cliente.get("/api/v1/publicaciones/explorar").json()["publicaciones"]
        if x["titulo"] == "Cabañas Baratas"
    )
    assert p["tarifa_desde"] == "50000.00"
    assert "total" not in p


def test_explorar_ordena_por_cercania_cuando_sabe_donde_esta_el_visitante(cliente, oferta):
    # Parado en El Bolsón: lo de El Bolsón tiene que venir primero.
    cuerpo = cliente.get("/api/v1/publicaciones/explorar?lat=-41.9667&lon=-71.5333").json()
    assert cuerpo["origen"] == [-41.9667, -71.5333]
    assert cuerpo["publicaciones"][0]["titulo"] == "Cabañas del Bolsón"


def test_explorar_pone_adelante_las_que_tienen_foto(cliente, db, oferta):
    """Una ficha sin foto encabezando el sitio es la peor primera impresión."""
    from sqlalchemy import delete

    from app.models import Foto

    # Le sacamos la foto a la primera alfabética: tiene que caer al final.
    antes = cliente.get("/api/v1/publicaciones/explorar").json()["publicaciones"]
    encabezaba = antes[0]["titulo"]
    db.execute(delete(Foto).where(Foto.publicacion_id == antes[0]["publicacion_id"]))
    db.commit()
    # La colección ya estaba cargada en la sesión: sin esto el endpoint sigue
    # viendo la foto que acabamos de borrar.
    db.expire_all()

    cuerpo = cliente.get("/api/v1/publicaciones/explorar").json()
    despues = [p["titulo"] for p in cuerpo["publicaciones"]]
    assert despues[0] != encabezaba
    assert despues[-1] == encabezaba


def test_explorar_filtra_por_destino_y_por_gente(cliente, oferta):
    solo_bolson = cliente.get("/api/v1/publicaciones/explorar?localidad=el-bolson").json()
    assert {p["titulo"] for p in solo_bolson["publicaciones"]} == {"Cabañas del Bolsón"}

    para_seis = cliente.get("/api/v1/publicaciones/explorar?personas=6").json()
    assert "Cabañas Baratas" not in {p["titulo"] for p in para_seis["publicaciones"]}
    assert "Complejo Caro" in {p["titulo"] for p in para_seis["publicaciones"]}


def test_explorar_pagina(cliente, oferta):
    cuerpo = cliente.get("/api/v1/publicaciones/explorar?por_pagina=2").json()
    assert len(cuerpo["publicaciones"]) == 2
    assert cuerpo["paginas"] >= 2
    segunda = cliente.get("/api/v1/publicaciones/explorar?por_pagina=2&pagina=2").json()
    primeros = {p["publicacion_id"] for p in cuerpo["publicaciones"]}
    assert not (primeros & {p["publicacion_id"] for p in segunda["publicaciones"]})
