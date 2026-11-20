"""Ventas que entraron por fuera: por mail o cargadas a mano (docs/01 §5 R3).

Despegar no publica iCal y una venta por WhatsApp no tiene calendario ninguno.
Estas pruebas cuidan que igual terminen ocupando la noche —y tapándola en las
otras plataformas— sin que nadie la venda dos veces.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.security import crear_token
from app.models import BloqueoFecha, Prestador, ReservaExterna, Unidad, Usuario
from app.models.enums import OrigenBloqueo
from app.services import calendario as agenda
from app.services.correo.analisis import analizar

HOY_LECTURA = date(2026, 9, 20)


@pytest.fixture
def anfitrion(db, oferta):
    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    return {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}


MAIL_DESPEGAR = """
Tenés una nueva reserva confirmada.
Localizador: DESP-8842
Huésped: María Fernanda Quiroga
Check-in: 11/11/2026
Check-out: 15/11/2026
Huéspedes: 3 personas
Unidad: Cabaña chica
Total: $ 248.500,00
"""


# --- Lectura del mail ---


def test_lee_una_confirmacion_de_despegar():
    r = analizar(
        remitente="reservas@despegar.com.ar",
        asunto="Confirmación de reserva",
        cuerpo=MAIL_DESPEGAR,
        hoy=HOY_LECTURA,
    )
    assert r.plataforma == "despegar"
    assert r.fecha_inicio == date(2026, 11, 11)
    assert r.fecha_fin == date(2026, 11, 15)
    assert r.huesped == "María Fernanda Quiroga"
    assert r.codigo_externo == "DESP-8842"
    assert r.unidad_nombre == "Cabaña chica"
    assert r.personas == 3
    assert r.monto == Decimal("248500.00")
    assert r.faltantes == []


def test_la_fecha_argentina_se_lee_dia_primero():
    """`11/10` es 11 de octubre. Leerlo al revés no da error: da el mes equivocado."""
    r = analizar(cuerpo="Check-in: 11/10/2026\nCheck-out: 13/10/2026", hoy=HOY_LECTURA)
    assert r.fecha_inicio == date(2026, 10, 11)
    assert r.fecha_fin == date(2026, 10, 13)


@pytest.mark.parametrize(
    ("cuerpo", "desde", "hasta"),
    [
        ("del 12 al 15 de octubre de 2026", date(2026, 10, 12), date(2026, 10, 15)),
        ("Entrada 2026-12-01 Salida 2026-12-05", date(2026, 12, 1), date(2026, 12, 5)),
        ("Llegada: 3 de enero\nSalida: 7 de enero", date(2027, 1, 3), date(2027, 1, 7)),
        ("Desde 05/11/2026 hasta 09/11/2026", date(2026, 11, 5), date(2026, 11, 9)),
    ],
)
def test_entiende_las_formas_de_escribir_un_rango(cuerpo, desde, hasta):
    r = analizar(cuerpo=cuerpo, hoy=HOY_LECTURA)
    assert (r.fecha_inicio, r.fecha_fin) == (desde, hasta)


def test_sin_anio_toma_la_proxima_vez_que_pasa():
    """Un mail de confirmación habla del futuro: en diciembre, «5 de enero» es del año que viene."""
    r = analizar(cuerpo="Entrada: 5 de enero\nSalida: 9 de enero", hoy=date(2026, 12, 20))
    assert r.fecha_inicio == date(2027, 1, 5)


def test_lo_que_no_se_entiende_se_declara():
    r = analizar(cuerpo="Hola, quería consultar disponibilidad para el verano.", hoy=HOY_LECTURA)
    assert not r.completa
    assert "fecha de entrada" in r.faltantes


def test_no_acepta_una_salida_anterior_a_la_entrada():
    r = analizar(cuerpo="Check-in: 15/11/2026\nCheck-out: 11/11/2026", hoy=HOY_LECTURA)
    assert not r.completa


# --- Del mail al calendario ---


def test_un_mail_de_despegar_bloquea_las_fechas(cliente, db, oferta, anfitrion):
    r = cliente.post(
        "/api/v1/mi-calendario/correo",
        headers=anfitrion,
        json={
            "remitente": "reservas@despegar.com.ar",
            "asunto": "Confirmación de reserva",
            "cuerpo": MAIL_DESPEGAR,
        },
    )
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["reserva"]["estado"] == "confirmada"
    assert cuerpo["reserva"]["plataforma_nombre"] == "Despegar"
    assert cuerpo["reserva"]["unidad"] == "Cabaña chica"
    assert cuerpo["reserva"]["huesped"] == "María Fernanda Quiroga"

    tramos = agenda.ocupacion(db, oferta["u_chica"].id)
    tomado = next(t for t in tramos if t.desde == date(2026, 11, 11))
    assert tomado.hasta == date(2026, 11, 15)
    assert tomado.origen is OrigenBloqueo.EXTERNA


def test_el_mismo_mail_dos_veces_no_duplica(cliente, db, oferta, anfitrion):
    """Los webhooks se reintentan y la gente reenvía."""
    pedido = {
        "remitente": "reservas@despegar.com.ar",
        "asunto": "Confirmación de reserva",
        "cuerpo": MAIL_DESPEGAR,
    }
    primera = cliente.post("/api/v1/mi-calendario/correo", headers=anfitrion, json=pedido).json()
    segunda = cliente.post("/api/v1/mi-calendario/correo", headers=anfitrion, json=pedido).json()

    assert primera["nueva"] is True
    assert segunda["nueva"] is False
    assert segunda["reserva"]["id"] == primera["reserva"]["id"]
    assert db.scalar(select(ReservaExterna.id).where(ReservaExterna.huella.is_not(None)))
    assert len(list(db.scalars(select(ReservaExterna)))) == 1


def test_lo_que_no_se_entiende_espera_y_no_bloquea(cliente, db, oferta, anfitrion):
    """Un calendario que se calla cuando no entendió es cómo se vende dos veces."""
    antes = len(list(db.scalars(select(BloqueoFecha))))
    r = cliente.post(
        "/api/v1/mi-calendario/correo",
        headers=anfitrion,
        json={"cuerpo": "Hola! Te confirmo la reserva de la cabaña, saludos."},
    )
    assert r.status_code == 201
    assert r.json()["reserva"]["estado"] == "por_revisar"
    assert r.json()["reserva"]["faltantes"]
    assert len(list(db.scalars(select(BloqueoFecha)))) == antes, "no tiene que bloquear nada"

    pendientes = cliente.get("/api/v1/mi-calendario/por-revisar", headers=anfitrion).json()
    assert len(pendientes) == 1


def test_con_varias_unidades_y_sin_nombre_no_adivina(cliente, db, oferta, anfitrion):
    """Bloquearle las fechas a la cabaña equivocada es peor que pedir que lo digan."""
    r = cliente.post(
        "/api/v1/mi-calendario/correo",
        headers=anfitrion,
        json={"cuerpo": "Check-in: 11/11/2026\nCheck-out: 14/11/2026\nHuésped: Ana Pérez"},
    )
    cuerpo = r.json()["reserva"]
    assert cuerpo["estado"] == "por_revisar"
    assert "a qué unidad corresponde" in cuerpo["faltantes"]


def test_el_anfitrion_completa_lo_que_falto_y_recien_ahi_bloquea(
    cliente, db, oferta, anfitrion
):
    pendiente = cliente.post(
        "/api/v1/mi-calendario/correo",
        headers=anfitrion,
        json={"cuerpo": "Check-in: 11/11/2026\nCheck-out: 14/11/2026\nHuésped: Ana Pérez"},
    ).json()["reserva"]

    r = cliente.patch(
        f"/api/v1/mi-calendario/reservas-externas/{pendiente['id']}",
        headers=anfitrion,
        json={"unidad_id": str(oferta["u_chica"].id)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "confirmada"

    tramos = agenda.ocupacion(db, oferta["u_chica"].id)
    assert any(t.desde == date(2026, 11, 11) for t in tramos)


# --- Venta cargada a mano ---


def test_una_venta_por_whatsapp_ocupa_la_noche(cliente, db, oferta, anfitrion):
    r = cliente.post(
        "/api/v1/mi-calendario/reservas-externas",
        headers=anfitrion,
        json={
            "unidad_id": str(oferta["u_chica"].id),
            "fecha_inicio": "2026-11-20",
            "fecha_fin": "2026-11-23",
            "huesped": "Carlos Gómez",
            "contacto": "+54 264 555 1234",
            "personas": 2,
            "monto": "150000.00",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["plataforma_nombre"] == "Venta propia"
    assert r.json()["monto"] == "150000.00"

    tramos = agenda.ocupacion(db, oferta["u_chica"].id)
    tomado = next(t for t in tramos if t.desde == date(2026, 11, 20))
    assert tomado.origen is OrigenBloqueo.EXTERNA
    assert tomado.nota == "Carlos Gómez"


def test_una_venta_por_fuera_sale_en_el_ical_hacia_las_otras_plataformas(
    cliente, db, oferta, anfitrion
):
    """Es el sentido de todo esto: lo de Despegar tiene que tapar la fecha en Airbnb."""
    cliente.post(
        "/api/v1/mi-calendario/reservas-externas",
        headers=anfitrion,
        json={
            "unidad_id": str(oferta["u_chica"].id),
            "fecha_inicio": "2026-11-20",
            "fecha_fin": "2026-11-23",
            "huesped": "Carlos Gómez",
        },
    )
    unidad = db.get(Unidad, oferta["u_chica"].id)
    exportado = agenda.exportar(db, unidad).decode()
    assert "20261120" in exportado
    assert "20261123" in exportado


def test_no_deja_pisar_una_noche_ya_vendida(cliente, oferta, anfitrion):
    """La colisión la frena la base, no un `if`."""
    pedido = {
        "unidad_id": str(oferta["u_chica"].id),
        "fecha_inicio": "2026-11-20",
        "fecha_fin": "2026-11-23",
    }
    assert cliente.post(
        "/api/v1/mi-calendario/reservas-externas", headers=anfitrion, json=pedido
    ).status_code == 201
    choque = cliente.post(
        "/api/v1/mi-calendario/reservas-externas",
        headers=anfitrion,
        json={**pedido, "fecha_inicio": "2026-11-22", "fecha_fin": "2026-11-25"},
    )
    assert choque.status_code == 409
    assert "ya están tomadas" in choque.json()["detail"]


def test_la_salida_no_puede_ser_anterior_a_la_entrada(cliente, oferta, anfitrion):
    r = cliente.post(
        "/api/v1/mi-calendario/reservas-externas",
        headers=anfitrion,
        json={
            "unidad_id": str(oferta["u_chica"].id),
            "fecha_inicio": "2026-11-23",
            "fecha_fin": "2026-11-20",
        },
    )
    assert r.status_code == 422


def test_descartarla_libera_las_fechas(cliente, db, oferta, anfitrion):
    creada = cliente.post(
        "/api/v1/mi-calendario/reservas-externas",
        headers=anfitrion,
        json={
            "unidad_id": str(oferta["u_chica"].id),
            "fecha_inicio": "2026-11-20",
            "fecha_fin": "2026-11-23",
        },
    ).json()

    assert cliente.delete(
        f"/api/v1/mi-calendario/reservas-externas/{creada['id']}", headers=anfitrion
    ).status_code == 204

    tramos = agenda.ocupacion(db, oferta["u_chica"].id)
    assert not any(t.desde == date(2026, 11, 20) for t in tramos)
    # Y la fecha vuelve a poder venderse.
    assert cliente.post(
        "/api/v1/mi-calendario/reservas-externas",
        headers=anfitrion,
        json={
            "unidad_id": str(oferta["u_chica"].id),
            "fecha_inicio": "2026-11-20",
            "fecha_fin": "2026-11-23",
        },
    ).status_code == 201


def test_no_se_puede_cargar_en_la_unidad_de_otro(cliente, db, oferta):
    ajeno = Usuario(email="ajeno@ejemplo.com.ar", nombre="A", apellido="B", es_prestador=True)
    db.add(ajeno)
    db.commit()
    r = cliente.post(
        "/api/v1/mi-calendario/reservas-externas",
        headers={"Authorization": f"Bearer {crear_token(str(ajeno.id))}"},
        json={
            "unidad_id": str(oferta["u_chica"].id),
            "fecha_inicio": "2026-11-20",
            "fecha_fin": "2026-11-23",
        },
    )
    assert r.status_code in (403, 404)


def test_la_reserva_externa_no_genera_comision(cliente, db, oferta, anfitrion):
    """No la vendimos nosotros: ocupa la noche, pero no cobramos nada."""
    from app.models import ComisionAplicada

    antes = len(list(db.scalars(select(ComisionAplicada))))
    cliente.post(
        "/api/v1/mi-calendario/reservas-externas",
        headers=anfitrion,
        json={
            "unidad_id": str(oferta["u_chica"].id),
            "fecha_inicio": "2026-11-20",
            "fecha_fin": "2026-11-23",
            "monto": "150000.00",
        },
    )
    assert len(list(db.scalars(select(ComisionAplicada)))) == antes


def test_el_calendario_general_muestra_la_venta_de_afuera(cliente, oferta, anfitrion):
    cliente.post(
        "/api/v1/mi-calendario/reservas-externas",
        headers=anfitrion,
        json={
            "unidad_id": str(oferta["u_chica"].id),
            "fecha_inicio": (date.today() + timedelta(days=10)).isoformat(),
            "fecha_fin": (date.today() + timedelta(days=13)).isoformat(),
            "huesped": "Carlos Gómez",
        },
    )
    cuerpo = cliente.get("/api/v1/mi-calendario?dias=30", headers=anfitrion).json()
    chica = next(
        u for u in cuerpo["unidades"] if u["unidad_id"] == str(oferta["u_chica"].id)
    )
    externo = next(t for t in chica["tramos"] if t["origen"] == "externa")
    assert externo["etiqueta"] == "Vendida por fuera"
    assert externo["nota"] == "Carlos Gómez"


def test_la_bandeja_de_uno_no_se_ve_desde_otra_cuenta(cliente, db, oferta, anfitrion):
    """Una reserva a medias no tiene unidad todavía, pero sí tiene dueño.

    Si el dueño fuera la unidad, el mail que un anfitrión pega quedaría sin
    pertenecer a nadie y aparecería en la bandeja de todos.
    """
    cliente.post(
        "/api/v1/mi-calendario/correo",
        headers=anfitrion,
        json={"cuerpo": "Check-in: 11/11/2026\nCheck-out: 14/11/2026\nHuésped: Ana Pérez"},
    )
    assert len(cliente.get("/api/v1/mi-calendario/por-revisar", headers=anfitrion).json()) == 1

    otra = Usuario(email="otra@ejemplo.com.ar", nombre="O", apellido="T", es_prestador=True)
    db.add(otra)
    db.flush()
    db.add(
        Prestador(
            usuario_id=otra.id,
            razon_social="Otro prestador",
            fecha_alta=date.today() - timedelta(days=10),
        )
    )
    db.commit()
    ajena = {"Authorization": f"Bearer {crear_token(str(otra.id))}"}
    assert cliente.get("/api/v1/mi-calendario/por-revisar", headers=ajena).json() == []


def test_el_mismo_mail_sin_unidad_tampoco_se_duplica(cliente, db, oferta, anfitrion):
    """En Postgres dos NULL no chocan: la idempotencia tiene que ir por prestador."""
    pedido = {"cuerpo": "Check-in: 11/11/2026\nCheck-out: 14/11/2026\nHuésped: Ana Pérez"}
    cliente.post("/api/v1/mi-calendario/correo", headers=anfitrion, json=pedido)
    segunda = cliente.post("/api/v1/mi-calendario/correo", headers=anfitrion, json=pedido).json()
    assert segunda["nueva"] is False
    assert len(list(db.scalars(select(ReservaExterna)))) == 1


def test_completar_sobre_fechas_tomadas_avisa_en_vez_de_reventar(
    cliente, db, oferta, anfitrion
):
    """El choque se le explica al anfitrión; no es un error nuestro."""
    cliente.post(
        "/api/v1/mi-calendario/reservas-externas",
        headers=anfitrion,
        json={
            "unidad_id": str(oferta["u_chica"].id),
            "fecha_inicio": "2027-03-01",
            "fecha_fin": "2027-03-05",
        },
    )
    media = cliente.post(
        "/api/v1/mi-calendario/correo",
        headers=anfitrion,
        json={"cuerpo": "Check-in: 02/03/2027\nCheck-out: 06/03/2027\nHuésped: Choque"},
    ).json()["reserva"]

    r = cliente.patch(
        f"/api/v1/mi-calendario/reservas-externas/{media['id']}",
        headers=anfitrion,
        json={"unidad_id": str(oferta["u_chica"].id)},
    )
    assert r.status_code == 409
    assert "ya están tomadas" in r.json()["detail"]


# --- Buzón de correo entrante ---


@pytest.fixture
def buzon(monkeypatch):
    """Configura el buzón como lo estaría en producción."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("CORREO_ENTRANTE_SECRETO", "un-secreto-largo")
    monkeypatch.setenv("CORREO_ENTRANTE_DOMINIO", "reservas.suitecabana.test")
    yield
    get_settings.cache_clear()


