"""Excursiones, etapa 1 (docs/05): turnos que se repiten, salidas por día, cupo
sin sobreventa, y que nada de esto se mezcle con los alojamientos."""

import threading
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import (
    Localidad,
    Prestador,
    Provincia,
    Publicacion,
    SalidaExcursion,
    SubtipoServicio,
    Tarifa,
    TipoServicio,
    Unidad,
    Usuario,
)
from app.models.enums import EstadoPublicacion, ModoReserva, OrigenBloqueo
from app.services import reservas, salidas
from app.services.precios_eventos import ZONA
from tests.conftest import LLEGADA, SALIDA

MARTES, JUEVES = 1, 3


def _proximo(dia_semana: int, semanas: int = 2) -> date:
    """Un día de la semana dado, unas semanas adelante (nunca hoy ni mañana)."""
    base = salidas.hoy() + timedelta(weeks=semanas)
    return base + timedelta(days=(dia_semana - base.weekday()) % 7)


@pytest.fixture
def excursion(db, oferta) -> dict:
    """Una cabalgata aprobada del mismo prestador, con un turno martes y jueves a las 9."""
    tipo = TipoServicio(codigo="excursion", nombre="Excursión", modo_reserva=ModoReserva.TURNO_CUPO)
    db.add(tipo)
    db.flush()
    subtipo = SubtipoServicio(tipo_id=tipo.id, codigo="cabalgata", nombre="Cabalgata")
    db.add(subtipo)
    db.flush()
    cara = oferta["cara"]
    publicacion = Publicacion(
        prestador_id=oferta["prestador"].id,
        tipo_servicio_id=tipo.id,
        subtipo_servicio_id=subtipo.id,
        titulo="Cabalgata al Dique",
        slug="cabalgata-al-dique",
        descripcion="Tres horas a caballo.",
        estado=EstadoPublicacion.APROBADA,
        localidad_id=cara.localidad_id,
        ubicacion=cara.ubicacion,
    )
    db.add(publicacion)
    db.flush()
    unidad = Unidad(publicacion_id=publicacion.id, nombre="Cabalgata", capacidad=8)
    db.add(unidad)
    db.flush()
    # Con tarifa por noche: si los filtros fallaran, saldría en la búsqueda de
    # alojamiento con precio.
    db.add(Tarifa(unidad_id=unidad.id, nombre="Base", precio_noche=Decimal(30000)))
    turno = salidas.crear_turno(
        db,
        unidad,
        nombre="Mañana",
        dias_semana=[JUEVES, MARTES, MARTES],
        hora_inicio=time(9, 0),
        duracion_minutos=180,
        cupo=10,
    )
    return {"publicacion": publicacion, "unidad": unidad, "turno": turno}


def _semana(db, excursion, desde: date):
    return salidas.salidas(db, excursion["unidad"], desde, desde + timedelta(days=6))


def _tomar(db, excursion, fecha, personas, **kw):
    salida = salidas.materializar(db, excursion["turno"], fecha)
    return salidas.tomar(db, salida, personas, kw.pop("origen", OrigenBloqueo.RESERVA), **kw)


# --- El turno genera salidas ---


def test_un_turno_sale_los_dias_que_dice_a_la_hora_argentina(db, excursion):
    lunes = _proximo(0)
    semana = _semana(db, excursion, lunes)
    assert [s.fecha.weekday() for s in semana] == [MARTES, JUEVES]
    martes = semana[0]
    assert martes.inicio == datetime(
        martes.fecha.year, martes.fecha.month, martes.fecha.day, 9, tzinfo=ZONA
    )
    assert martes.fin - martes.inicio == timedelta(hours=3)
    assert (martes.cupo, martes.libres, martes.salida_id) == (10, 10, None)
    # Los días repetidos se guardan una vez y ordenados.
    assert excursion["turno"].dias_semana == [MARTES, JUEVES]


