"""Bloqueos, importación y exportación de calendarios (docs/01 §5 R3).

Estas pruebas cubren la promesa central del producto: cero dobles reservas.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range

from app.models import BloqueoFecha, CalendarioExterno
from app.models.enums import OrigenBloqueo
from app.services import calendario as agenda
from app.services import ical
from tests.conftest import HOY

LLEGADA = date(2026, 11, 10)
SALIDA = date(2026, 11, 14)


def ics(*tramos: tuple[str, str], prodid="-//Airbnb Inc//Hosting Calendar//EN") -> bytes:
    eventos = "".join(
        f"BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:{d}\r\nDTEND;VALUE=DATE:{h}\r\n"
        f"UID:{d}-{h}@airbnb.com\r\nSUMMARY:Reserved\r\nEND:VEVENT\r\n"
        for d, h in tramos
    )
    return (
        f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:{prodid}\r\nCALSCALE:GREGORIAN\r\n"
        f"{eventos}END:VCALENDAR\r\n"
    ).encode()


# --- Formato ---


def test_lee_un_calendario_de_airbnb(db):
    tramos = ical.parsear(ics(("20261110", "20261114"), ("20261220", "20261227")))
    assert [(t.desde, t.hasta) for t in tramos] == [
        (date(2026, 11, 10), date(2026, 11, 14)),
        (date(2026, 12, 20), date(2026, 12, 27)),
    ]


def test_la_salida_es_exclusiva_como_en_la_base(db):
    """DTEND es el día de salida: esa noche queda libre para el próximo."""
    tramo = ical.parsear(ics(("20261110", "20261111")))[0]
    assert tramo.desde == date(2026, 11, 10)
    assert tramo.hasta == date(2026, 11, 11)  # una sola noche


def test_un_archivo_que_no_es_ical_se_rechaza():
    with pytest.raises(ical.CalendarioIlegible):
        ical.parsear(b"esto no es un calendario")


def test_restar_saca_lo_que_ya_esta_tomado():
    pedido = [ical.Ocupacion(desde=date(2026, 11, 10), hasta=date(2026, 11, 20))]
    libres = ical.restar(pedido, [(date(2026, 11, 12), date(2026, 11, 15))])
    assert [(t.desde, t.hasta) for t in libres] == [
        (date(2026, 11, 10), date(2026, 11, 12)),
        (date(2026, 11, 15), date(2026, 11, 20)),
    ]


def test_restar_puede_dejar_nada():
    pedido = [ical.Ocupacion(desde=date(2026, 11, 10), hasta=date(2026, 11, 14))]
    assert ical.restar(pedido, [(date(2026, 11, 1), date(2026, 12, 1))]) == []


# --- Bloqueo manual ---


def test_bloquear_y_soltar_fechas(db, oferta):
    unidad = oferta["u_cara"]
    bloqueo = agenda.bloquear(db, unidad.id, LLEGADA, SALIDA, "Uso familiar")
    tramos = agenda.ocupacion(db, unidad.id)
    assert any(t.id == bloqueo.id and t.etiqueta == "Bloqueada por vos" for t in tramos)

    assert agenda.desbloquear(db, unidad.id, bloqueo.id) is True
    assert all(t.id != bloqueo.id for t in agenda.ocupacion(db, unidad.id))


def test_no_se_puede_bloquear_sobre_algo_tomado(db, oferta):
    unidad = oferta["u_cara"]
    agenda.bloquear(db, unidad.id, LLEGADA, SALIDA)
    with pytest.raises(agenda.FechasOcupadas):
        agenda.bloquear(db, unidad.id, LLEGADA + timedelta(days=1), SALIDA + timedelta(days=2))


def test_el_rango_al_reves_se_rechaza(db, oferta):
    with pytest.raises(agenda.RangoInvalido):
        agenda.bloquear(db, oferta["u_cara"].id, SALIDA, LLEGADA)


def test_solo_se_sueltan_los_bloqueos_manuales(db, oferta):
    """Un bloqueo que vino de una reserva no lo suelta el prestador a mano."""
    unidad = oferta["u_cara"]
    db.add(
        BloqueoFecha(
            unidad_id=unidad.id,
            rango=Range(LLEGADA, SALIDA, bounds="[)"),
            origen=OrigenBloqueo.RESERVA,
            activo=True,
        )
    )
    db.flush()
    reserva = db.scalar(
        select(BloqueoFecha).where(
            BloqueoFecha.unidad_id == unidad.id, BloqueoFecha.origen == OrigenBloqueo.RESERVA
        )
    )
    assert agenda.desbloquear(db, unidad.id, reserva.id) is False


# --- Importación ---


def _calendario(db, unidad) -> CalendarioExterno:
    c = CalendarioExterno(unidad_id=unidad.id, nombre="Airbnb", url="https://airbnb.test/x.ics")
    db.add(c)
    db.flush()
    return c


def test_importar_bloquea_las_fechas_de_la_otra_plataforma(db, oferta):
    unidad = oferta["u_cara"]
    c = _calendario(db, unidad)
    resultado = agenda.sincronizar(db, c, ics(("20261110", "20261114")))
    assert resultado.importados == 1
    assert resultado.descartados == 0

    tramos = agenda.ocupacion(db, unidad.id)
    externo = next(t for t in tramos if t.origen is OrigenBloqueo.ICAL)
    assert (externo.desde, externo.hasta) == (LLEGADA, SALIDA)
    assert externo.calendario == "Airbnb"
    assert c.ultima_sincronizacion is not None


def test_una_fecha_ocupada_en_otra_plataforma_no_se_puede_reservar_aca(db, oferta):
    """Es la casilla de verificación de docs/01 §5 R3."""
    from app.services import busqueda

    unidad = oferta["u_cara"]
    agenda.sincronizar(db, _calendario(db, unidad), ics(("20261110", "20261114")))
    db.flush()

    filtros = busqueda.Filtros(
        fecha_inicio=LLEGADA, fecha_fin=SALIDA, personas=2, localidad="bariloche"
    )
    resultados = busqueda.buscar(db, filtros, hoy=HOY).resultados
    unidades = [r.unidad.nombre for r in resultados if r.titulo == "Complejo Caro"]
    assert "Cabaña 1" not in unidades  # la unidad cara quedó tomada


def test_importar_no_pisa_una_reserva_propia(db, oferta):
    """Lo que se superpone se descarta y se informa, en vez de reventar."""
    unidad = oferta["u_cara"]
    agenda.bloquear(db, unidad.id, date(2026, 11, 12), date(2026, 11, 13), "Mantenimiento")
    resultado = agenda.sincronizar(db, _calendario(db, unidad), ics(("20261110", "20261114")))

    assert resultado.importados == 2  # se parte en dos alrededor del bloqueo propio
    tramos = sorted(
        [t for t in agenda.ocupacion(db, unidad.id) if t.origen is OrigenBloqueo.ICAL],
        key=lambda t: t.desde,
    )
    assert [(t.desde, t.hasta) for t in tramos] == [
        (date(2026, 11, 10), date(2026, 11, 12)),
        (date(2026, 11, 13), date(2026, 11, 14)),
    ]
    # El bloqueo manual sigue intacto.
    assert any(t.origen is OrigenBloqueo.MANUAL for t in agenda.ocupacion(db, unidad.id))


def test_sincronizar_de_nuevo_libera_lo_que_alla_se_cancelo(db, oferta):
    unidad = oferta["u_cara"]
    c = _calendario(db, unidad)
    agenda.sincronizar(db, c, ics(("20261110", "20261114"), ("20261220", "20261227")))
    assert len([t for t in agenda.ocupacion(db, unidad.id) if t.origen is OrigenBloqueo.ICAL]) == 2

    agenda.sincronizar(db, c, ics(("20261220", "20261227")))
    quedan = [t for t in agenda.ocupacion(db, unidad.id) if t.origen is OrigenBloqueo.ICAL]
    assert len(quedan) == 1
    assert quedan[0].desde == date(2026, 12, 20)


def test_un_calendario_ilegible_deja_el_motivo_registrado(db, oferta):
    c = _calendario(db, oferta["u_cara"])
    with pytest.raises(ical.CalendarioIlegible):
        agenda.sincronizar(db, c, b"cualquier cosa")
    assert c.ultimo_error and "no se entiende" in c.ultimo_error


# --- Exportación ---


def test_exportar_publica_las_noches_tomadas(db, oferta):
    unidad = oferta["u_cara"]
    agenda.bloquear(db, unidad.id, LLEGADA, SALIDA, "Uso familiar")
    texto = agenda.exportar(db, unidad).decode()

    assert "BEGIN:VCALENDAR" in texto
    assert "DTSTART;VALUE=DATE:20261110" in texto
    assert "DTEND;VALUE=DATE:20261114" in texto


def test_exportar_no_devuelve_lo_que_trajo_otra_plataforma(db, oferta):
    """Devolverle a Airbnb sus propias fechas sería un eco sin sentido."""
    unidad = oferta["u_cara"]
    agenda.sincronizar(db, _calendario(db, unidad), ics(("20261110", "20261114")))
    agenda.bloquear(db, unidad.id, date(2026, 12, 1), date(2026, 12, 5), "Propio")

    texto = agenda.exportar(db, unidad).decode()
    assert "20261201" in texto  # el propio sí
    assert "20261110" not in texto  # el importado no


def test_exportar_no_filtra_datos_del_huesped(db, oferta):
    unidad = oferta["u_cara"]
    db.add(
        BloqueoFecha(
            unidad_id=unidad.id,
            rango=Range(LLEGADA, SALIDA, bounds="[)"),
            origen=OrigenBloqueo.RESERVA,
            activo=True,
            nota="Reserva de Ana Pérez, 2 personas, pagó $200.000",
        )
    )
    db.flush()
    texto = agenda.exportar(db, unidad).decode()
    assert "Ana Pérez" not in texto
    assert "200.000" not in texto
    assert "Reservada acá" in texto


def test_ida_y_vuelta(db, oferta):
    """Lo que exportamos lo tenemos que poder volver a leer."""
    unidad = oferta["u_cara"]
    agenda.bloquear(db, unidad.id, LLEGADA, SALIDA)
    tramos = ical.parsear(agenda.exportar(db, unidad))
    assert (tramos[0].desde, tramos[0].hasta) == (LLEGADA, SALIDA)


def test_las_fechas_guardadas_no_se_corren(db, oferta):
    """Regresión: pasar una tupla a un DATERANGE crea extremos exclusivos y Postgres
    normaliza el rango discreto corriendo el inicio un día. Esta prueba lee de vuelta
    desde la base —no el objeto en memoria— porque el corrimiento solo se ve ahí."""
    from sqlalchemy import text

    unidad = oferta["u_cara"]
    bloqueo = agenda.bloquear(db, unidad.id, date(2027, 5, 10), date(2027, 5, 15))
    db.flush()

    guardado = db.execute(
        text("SELECT lower(rango), upper(rango) FROM bloqueo_fecha WHERE id = :i"),
        {"i": str(bloqueo.id)},
    ).one()
    assert guardado[0] == date(2027, 5, 10), "la fecha de inicio se corrió al guardar"
    assert guardado[1] == date(2027, 5, 15)

    db.expire(bloqueo)
    releido = agenda.ocupacion(db, unidad.id)
    tramo = next(t for t in releido if t.id == bloqueo.id)
    assert (tramo.desde, tramo.hasta) == (date(2027, 5, 10), date(2027, 5, 15))


def test_el_calendario_importado_tampoco_se_corre(db, oferta):
    unidad = oferta["u_cara"]
    c = _calendario(db, unidad)
    agenda.sincronizar(db, c, ics(("20270301", "20270305")))
    db.flush()

    from sqlalchemy import text

    fila = db.execute(
        text(
            "SELECT lower(rango), upper(rango) FROM bloqueo_fecha "
            "WHERE calendario_externo_id = :c"
        ),
        {"c": str(c.id)},
    ).one()
    assert (fila[0], fila[1]) == (date(2027, 3, 1), date(2027, 3, 5))
