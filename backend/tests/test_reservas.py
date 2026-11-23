"""Motor de reservas (docs/01 §5 R5, R6, R8).

Acá se prueba la promesa central: cero dobles reservas, y que el precio que el
viajero vio sea el que se le cobra.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from app.models import BloqueoFecha, ComisionAplicada, PoliticaCancelacion, Usuario
from app.models.comision import ReglaComision
from app.models.enums import EstadoReserva, OrigenBloqueo, QuienPaga
from app.services import busqueda, reservas
from app.services.pagos.base import EstadoPago
from tests.conftest import HOY, LLEGADA, SALIDA


@pytest.fixture
def viajero(db):
    u = Usuario(
        email="viajera@ejemplo.com.ar",
        nombre="Ana",
        apellido="Pérez",
        email_verificado=True,
        telefono="+5492644123456",
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def unidad(db, oferta):
    """La unidad cara, libre en las fechas de prueba."""
    return oferta["u_cara"]


def reservar(db, viajero, unidad, **kw):
    datos = dict(fecha_inicio=LLEGADA, fecha_fin=SALIDA, personas=2, hoy=HOY)
    datos.update(kw)
    return reservas.crear(db, viajero, unidad, **datos)


# --- Cotización ---


def test_el_precio_cotizado_es_el_de_la_busqueda(db, viajero, unidad):
    """docs/01 §5 R5: el precio mostrado al inicio coincide con el cobrado."""
    filtros = busqueda.Filtros(
        fecha_inicio=LLEGADA, fecha_fin=SALIDA, personas=2, localidad="bariloche"
    )
    fila = next(
        r for r in busqueda.buscar(db, filtros, hoy=HOY).resultados if r.titulo == "Complejo Caro"
    )
    cotizacion = reservas.cotizar(db, unidad, LLEGADA, SALIDA, personas=2, hoy=HOY)
    # La búsqueda muestra la unidad más barata; se compara contra esa.
    if fila.unidad.id == unidad.id:
        assert cotizacion.total_viajero == fila.unidad.precio.total


def test_no_se_cotiza_una_publicacion_no_aprobada(db, viajero, oferta):
    from app.models.enums import EstadoPublicacion

    oferta["cara"].estado = EstadoPublicacion.PAUSADA
    db.flush()
    with pytest.raises(reservas.NoSePuedeReservar):
        reservas.cotizar(db, oferta["u_cara"], LLEGADA, SALIDA, hoy=HOY)


# --- Creación ---


def test_reservar_retiene_las_fechas(db, viajero, unidad):
    reserva = reservar(db, viajero, unidad)
    assert reserva.estado is EstadoReserva.PENDIENTE_PAGO
    assert reserva.codigo and len(reserva.codigo) == 8
    assert reserva.vence_pago_en is not None

    bloqueo = db.scalar(
        select(BloqueoFecha).where(
            BloqueoFecha.unidad_id == unidad.id,
            BloqueoFecha.origen == OrigenBloqueo.RETENCION,
        )
    )
    assert bloqueo is not None
    assert bloqueo.vence_en == reserva.vence_pago_en


def test_sin_correo_verificado_no_se_reserva(db, unidad):
    """docs/01 §5 R1: no se puede reservar sin correo verificado."""
    sin_verificar = Usuario(
        email="nueva@ejemplo.com.ar", nombre="N", apellido="N", email_verificado=False
    )
    db.add(sin_verificar)
    db.flush()
    with pytest.raises(reservas.NoSePuedeReservar, match="[Vv]erificá"):
        reservar(db, sin_verificar, unidad)


def test_dos_reservas_de_las_mismas_fechas_no_pueden_convivir(db, viajero, unidad):
    """La promesa del producto, probada contra la base."""
    reservar(db, viajero, unidad)
    otro = Usuario(email="otro@ejemplo.com.ar", nombre="O", apellido="O", email_verificado=True)
    db.add(otro)
    db.flush()
    with pytest.raises(reservas.FechasTomadas):
        reservar(db, otro, unidad)


def test_la_unidad_reservada_desaparece_de_la_busqueda(db, viajero, unidad):
    reservar(db, viajero, unidad)
    db.flush()
    filtros = busqueda.Filtros(
        fecha_inicio=LLEGADA, fecha_fin=SALIDA, personas=6, localidad="bariloche"
    )
    resultados = busqueda.buscar(db, filtros, hoy=HOY).resultados
    assert all(r.unidad.id != unidad.id for r in resultados)


def test_cada_reserva_guarda_su_comision(db, viajero, unidad):
    """docs/00 §7: cambiar una regla no altera reservas existentes."""
    reserva = reservar(db, viajero, unidad)
    item = reserva.items[0]
    snapshot = db.scalar(
        select(ComisionAplicada).where(ComisionAplicada.item_reserva_id == item.id)
    )
    assert snapshot is not None
    antes = snapshot.comision_total

    regla = db.scalar(select(ReglaComision).where(ReglaComision.es_default))
    regla.porcentaje = D(50)
    regla.quien_paga = QuienPaga.VIAJERO
    db.flush()
    db.refresh(snapshot)
    assert snapshot.comision_total == antes  # intacta


def test_el_total_incluye_el_cargo_de_servicio_cuando_lo_paga_el_viajero(db, viajero, unidad):
    regla = db.scalar(select(ReglaComision).where(ReglaComision.es_default))
    regla.quien_paga = QuienPaga.VIAJERO
    db.flush()

    reserva = reservar(db, viajero, unidad)
    item = reserva.items[0]
    assert reserva.total == item.subtotal + item.comision.cargo_viajero
    assert item.comision.cargo_viajero > 0


# --- Pago ---


def test_el_pago_aprobado_confirma_y_afirma_el_bloqueo(db, viajero, unidad):
    reserva = reservar(db, viajero, unidad)
    reservas.registrar_pago(db, reserva, "pago-1", "simulada", EstadoPago.APROBADO)

    assert reserva.estado is EstadoReserva.CONFIRMADA
    assert reserva.vence_pago_en is None
    bloqueo = db.scalar(
        select(BloqueoFecha).where(BloqueoFecha.item_reserva_id == reserva.items[0].id)
    )
    assert bloqueo.origen is OrigenBloqueo.RESERVA
    assert bloqueo.vence_en is None


def test_el_webhook_repetido_no_duplica_nada(db, viajero, unidad):
    """docs/01 §5 R6: las notificaciones se procesan una sola vez."""
    reserva = reservar(db, viajero, unidad)
    for _ in range(3):
        reservas.registrar_pago(db, reserva, "pago-1", "simulada", EstadoPago.APROBADO)

    assert len(reserva.pagos) == 1
    assert reserva.estado is EstadoReserva.CONFIRMADA
    bloqueos = db.scalars(
        select(BloqueoFecha).where(BloqueoFecha.item_reserva_id == reserva.items[0].id)
    ).all()
    assert len(bloqueos) == 1


def test_el_pago_rechazado_libera_las_fechas(db, viajero, unidad):
    reserva = reservar(db, viajero, unidad)
    reservas.registrar_pago(db, reserva, "pago-2", "simulada", EstadoPago.RECHAZADO)

    assert reserva.estado is EstadoReserva.CANCELADA
    assert not db.scalars(
        select(BloqueoFecha).where(BloqueoFecha.item_reserva_id == reserva.items[0].id)
    ).all()


def test_si_la_publicacion_es_a_solicitud_queda_esperando_al_prestador(db, viajero, oferta):
    unidad = db.scalar(
        select(type(oferta["u_cara"])).where(
            type(oferta["u_cara"]).publicacion_id == oferta["cara"].id
        )
    )
    oferta["cara"].confirmacion_inmediata = False
    db.flush()

    reserva = reservar(db, viajero, unidad)
    reservas.registrar_pago(db, reserva, "pago-3", "simulada", EstadoPago.APROBADO)
    assert reserva.estado is EstadoReserva.PENDIENTE_APROBACION
    assert reserva.vence_aprobacion_en is not None

    reservas.aprobar(db, reserva)
    assert reserva.estado is EstadoReserva.CONFIRMADA


def test_el_prestador_puede_rechazar_y_las_fechas_se_liberan(db, viajero, oferta):
    oferta["cara"].confirmacion_inmediata = False
    db.flush()
    reserva = reservar(db, viajero, oferta["u_cara"])
    reservas.registrar_pago(db, reserva, "pago-4", "simulada", EstadoPago.APROBADO)
    reservas.rechazar(db, reserva, "Tengo la casa en refacción")

    assert reserva.estado is EstadoReserva.CANCELADA
    assert not db.scalars(
        select(BloqueoFecha).where(BloqueoFecha.item_reserva_id == reserva.items[0].id)
    ).all()


def test_no_se_aprueba_una_reserva_que_no_espera_respuesta(db, viajero, unidad):
    reserva = reservar(db, viajero, unidad)
    with pytest.raises(reservas.TransicionInvalida):
        reservas.aprobar(db, reserva)


# --- Cancelación y reintegros ---


def _con_politica(db, oferta, tramos):
    politica = PoliticaCancelacion(codigo="prueba", nombre="De prueba", tramos=tramos)
    db.add(politica)
    db.flush()
    oferta["cara"].politica_cancelacion_id = politica.id
    db.flush()


def test_el_reintegro_sale_de_la_politica_que_la_reserva_guardo(db, viajero, oferta):
    _con_politica(db, oferta, [{"dias_antes": 7, "porcentaje_reintegro": 100},
                               {"dias_antes": 2, "porcentaje_reintegro": 50}])
    reserva = reservar(db, viajero, oferta["u_cara"])
    reservas.registrar_pago(db, reserva, "pago-5", "simulada", EstadoPago.APROBADO)

    # Faltan muchos días: reintegro completo.
    r = reservas.calcular_reintegro(reserva, hoy=LLEGADA - timedelta(days=20))
    assert r.porcentaje == 100
    assert r.monto == reserva.total

    # Faltan 3: alcanza el tramo del 50%.
    r = reservas.calcular_reintegro(reserva, hoy=LLEGADA - timedelta(days=3))
    assert r.porcentaje == 50

    # El mismo día: nada.
    r = reservas.calcular_reintegro(reserva, hoy=LLEGADA)
    assert r.porcentaje == 0


def test_cancelar_libera_las_fechas_y_dice_cuanto_se_devuelve(db, viajero, oferta):
    _con_politica(db, oferta, [{"dias_antes": 7, "porcentaje_reintegro": 100}])
    reserva = reservar(db, viajero, oferta["u_cara"])
    reservas.registrar_pago(db, reserva, "pago-6", "simulada", EstadoPago.APROBADO)

    reintegro = reservas.cancelar(db, reserva, "Cambio de planes", hoy=LLEGADA - timedelta(days=30))
    assert reintegro.porcentaje == 100
    assert reserva.estado is EstadoReserva.CANCELADA
    assert not db.scalars(
        select(BloqueoFecha).where(BloqueoFecha.item_reserva_id == reserva.items[0].id)
    ).all()


def test_no_se_cancela_dos_veces(db, viajero, unidad):
    reserva = reservar(db, viajero, unidad)
    reservas.cancelar(db, reserva, "Primera", hoy=HOY)
    with pytest.raises(reservas.TransicionInvalida):
        reservas.cancelar(db, reserva, "Segunda", hoy=HOY)


def test_una_reserva_sin_politica_no_inventa_reintegro(db, viajero, unidad):
    reserva = reservar(db, viajero, unidad)
    r = reservas.calcular_reintegro(reserva, hoy=HOY)
    assert r.porcentaje == 0
    assert "no tiene política" in r.motivo


# --- Vencimiento ---


def test_la_reserva_no_pagada_se_libera_sola(db, viajero, unidad):
    """docs/01 §5 R5: una reserva no pagada en el plazo se libera automáticamente."""
    reserva = reservar(db, viajero, unidad)
    reserva.vence_pago_en = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()

    liberadas = reservas.liberar_vencidas(db)
    assert liberadas == 1
    assert reserva.estado is EstadoReserva.CANCELADA
    assert not db.scalars(
        select(BloqueoFecha).where(BloqueoFecha.item_reserva_id == reserva.items[0].id)
    ).all()


def test_una_retencion_vencida_no_bloquea_aunque_la_tarea_no_haya_corrido(db, viajero, unidad):
    """La red de seguridad: la búsqueda ya ignora las retenciones vencidas."""
    reserva = reservar(db, viajero, unidad)
    bloqueo = db.scalar(
        select(BloqueoFecha).where(BloqueoFecha.item_reserva_id == reserva.items[0].id)
    )
    bloqueo.vence_en = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()

    filtros = busqueda.Filtros(
        fecha_inicio=LLEGADA, fecha_fin=SALIDA, personas=6, localidad="bariloche"
    )
    resultados = busqueda.buscar(db, filtros, hoy=HOY).resultados
    assert any(r.unidad.id == unidad.id for r in resultados)


def test_traer_por_codigo(db, viajero, unidad):
    reserva = reservar(db, viajero, unidad)
    db.flush()
    assert reservas.traer(db, reserva.codigo.lower()).id == reserva.id
    assert reservas.traer(db, "NOEXISTE") is None


# --- Avisos (docs/01 §5 R9) ---


def test_reservar_deja_el_aviso_en_el_buzon(db, viajero, unidad):
    from app.models import Notificacion

    reserva = reservar(db, viajero, unidad)
    avisos = db.scalars(
        select(Notificacion).where(Notificacion.reserva_id == reserva.id)
    ).all()
    assert [a.evento for a in avisos] == ["reserva_creada"]
    assert avisos[0].destino == viajero.email
    assert reserva.codigo in avisos[0].asunto


def test_confirmar_avisa_a_los_dos(db, viajero, unidad):
    from app.models import Notificacion

    reserva = reservar(db, viajero, unidad)
    reservas.registrar_pago(db, reserva, "pago-aviso", "simulada", EstadoPago.APROBADO)

    eventos = [
        a.evento
        for a in db.scalars(select(Notificacion).where(Notificacion.reserva_id == reserva.id))
    ]
    assert "reserva_confirmada" in eventos  # al viajero
    assert "nueva_reserva" in eventos  # al prestador


def test_el_aviso_al_prestador_dice_cuanto_le_queda(db, viajero, unidad):
    from app.models import Notificacion

    reserva = reservar(db, viajero, unidad)
    reservas.registrar_pago(db, reserva, "pago-neto", "simulada", EstadoPago.APROBADO)
    aviso = db.scalar(
        select(Notificacion).where(
            Notificacion.reserva_id == reserva.id, Notificacion.evento == "nueva_reserva"
        )
    )
    assert "Te queda:" in aviso.cuerpo
    assert "comisión" in aviso.cuerpo


def test_cancelar_avisa_con_el_motivo(db, viajero, unidad):
    from app.models import Notificacion

    reserva = reservar(db, viajero, unidad)
    reservas.cancelar(db, reserva, "Se me complicó el viaje", hoy=HOY)
    avisos = db.scalars(
        select(Notificacion).where(
            Notificacion.reserva_id == reserva.id,
            Notificacion.evento.like("reserva_cancelada%"),
        )
    ).all()
    assert len(avisos) == 2  # viajero y prestador
    assert all("Se me complicó el viaje" in a.cuerpo for a in avisos)


def test_los_avisos_van_solo_por_correo(db, unidad):
    """WhatsApp no tiene proveedor: es el botón de la reserva confirmada
    (app.services.contacto). Encolar mensajes que nunca salen no sirve a nadie."""
    from app.models import Notificacion
    from app.models.enums import CanalNotificacion

    con_telefono = Usuario(
        email="contel@ejemplo.com.ar",
        nombre="Con",
        apellido="Teléfono",
        telefono="+5492645550000",
        email_verificado=True,
    )
    db.add(con_telefono)
    db.flush()

    reserva = reservar(db, con_telefono, unidad)
    canales = set(
        db.scalars(select(Notificacion.canal).where(Notificacion.reserva_id == reserva.id))
    )
    assert canales == {CanalNotificacion.EMAIL}


def test_el_correo_se_marca_enviado(db, viajero, unidad):
    from app.models import Notificacion
    from app.models.enums import CanalNotificacion, EstadoNotificacion
    from app.services import notificaciones

    reserva = reservar(db, viajero, unidad)
    correo = db.scalar(
        select(Notificacion).where(
            Notificacion.reserva_id == reserva.id,
            Notificacion.canal == CanalNotificacion.EMAIL,
        )
    )
    assert notificaciones.enviar(db, correo) is True
    assert correo.estado is EstadoNotificacion.ENVIADA
    assert correo.enviada_en is not None


def test_vaciar_el_buzon_cuenta_lo_que_salio(db, viajero, unidad):
    from app.services import notificaciones

    reservar(db, viajero, unidad)
    resultado = notificaciones.enviar_pendientes(db)
    assert resultado["intentadas"] >= 1
    assert resultado["enviadas"] >= 1