def test_la_temporada_limita_los_dias_del_turno(db, excursion):
    turno = excursion["turno"]
    martes = _proximo(MARTES)
    turno.desde = martes + timedelta(days=1)
    turno.hasta = martes + timedelta(days=7)
    db.flush()
    lista = salidas.salidas(
        db, excursion["unidad"], martes - timedelta(days=1), martes + timedelta(days=20)
    )
    assert [s.fecha for s in lista] == [martes + timedelta(days=2), martes + timedelta(days=7)]


def test_no_lista_salidas_que_ya_salieron_ni_mas_alla_de_12_meses(db, excursion):
    martes = _proximo(MARTES)
    ahora = datetime(martes.year, martes.month, martes.day, 10, tzinfo=ZONA)
    lista = salidas.salidas(
        db, excursion["unidad"], martes, martes + timedelta(days=2), ahora=ahora
    )
    assert [s.fecha for s in lista] == [martes + timedelta(days=2)]  # el martes ya salió

    lejos = salidas.hoy() + timedelta(days=salidas.VENTANA_DIAS + 1)
    assert salidas.salidas(db, excursion["unidad"], lejos, lejos + timedelta(days=14)) == []
    with pytest.raises(salidas.SalidaInvalida, match="12 meses"):
        lejos_martes = lejos + timedelta(days=(MARTES - lejos.weekday()) % 7)
        salidas.materializar(db, excursion["turno"], lejos_martes)


def test_un_turno_inactivo_no_genera_salidas(db, excursion):
    excursion["turno"].activo = False
    db.flush()
    assert _semana(db, excursion, _proximo(0)) == []


def test_materializar_un_dia_que_el_turno_no_sale_se_rechaza(db, excursion):
    with pytest.raises(salidas.SalidaInvalida, match="no sale ese día"):
        salidas.materializar(db, excursion["turno"], _proximo(0))


def test_materializar_dos_veces_da_la_misma_salida(db, excursion):
    martes = _proximo(MARTES)
    a = salidas.materializar(db, excursion["turno"], martes)
    b = salidas.materializar(db, excursion["turno"], martes)
    assert a.id == b.id
    assert db.scalar(text("SELECT count(*) FROM salida_excursion")) == 1


# --- Cupo ---


def test_tomar_lugares_descuenta_del_cupo(db, excursion):
    martes = _proximo(MARTES)
    _tomar(db, excursion, martes, 4)
    _tomar(db, excursion, martes, 3)
    martes_vista, jueves_vista = _semana(db, excursion, martes - timedelta(days=1))
    assert (martes_vista.libres, martes_vista.salida_id is not None) == (3, True)
    assert jueves_vista.libres == 10  # el otro día no se toca


def test_no_se_toman_mas_lugares_que_los_libres(db, excursion):
    martes = _proximo(MARTES)
    _tomar(db, excursion, martes, 8)
    with pytest.raises(salidas.SinCupo, match="^Quedan 2 lugares en esta salida$") as e:
        _tomar(db, excursion, martes, 3)
    assert e.value.libres == 2
    _tomar(db, excursion, martes, 2)  # justo los que quedan
    with pytest.raises(salidas.SinCupo, match="^No quedan lugares en esta salida$"):
        _tomar(db, excursion, martes, 1)


def test_la_base_impide_pasarse_del_cupo_aunque_nadie_consulte(db, excursion):
    """Lo que cierra la puerta aunque algún código se saltee el bloqueo."""
    salida = salidas.materializar(db, excursion["turno"], _proximo(MARTES))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            update(SalidaExcursion).where(SalidaExcursion.id == salida.id).values(ocupados=11)
        )


def test_se_necesita_al_menos_una_persona(db, excursion):
    with pytest.raises(salidas.SalidaInvalida, match="al menos una persona"):
        _tomar(db, excursion, _proximo(MARTES), 0)