def test_sin_secreto_configurado_el_buzon_esta_cerrado(cliente, monkeypatch):
    """Un buzón abierto al mundo deja que cualquiera te ocupe el calendario."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("CORREO_ENTRANTE_SECRETO", "")
    r = cliente.post("/api/v1/correo/entrante", json={"text": "hola", "to": "x@y.z"})
    get_settings.cache_clear()
    assert r.status_code == 503
    assert "pegan a mano" in r.json()["detail"]


def test_con_el_secreto_equivocado_no_entra(cliente, buzon, oferta):
    r = cliente.post(
        "/api/v1/correo/entrante",
        headers={"x-buzon-secreto": "otro"},
        json={"text": MAIL_DESPEGAR, "to": f"reservas+{oferta['prestador'].id.hex}@x.test"},
    )
    assert r.status_code == 401


def test_un_mail_reenviado_al_buzon_bloquea_las_fechas(cliente, db, buzon, oferta):
    r = cliente.post(
        "/api/v1/correo/entrante",
        headers={"x-buzon-secreto": "un-secreto-largo"},
        json={
            "to": f"reservas+{oferta['prestador'].id.hex}@reservas.suitecabana.test",
            "from": "reservas@despegar.com.ar",
            "subject": "Confirmación de reserva",
            "text": MAIL_DESPEGAR,
            "Message-ID": "<abc-123@despegar.com.ar>",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["estado"] == "confirmada"

    tramos = agenda.ocupacion(db, oferta["u_chica"].id)
    assert any(t.origen is OrigenBloqueo.EXTERNA for t in tramos)


def test_el_proveedor_puede_reintentar_sin_duplicar(cliente, db, buzon, oferta):
    """Los webhooks se reintentan: el mismo Message-ID no puede entrar dos veces."""
    pedido = {
        "to": f"reservas+{oferta['prestador'].id.hex}@reservas.suitecabana.test",
        "from": "reservas@despegar.com.ar",
        "text": MAIL_DESPEGAR,
        "Message-ID": "<abc-123@despegar.com.ar>",
    }
    cabecera = {"x-buzon-secreto": "un-secreto-largo"}
    primera = cliente.post("/api/v1/correo/entrante", headers=cabecera, json=pedido).json()
    segunda = cliente.post("/api/v1/correo/entrante", headers=cabecera, json=pedido).json()
    assert primera["nueva"] is True
    assert segunda["nueva"] is False
    assert len(list(db.scalars(select(ReservaExterna)))) == 1


def test_una_direccion_de_buzon_inventada_no_carga_nada(cliente, buzon):
    r = cliente.post(
        "/api/v1/correo/entrante",
        headers={"x-buzon-secreto": "un-secreto-largo"},
        json={"to": "reservas+nodeaca@reservas.suitecabana.test", "text": MAIL_DESPEGAR},
    )
    assert r.status_code in (404, 422)
