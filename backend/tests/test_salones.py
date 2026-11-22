"""Salones de eventos, etapa 1 (docs/04): disponibilidad por hora sin dobles
reservas, catálogos por tipo de servicio, y que nada de esto se mezcle con los
alojamientos."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    BloqueoHorario,
    Comodidad,
    Publicacion,
    SubtipoServicio,
    Tarifa,
    TipoServicio,
    Unidad,
)
from app.models.enums import EstadoPublicacion, ModoReserva, OrigenBloqueo
from app.services import horarios, reservas
from app.services import publicaciones as fichas
from app.services.horarios import ZONA
from tests.conftest import LLEGADA, SALIDA


@pytest.fixture
def salon(db, oferta) -> dict:
    """Un salón aprobado, del mismo anfitrión y en la misma localidad que las cabañas."""
    tipo = TipoServicio(
        codigo="salon_eventos", nombre="Salón de eventos", modo_reserva=ModoReserva.HORAS
    )
    db.add(tipo)
    db.flush()
    subtipo = SubtipoServicio(tipo_id=tipo.id, codigo="quincho_eventos", nombre="Quincho")
    pista = Comodidad(codigo="pista", nombre="Pista de baile", tipos=[tipo])
    oferta["wifi"].tipos.append(tipo)
    db.add_all([subtipo, pista])
    db.flush()

    cara = oferta["cara"]
    publicacion = Publicacion(
        prestador_id=oferta["prestador"].id,
        tipo_servicio_id=tipo.id,
        subtipo_servicio_id=subtipo.id,
        titulo="Salón Los Álamos",
        slug="salon-los-alamos",
        descripcion="Salón para 80 personas.",
        estado=EstadoPublicacion.APROBADA,
        localidad_id=cara.localidad_id,
        ubicacion=cara.ubicacion,
        confirmacion_inmediata=False,
    )
    db.add(publicacion)
    db.flush()
    unidad = Unidad(
        publicacion_id=publicacion.id, nombre="Salón", capacidad=120, capacidad_sentados=80
    )
    db.add(unidad)
    db.flush()
    # Con tarifa por noche: si los filtros fallaran, el salón saldría en la
    # búsqueda de alojamiento con precio, que es justo lo que no tiene que pasar.
    db.add(Tarifa(unidad_id=unidad.id, nombre="Base", precio_noche=Decimal(100000)))
    db.flush()
    return {"tipo": tipo, "publicacion": publicacion, "unidad": unidad, "subtipo": subtipo}


def _hora(dia: int, hora: int, minuto: int = 0) -> datetime:
    """Una hora de reloj argentina, en un día cualquiera del futuro."""
    base = datetime.now(ZONA).date() + timedelta(days=30 + dia)
    return datetime(base.year, base.month, base.day, hora, minuto, tzinfo=ZONA)


def _bloquear(db, unidad, inicio, fin, **kw):
    return horarios.bloquear(db, unidad, inicio, fin, OrigenBloqueo.MANUAL, **kw)


# --- Disponibilidad por hora ---


def test_un_rango_libre_se_toma(db, salon):
    u = salon["unidad"]
    _bloquear(db, u, _hora(0, 15), _hora(0, 18))
    assert not horarios.libre(db, u.id, _hora(0, 17), _hora(0, 19))
    assert horarios.libre(db, u.id, _hora(0, 10), _hora(0, 14))


def test_dos_rangos_que_se_pisan_no_conviven(db, salon):
    u = salon["unidad"]
    _bloquear(db, u, _hora(0, 15), _hora(0, 18))
    with pytest.raises(horarios.HorarioOcupado):
        _bloquear(db, u, _hora(0, 17), _hora(0, 20))
    # Y la transacción sigue viva: el rechazo no se lleva lo anterior.
    assert len(horarios.ocupados(db, u.id, _hora(0, 0), _hora(1, 0))) == 1


def test_uno_que_termina_cuando_empieza_el_otro_conviven(db, salon):
    u = salon["unidad"]
    _bloquear(db, u, _hora(0, 15), _hora(0, 18))
    _bloquear(db, u, _hora(0, 18), _hora(0, 21))
    assert [o.inicio for o in horarios.ocupados(db, u.id, _hora(0, 0), _hora(1, 0))] == [
        _hora(0, 15), _hora(0, 18)
    ]


def test_un_evento_que_cruza_la_medianoche_ocupa_la_madrugada(db, salon):
    u = salon["unidad"]
    _bloquear(db, u, _hora(0, 21), _hora(1, 5))
    assert not horarios.libre(db, u.id, _hora(1, 2), _hora(1, 4))
    assert horarios.libre(db, u.id, _hora(1, 10), _hora(1, 14))


def test_la_base_impide_la_superposicion_aunque_nadie_consulte_antes(db, salon):
    """Lo que de verdad cierra la ventana entre el chequeo y la inserción."""
    u = salon["unidad"]
    _bloquear(db, u, _hora(2, 20), _hora(2, 23))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(
                "INSERT INTO bloqueo_horario (id, unidad_id, rango, origen, activo) "
                "VALUES (gen_random_uuid(), :u, tstzrange(:a, :b, '[)'), 'manual', true)"
            ),
            {"u": u.id, "a": _hora(2, 22), "b": _hora(2, 23, 30)},
        )


def test_un_bloqueo_inactivo_no_ocupa(db, salon):
    u = salon["unidad"]
    b = _bloquear(db, u, _hora(3, 15), _hora(3, 18))
    b.activo = False
    db.flush()
    _bloquear(db, u, _hora(3, 16), _hora(3, 17))


def test_una_retencion_vencida_no_traba_al_que_llega_despues(db, salon):
    u = salon["unidad"]
    ahora = datetime.now(UTC)
    _bloquear(db, u, _hora(4, 15), _hora(4, 18), vence_en=ahora - timedelta(minutes=1))
    assert horarios.libre(db, u.id, _hora(4, 16), _hora(4, 17))
    _bloquear(db, u, _hora(4, 16), _hora(4, 17))


def test_la_tarea_suelta_las_retenciones_vencidas(db, salon):
    u = salon["unidad"]
    vencida = _bloquear(
        db, u, _hora(5, 15), _hora(5, 18), vence_en=datetime.now(UTC) - timedelta(minutes=1)
    )
    vigente = _bloquear(
        db, u, _hora(5, 19), _hora(5, 21), vence_en=datetime.now(UTC) + timedelta(minutes=10)
    )
    assert horarios.soltar_vencidos(db) == 1
    db.expire_all()
    assert db.get(BloqueoHorario, vencida.id).activo is False
    assert db.get(BloqueoHorario, vigente.id).activo is True


@pytest.mark.parametrize(
    ("inicio", "fin", "motivo"),
    [
        (_hora(0, 18), _hora(0, 15), "posterior"),
        (_hora(0, 15), _hora(0, 15, 10), "corto"),
        (_hora(0, 15), _hora(3, 15), "48 horas"),
        (_hora(0, 15).replace(tzinfo=None), _hora(0, 18).replace(tzinfo=None), "zona"),
    ],
)
def test_rangos_sin_sentido_se_rechazan(db, salon, inicio, fin, motivo):
    with pytest.raises(horarios.HorarioInvalido, match=motivo):
        _bloquear(db, salon["unidad"], inicio, fin)


def test_una_cabana_no_se_bloquea_por_horario(db, oferta):
    with pytest.raises(horarios.HorarioInvalido, match="por horario"):
        _bloquear(db, oferta["u_cara"], _hora(0, 15), _hora(0, 18))


# --- Separado de los alojamientos ---


def test_la_busqueda_de_alojamiento_no_muestra_salones(cliente, salon):
    from tests.test_api_reservas import FECHAS

    r = cliente.get(
        "/api/v1/publicaciones/buscar",
        params={"localidad": "bariloche", **FECHAS, "personas": 2},
    ).json()
    titulos = {x["titulo"] for x in r["resultados"]}
    assert titulos  # las cabañas siguen apareciendo
    assert "Salón Los Álamos" not in titulos


def test_explorar_y_destinos_no_cuentan_salones(cliente, db, salon):
    r = cliente.get("/api/v1/publicaciones/explorar", params={"localidad": "bariloche"}).json()
    assert "Salón Los Álamos" not in {x["titulo"] for x in r["publicaciones"]}
    total_antes = sum(n for _, _, n in fichas.destinos_con_oferta(db))
    salon["publicacion"].estado = EstadoPublicacion.PAUSADA
    db.flush()
    assert sum(n for _, _, n in fichas.destinos_con_oferta(db)) == total_antes


def test_la_ficha_de_alojamiento_no_abre_un_salon(cliente, salon):
    r = cliente.get(f"/api/v1/publicaciones/{salon['publicacion'].slug}")
    assert r.status_code == 404


def test_un_salon_no_se_cotiza_por_noches(db, salon):
    with pytest.raises(reservas.NoSePuedeReservar, match="^Esto no se reserva por noches$"):
        reservas.cotizar(db, salon["unidad"], LLEGADA, SALIDA)


# --- Catálogos por tipo ---


def test_los_filtros_traen_las_comodidades_de_cada_tipo(cliente, salon):
    alojamiento = cliente.get("/api/v1/publicaciones/filtros").json()
    de_salon = cliente.get(
        "/api/v1/publicaciones/filtros", params={"tipo": "salon_eventos"}
    ).json()
    codigos = {c["codigo"] for c in alojamiento["comodidades"]}
    assert "pista" not in codigos and "wifi" in codigos
    codigos = {c["codigo"] for c in de_salon["comodidades"]}
    assert {"pista", "wifi"} <= codigos and "pileta" not in codigos
    assert [s["codigo"] for s in de_salon["subtipos"]] == ["quincho_eventos"]
    assert "quincho_eventos" not in {s["codigo"] for s in alojamiento["subtipos"]}


def test_una_cabana_no_puede_ser_quincho_ni_tener_pista(cliente, db, oferta, salon):
    from app.core.security import crear_token
    from app.models import Usuario

    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    cabecera = {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}
    cara = oferta["cara"]
    r = cliente.patch(
        f"/api/v1/mis-publicaciones/{cara.id}",
        headers=cabecera,
        json={"subtipo_servicio_id": str(salon["subtipo"].id)},
    )
    assert r.status_code == 422

    r = cliente.patch(
        f"/api/v1/mis-publicaciones/{cara.id}",
        headers=cabecera,
        json={"comodidades": ["wifi", "pista"]},
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    guardadas = {c.codigo for c in db.get(Publicacion, cara.id).comodidades}
    assert guardadas == {"wifi"}


def test_el_catalogo_real_es_idempotente_y_completa_tipos(db):
    from app.semilla import cargar_catalogo

    cargar_catalogo(db)
    cargar_catalogo(db)
    salon_tipo = db.scalar(select(TipoServicio).where(TipoServicio.codigo == "salon_eventos"))
    assert salon_tipo.modo_reserva is ModoReserva.HORAS
    wifi = db.scalar(select(Comodidad).where(Comodidad.codigo == "wifi"))
    assert {t.codigo for t in wifi.tipos} == {"alojamiento", "salon_eventos"}
    assert len(wifi.tipos) == 2  # no se duplicó