def test_no_se_toma_lugar_en_una_salida_que_ya_salio(db, excursion):
    martes = _proximo(MARTES)
    salida = salidas.materializar(db, excursion["turno"], martes)
    despues = datetime(martes.year, martes.month, martes.day, 9, 1, tzinfo=ZONA)
    with pytest.raises(salidas.SalidaInvalida, match="ya salió"):
        salidas.tomar(db, salida, 1, OrigenBloqueo.RESERVA, ahora=despues)


def test_soltar_devuelve_los_lugares_una_sola_vez(db, excursion):
    martes = _proximo(MARTES)
    tomado = _tomar(db, excursion, martes, 6)
    salidas.soltar(db, tomado)
    salidas.soltar(db, tomado)
    assert tomado.salida.ocupados == 0
    assert _semana(db, excursion, martes - timedelta(days=1))[0].libres == 10


# --- Retenciones con vencimiento ---


def test_una_retencion_vencida_cuenta_libre_y_se_suelta_al_tomar(db, excursion):
    martes = _proximo(MARTES)
    ahora = datetime.now(UTC)
    _tomar(db, excursion, martes, 7, origen=OrigenBloqueo.RETENCION,
           vence_en=ahora - timedelta(minutes=1))
    assert _semana(db, excursion, martes - timedelta(days=1))[0].libres == 10

    tomado = _tomar(db, excursion, martes, 9)  # entran porque la vencida se soltó
    assert tomado.salida.ocupados == 9


def test_una_retencion_vigente_ocupa(db, excursion):
    martes = _proximo(MARTES)
    _tomar(db, excursion, martes, 7, origen=OrigenBloqueo.RETENCION,
           vence_en=datetime.now(UTC) + timedelta(minutes=15))
    with pytest.raises(salidas.SinCupo):
        _tomar(db, excursion, martes, 4)


def test_la_tarea_suelta_las_retenciones_vencidas(db, excursion):
    martes = _proximo(MARTES)
    ahora = datetime.now(UTC)
    _tomar(db, excursion, martes, 2, origen=OrigenBloqueo.RETENCION,
           vence_en=ahora + timedelta(minutes=10))
    _tomar(db, excursion, martes, 1)
    # La última: cada toma suelta antes las vencidas, así que esta queda para la tarea.
    vencida = _tomar(db, excursion, martes, 3, origen=OrigenBloqueo.RETENCION,
                     vence_en=ahora - timedelta(minutes=1))
    assert salidas.soltar_vencidos(db, ahora) == 3
    db.refresh(vencida)
    assert not vencida.activo
    assert vencida.salida.ocupados == 3
    assert salidas.soltar_vencidos(db, ahora) == 0


# --- Excepciones del prestador ---


def test_una_salida_suspendida_no_se_ofrece_ni_se_vende(db, excursion):
    martes = _proximo(MARTES)
    salida = salidas.materializar(db, excursion["turno"], martes)
    salidas.suspender(db, salida, "Pronóstico de tormenta")

    publico = _semana(db, excursion, martes - timedelta(days=1))
    assert [s.fecha for s in publico] == [martes + timedelta(days=2)]
    panel = salidas.salidas(
        db, excursion["unidad"], martes, martes, con_suspendidas=True
    )
    assert [(s.fecha, s.suspendida) for s in panel] == [(martes, True)]
    with pytest.raises(salidas.SalidaInvalida, match="suspendida"):
        salidas.tomar(db, salida, 1, OrigenBloqueo.RESERVA)

    salidas.reanudar(db, salida)
    assert _semana(db, excursion, martes - timedelta(days=1))[0].fecha == martes


def test_no_se_suspende_una_salida_con_gente_anotada(db, excursion):
    martes = _proximo(MARTES)
    tomado = _tomar(db, excursion, martes, 2)
    with pytest.raises(salidas.SalidaInvalida, match="^Esa salida tiene 2 lugares tomados$"):
        salidas.suspender(db, tomado.salida)


