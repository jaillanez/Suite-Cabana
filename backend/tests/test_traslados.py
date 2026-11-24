"""Traslados, etapa 1 (docs/06): precio por tramo o por km, recargo nocturno,
capacidad, anticipación y que dos viajes del mismo vehículo no se pisen."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    LugarTraslado,
    Publicacion,
    SubtipoServicio,
    TarifaTraslado,
    TipoServicio,
    TramoTraslado,
    Unidad,
)
from app.models.enums import EstadoPublicacion, ModoReserva, OrigenBloqueo
from app.services import precios_traslado as pt
from app.services import traslados
from app.services.precios_eventos import ZONA

AEROPUERTO = (-41.1512, -71.1578)
CENTRO = (-41.1335, -71.3103)
BASE = (-41.1400, -71.3000)
AHORA = datetime(2027, 3, 1, 10, 0, tzinfo=ZONA)


def _punto(lat, lon) -> str:
    return f"SRID=4326;POINT({lon} {lat})"


def _a_las(hora: int, minuto: int = 0, dias: int = 2) -> datetime:
    d = AHORA.date() + timedelta(days=dias)
    return datetime(d.year, d.month, d.day, hora, minuto, tzinfo=ZONA)


@pytest.fixture
def traslado(db, oferta) -> dict:
    """Un auto para 4 con 3 valijas, el tramo Aeropuerto ↔ Centro y tarifa por km."""
    tipo = TipoServicio(codigo="traslado", nombre="Traslado", modo_reserva=ModoReserva.TRAMO)
    db.add(tipo)
    db.flush()
    subtipo = SubtipoServicio(
        tipo_id=tipo.id, codigo="traslado_aeropuerto", nombre="Aeropuerto y terminal"
    )
    db.add(subtipo)
    db.flush()
    cara = oferta["cara"]
    publicacion = Publicacion(
        prestador_id=oferta["prestador"].id, tipo_servicio_id=tipo.id,
        subtipo_servicio_id=subtipo.id, titulo="Traslados del Lago", slug="traslados-del-lago",
        descripcion="Traslados al aeropuerto.", estado=EstadoPublicacion.APROBADA,
        localidad_id=cara.localidad_id, ubicacion=_punto(*CENTRO),
    )
    db.add(publicacion)
    db.flush()
    auto = Unidad(
        publicacion_id=publicacion.id, nombre="Auto", capacidad=4, equipaje=3,
        preparacion_minutos=10,
    )
    db.add(auto)
    db.flush()
    aeropuerto = LugarTraslado(
        publicacion_id=publicacion.id, nombre="Aeropuerto", ubicacion=_punto(*AEROPUERTO)
    )
    centro = LugarTraslado(
        publicacion_id=publicacion.id, nombre="Centro", ubicacion=_punto(*CENTRO)
    )
    db.add_all([aeropuerto, centro])
    db.flush()
    tramo = TramoTraslado(
        unidad_id=auto.id, origen_id=aeropuerto.id, destino_id=centro.id,
        precio=Decimal(25000), duracion_minutos=30,
    )
    tarifa = TarifaTraslado(
        unidad_id=auto.id, precio_km=Decimal(900), bajada=Decimal(2000),
        minimo=Decimal(10000), radio_km=50, recargo_nocturno_desde=time(22),
        recargo_nocturno_hasta=time(6), recargo_nocturno_porcentaje=Decimal(20),
    )
    db.add_all([tramo, tarifa])
    db.flush()
    return {
        "publicacion": publicacion, "auto": auto, "aeropuerto": aeropuerto,
        "centro": centro, "tramo": tramo, "tarifa": tarifa,
    }


# --- Cuenta pura ---


AUTO = pt.Vehiculo(pasajeros=4, valijas=3, preparacion_minutos=10)
TRAMO = pt.Tramo(precio=Decimal(25000), duracion_minutos=30)


def test_la_distancia_en_linea_recta():
    km = pt.distancia_km(pt.Punto(*AEROPUERTO), pt.Punto(*CENTRO))
    assert 12.5 < km < 13.5


def test_por_tramo_el_vehiculo_queda_ocupado_hasta_que_vuelve_y_se_prepara():
    p = pt.por_tramo(TRAMO, AUTO, pt.Reglas(), _a_las(14), AHORA, pasajeros=3)
    assert p.subtotal == Decimal(25000)
    assert p.llegada == _a_las(14, 30)
    assert p.ocupado_hasta == _a_las(15, 10)  # 30 de vuelta + 10 de preparación


def test_si_no_vuelve_a_la_base_solo_cuenta_el_viaje():
    p = pt.por_tramo(TRAMO, AUTO, pt.Reglas(vuelve_a_base=False), _a_las(14), AHORA, 1)
    assert p.ocupado_hasta == _a_las(14, 40)


def test_por_persona_multiplica_por_los_pasajeros():
    tramo = pt.Tramo(precio=Decimal(8000), duracion_minutos=30, por_persona=True)
    assert pt.por_tramo(tramo, AUTO, pt.Reglas(), _a_las(14), AHORA, 3).subtotal == Decimal(
        24000
    )


@pytest.mark.parametrize(
    ("hora", "minuto", "recargo"),
    [(23, 30, True), (5, 0, True), (6, 0, False), (21, 59, False), (22, 0, True)],
)
def test_el_recargo_nocturno_cruza_la_medianoche(hora, minuto, recargo):
    reglas = pt.Reglas(
        recargo_nocturno_desde=time(22), recargo_nocturno_hasta=time(6),
        recargo_nocturno_porcentaje=Decimal(20),
    )
    p = pt.por_tramo(TRAMO, AUTO, reglas, _a_las(hora, minuto), AHORA, 2)
    assert p.subtotal == (Decimal(30000) if recargo else Decimal(25000))
    assert (len(p.lineas) == 2) is recargo


def test_por_km_con_bajada_factor_de_ruta_y_minimo():
    reglas = pt.Reglas(precio_km=Decimal(900), bajada=Decimal(2000), minimo=Decimal(10000))
    p = pt.por_km(
        pt.Punto(*AEROPUERTO), pt.Punto(*CENTRO), None, AUTO, reglas, _a_las(14), AHORA, 2
    )
    # ~12,9 km en línea recta × 1,3 = ~16,8 km.
    assert Decimal("16.5") < p.km < Decimal("17.2")
    assert p.subtotal == (Decimal(2000) + p.km * 900).quantize(Decimal("0.01"))
    assert p.llegada - p.inicio == timedelta(minutes=20)  # 16,8 km a 60 km/h, de a 5 min

    corto = pt.por_km(
        pt.Punto(*CENTRO), pt.Punto(*BASE), None, AUTO, reglas, _a_las(14), AHORA, 1
    )
    assert corto.subtotal == Decimal(10000)  # rige el mínimo
    assert corto.llegada - corto.inicio == timedelta(minutes=15)  # nunca menos de 15


@pytest.mark.parametrize(
    ("cambios", "mensaje"),
    [
        ({"pasajeros": 5}, "hasta 4 pasajeros"),
        ({"pasajeros": 0}, "al menos una persona"),
        ({"valijas": 4}, "hasta 3 valijas"),
        ({"inicio": AHORA + timedelta(hours=11)}, "12 h de anticipación"),
        ({"inicio": AHORA + timedelta(days=400)}, "12 meses"),
    ],
)
def test_lo_que_no_se_puede_cotizar(cambios, mensaje):
    datos = {"pasajeros": 2, "valijas": 1, "inicio": _a_las(14), **cambios}
    with pytest.raises(pt.TrasladoInvalido, match=mensaje):
        pt.por_tramo(
            TRAMO, AUTO, pt.Reglas(), datos["inicio"], AHORA, datos["pasajeros"],
            datos["valijas"],
        )


def test_sin_limite_de_valijas_entra_cualquier_cantidad():
    sin_limite = pt.Vehiculo(pasajeros=4)
    assert pt.por_tramo(TRAMO, sin_limite, pt.Reglas(), _a_las(14), AHORA, 2, 9).subtotal


def test_por_km_fuera_del_radio_o_sin_tarifa_no_va():
    reglas = pt.Reglas(precio_km=Decimal(900), radio_km=5)
    with pytest.raises(pt.TrasladoInvalido, match="hasta 5 km de su base"):
        pt.por_km(
            pt.Punto(*CENTRO), pt.Punto(*AEROPUERTO), pt.Punto(*BASE), AUTO, reglas,
            _a_las(14), AHORA, 2,
        )
    with pytest.raises(pt.TrasladoInvalido, match="no cobra por kilómetro"):
        pt.por_km(
            pt.Punto(*CENTRO), pt.Punto(*AEROPUERTO), None, AUTO, pt.Reglas(), _a_las(14),
            AHORA, 2,
        )


# --- Con la base ---


def test_el_tramo_vale_a_la_vuelta_si_es_de_los_dos_sentidos(db, traslado):
    t = traslado
    ida = traslados.tramo_entre(db, t["auto"], t["aeropuerto"].id, t["centro"].id)
    vuelta = traslados.tramo_entre(db, t["auto"], t["centro"].id, t["aeropuerto"].id)
    assert ida.id == vuelta.id == t["tramo"].id

    t["tramo"].ambos_sentidos = False
    db.flush()
    assert traslados.tramo_entre(db, t["auto"], t["centro"].id, t["aeropuerto"].id) is None


def test_el_tramo_del_sentido_pedido_gana_sobre_el_inverso(db, traslado):
    t = traslado
    vuelta = TramoTraslado(
        unidad_id=t["auto"].id, origen_id=t["centro"].id, destino_id=t["aeropuerto"].id,
        precio=Decimal(20000), duracion_minutos=30,
    )
    db.add(vuelta)
    db.flush()
    assert traslados.tramo_entre(db, t["auto"], t["centro"].id, t["aeropuerto"].id).id == (
        vuelta.id
    )


def test_cotizar_un_recorrido_que_no_hace(db, traslado):
    otro = LugarTraslado(
        publicacion_id=traslado["publicacion"].id, nombre="Cerro", ubicacion=_punto(*BASE)
    )
    db.add(otro)
    db.flush()
    with pytest.raises(pt.TrasladoInvalido, match="no hace ese recorrido"):
        traslados.cotizar_tramo(
            db, traslado["auto"], otro.id, traslado["centro"].id, _a_las(14), 2, ahora=AHORA
        )


def test_la_tarifa_del_vehiculo_se_aplica(db, traslado):
    t = traslado
    p = traslados.cotizar_tramo(
        db, t["auto"], t["aeropuerto"].id, t["centro"].id, _a_las(23), 2, ahora=AHORA
    )
    assert p.subtotal == Decimal(30000)  # con el 20 % nocturno de su tarifa


def test_el_radio_se_mide_desde_la_base(db, traslado):
    t = traslado
    t["tarifa"].radio_km = 5
    db.flush()
    # Sin lugar base, la base es la publicación (en el centro): el aeropuerto queda lejos.
    with pytest.raises(pt.TrasladoInvalido, match="hasta 5 km"):
        traslados.cotizar_km(
            db, t["auto"], pt.Punto(*CENTRO), pt.Punto(*AEROPUERTO), _a_las(14), 2,
            ahora=AHORA,
        )
    # Con la base en el aeropuerto, el centro es el que queda lejos.
    t["aeropuerto"].es_base = True
    db.flush()
    assert traslados.base_de(db, t["auto"]).lat == round(AEROPUERTO[0], 2)  # redondeada


def test_dos_viajes_del_mismo_vehiculo_no_se_pisan(db, traslado):
    t = traslado
    ahora = datetime.now(UTC)
    manana = (ahora + timedelta(days=2)).astimezone(ZONA).date()

    def a_las(h, m=0):
        return datetime(manana.year, manana.month, manana.day, h, m, tzinfo=ZONA)

    def viaje(h, m=0):
        return traslados.cotizar_tramo(
            db, t["auto"], t["aeropuerto"].id, t["centro"].id, a_las(h, m), 2
        )

    primero = viaje(14)  # ocupado de 14:00 a 15:10
    traslados.ocupar(db, t["auto"], primero, OrigenBloqueo.MANUAL)
    # A las 14:45 el auto todavía está volviendo.
    assert not traslados.libre(db, t["auto"], viaje(14, 45))
    with pytest.raises(traslados.NoDisponible):
        traslados.ocupar(db, t["auto"], viaje(14, 45), OrigenBloqueo.MANUAL)
    # A las 15:10 ya volvió y se preparó.
    assert traslados.libre(db, t["auto"], viaje(15, 10))
    traslados.ocupar(db, t["auto"], viaje(15, 10), OrigenBloqueo.MANUAL)


def test_un_tramo_no_puede_ir_y_volver_al_mismo_lugar(db, traslado):
    t = traslado
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            TramoTraslado(
                unidad_id=t["auto"].id, origen_id=t["centro"].id, destino_id=t["centro"].id,
                precio=Decimal(1000), duracion_minutos=10,
            )
        )
        db.flush()


def test_un_alojamiento_no_es_un_vehiculo(db, traslado, oferta):
    with pytest.raises(pt.TrasladoInvalido, match="no es un vehículo"):
        traslados.cotizar_tramo(
            db, oferta["u_cara"], traslado["aeropuerto"].id, traslado["centro"].id,
            _a_las(14), 2, ahora=AHORA,
        )