def test_el_cupo_de_una_salida_no_baja_de_lo_tomado(db, excursion):
    martes = _proximo(MARTES)
    tomado = _tomar(db, excursion, martes, 6)
    with pytest.raises(salidas.SalidaInvalida, match="Ya hay 6 lugares tomados"):
        salidas.cambiar_cupo(db, tomado.salida, 5)
    salidas.cambiar_cupo(db, tomado.salida, 14)
    assert _semana(db, excursion, martes - timedelta(days=1))[0].libres == 8


def test_cambiar_el_turno_no_mueve_lo_ya_vendido(db, excursion):
    martes = _proximo(MARTES)
    _tomar(db, excursion, martes, 2)
    turno = excursion["turno"]
    turno.hora_inicio = time(15, 0)
    turno.cupo = 4
    db.flush()
    martes_vista, jueves_vista = _semana(db, excursion, martes - timedelta(days=1))
    assert (martes_vista.inicio.hour, martes_vista.cupo, martes_vista.libres) == (9, 10, 8)
    assert (jueves_vista.inicio.hour, jueves_vista.cupo) == (15, 4)


def test_una_salida_extra_aparece_entre_las_del_turno(db, excursion):
    lunes = _proximo(0)
    salidas.agregar_salida(
        db, excursion["unidad"], fecha=lunes, hora_inicio=time(18, 30),
        duracion_minutos=120, cupo=6, nombre="Cabalgata a la luz de la luna",
    )
    semana = _semana(db, excursion, lunes)
    assert [(s.fecha.weekday(), s.nombre, s.cupo) for s in semana] == [
        (0, "Salida especial", 6), (MARTES, "Mañana", 10), (JUEVES, "Mañana", 10)
    ]


# --- Validaciones ---


@pytest.mark.parametrize(
    ("cambios", "mensaje"),
    [
        ({"dias_semana": []}, "al menos un día"),
        ({"dias_semana": [7]}, "al menos un día"),
        ({"cupo": 0}, "cupo"),
        ({"cupo": 501}, "cupo"),
        ({"duracion_minutos": 10}, "duración"),
        ({"duracion_minutos": 14 * 24 * 60 + 1}, "duración"),
        ({"desde": date(2027, 3, 1), "hasta": date(2027, 2, 1)}, "temporada"),
    ],
)
def test_un_turno_mal_cargado_se_rechaza(db, excursion, cambios, mensaje):
    datos = {
        "nombre": "Tarde", "dias_semana": [5], "hora_inicio": time(16),
        "duracion_minutos": 120, "cupo": 8, **cambios,
    }
    with pytest.raises(salidas.SalidaInvalida, match=mensaje):
        salidas.crear_turno(db, excursion["unidad"], **datos)


def test_un_alojamiento_no_tiene_turnos(db, oferta):
    with pytest.raises(salidas.SalidaInvalida, match="turno y cupo"):
        salidas.crear_turno(
            db, oferta["u_cara"], nombre="X", dias_semana=[1], hora_inicio=time(9),
            duracion_minutos=60, cupo=4,
        )


# --- Separada de los alojamientos ---


def test_la_busqueda_de_alojamiento_no_muestra_excursiones(cliente, excursion):
    from tests.test_api_reservas import FECHAS

    r = cliente.get(
        "/api/v1/publicaciones/buscar",
        params={"localidad": "bariloche", **FECHAS, "personas": 2},
    ).json()
    titulos = {x["titulo"] for x in r["resultados"]}
    assert titulos
    assert "Cabalgata al Dique" not in titulos


def test_una_excursion_no_se_cotiza_por_noches(db, excursion):
    with pytest.raises(reservas.NoSePuedeReservar, match="^Esto no se reserva por noches$"):
        reservas.cotizar(db, excursion["unidad"], LLEGADA, SALIDA)


# --- Concurrencia real: dos conexiones a la vez ---


@pytest.fixture
def excursion_comprometida(engine):
    """Una excursión guardada de verdad (con commit), para probar con dos conexiones.

    Los demás tests corren dentro de una transacción que se deshace; acá hacen
    falta dos transacciones de verdad que se esperen. Todo lleva un sufijo único
    y se borra al terminar.
    """
    sufijo = uuid.uuid4().hex[:8]
    Sesion = sessionmaker(bind=engine, expire_on_commit=False)
    with Sesion() as db:
        prov = Provincia(nombre=f"P {sufijo}", slug=f"p-{sufijo}")
        db.add(prov)
        db.flush()
        loc = Localidad(provincia_id=prov.id, nombre=f"L {sufijo}", slug=f"l-{sufijo}")
        tipo = TipoServicio(
            codigo=f"exc-{sufijo}", nombre="Excursión", modo_reserva=ModoReserva.TURNO_CUPO
        )
        usuario = Usuario(email=f"{sufijo}@demo.test", nombre="P", apellido="C", es_prestador=True)
        db.add_all([loc, tipo, usuario])
        db.flush()
        prest = Prestador(usuario_id=usuario.id, razon_social="P", es_demo=True)
        db.add(prest)
        db.flush()
        pub = Publicacion(
            prestador_id=prest.id, tipo_servicio_id=tipo.id, titulo="Trekking",
            slug=f"trekking-{sufijo}", descripcion="", localidad_id=loc.id,
        )
        db.add(pub)
        db.flush()
        unidad = Unidad(publicacion_id=pub.id, nombre="Trekking", capacidad=10)
        db.add(unidad)
        db.flush()
        turno = salidas.crear_turno(
            db, unidad, nombre="Mañana", dias_semana=list(range(7)), hora_inicio=time(8),
            duracion_minutos=240, cupo=4,
        )
        salida = salidas.materializar(db, turno, salidas.hoy() + timedelta(days=10))
        db.commit()
        ids = {"salida": salida.id, "turno": turno.id, "unidad": unidad.id, "pub": pub.id,
               "prest": prest.id, "usuario": usuario.id, "tipo": tipo.id, "loc": loc.id,
               "prov": prov.id}
    yield Sesion, ids
    with engine.begin() as con:
        for tabla, clave in [
            ("cupo_tomado", ("salida_id", "salida")),
            ("salida_excursion", ("id", "salida")),
            ("turno_excursion", ("id", "turno")),
            ("unidad", ("id", "unidad")),
            ("publicacion", ("id", "pub")),
            ("prestador", ("id", "prest")),
            ("usuario", ("id", "usuario")),
            ("tipo_servicio", ("id", "tipo")),
            ("localidad", ("id", "loc")),
            ("provincia", ("id", "prov")),
        ]:
            columna, nombre = clave
            con.execute(text(f"DELETE FROM {tabla} WHERE {columna} = :v"), {"v": ids[nombre]})


def test_dos_pedidos_simultaneos_por_los_ultimos_lugares_no_pasan_los_dos(
    excursion_comprometida,
):
    Sesion, ids = excursion_comprometida
    resultado: dict = {}

    def segundo():
        with Sesion() as db:
            salida = db.get(SalidaExcursion, ids["salida"])
            try:
                salidas.tomar(db, salida, 3, OrigenBloqueo.RESERVA)
                db.commit()
                resultado["segundo"] = "tomó"
            except salidas.SinCupo as e:
                db.rollback()
                resultado["segundo"] = e.libres

    with Sesion() as primero:
        salida = primero.get(SalidaExcursion, ids["salida"])
        salidas.tomar(primero, salida, 3, OrigenBloqueo.RESERVA)
        hilo = threading.Thread(target=segundo)
        hilo.start()
        hilo.join(timeout=0.5)
        assert hilo.is_alive(), "el segundo tenía que esperar al primero"
        primero.commit()
    hilo.join(timeout=10)

    assert resultado["segundo"] == 1  # vio los 3 del primero y no le alcanzó
    with Sesion() as db:
        assert db.scalar(
            select(SalidaExcursion.ocupados).where(SalidaExcursion.id == ids["salida"])
        ) == 3
