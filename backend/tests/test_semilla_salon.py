"""El salón de Los Búhos en la semilla (docs/04, etapa 7)."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range

import app.semilla as semilla
from app.models import BloqueoHorario, FranjaHoraria, Publicacion, Unidad
from app.models.enums import EstadoPublicacion, ModoReserva, OrigenBloqueo
from app.semilla import datos
from app.services import edicion


def _cargar(db, tmp_path, monkeypatch):
    # Sin las fotos reales (no están en el repo) y sin escribir en la carpeta de medios.
    monkeypatch.setattr(semilla, "CARPETA_SALON_LOS_BUHOS", tmp_path)
    semilla.cargar_catalogo(db)
    cabanas = semilla.cargar_los_buhos(db)
    return cabanas, semilla.cargar_salon_los_buhos(db, cabanas)


def test_el_salon_queda_en_borrador_junto_a_las_cabanas(db, tmp_path, monkeypatch):
    cabanas, salon = _cargar(db, tmp_path, monkeypatch)
    assert salon.estado is EstadoPublicacion.BORRADOR
    assert salon.es_demo
    # Mismo anfitrión y mismo lugar: es lo que habilita el paquete salón + cabañas.
    assert salon.prestador_id == cabanas.prestador_id
    assert salon.localidad_id == cabanas.localidad_id
    assert salon.tipo_servicio.modo_reserva is ModoReserva.HORAS
    assert salon.politica_cancelacion.codigo == "eventos"
    assert [c.codigo for c in salon.comodidades] == ["mesas_sillas"]
    # Nada inventado: ni espacios ni precios ni descripción.
    faltan = edicion.faltantes(db, salon)
    assert "Falta cargar al menos un espacio" in faltan
    assert any("descripción" in f for f in faltan)
    # Correr la semilla otra vez no lo duplica.
    assert semilla.cargar_salon_los_buhos(db, cabanas).id == salon.id


def test_las_fotos_van_en_el_orden_de_los_datos(tmp_path, monkeypatch):
    monkeypatch.setattr(semilla, "CARPETA_SALON_LOS_BUHOS", tmp_path)
    for nombre in reversed(datos.LOS_BUHOS_SALON["fotos"]):
        (tmp_path / nombre).write_bytes(b"x")
    (tmp_path / "LEEME.md").write_text("no es foto")
    assert [p.name for p in semilla.fotos_del_salon_los_buhos()] == (
        datos.LOS_BUHOS_SALON["fotos"]
    )


def test_limpiar_la_demo_se_lleva_el_salon_con_sus_turnos(db, tmp_path, monkeypatch):
    """Con turnos y bloqueos por hora cargados, la limpieza fallaba por clave foránea."""
    _, salon = _cargar(db, tmp_path, monkeypatch)
    espacio = Unidad(publicacion_id=salon.id, nombre="Salón", capacidad=60)
    db.add(espacio)
    db.flush()
    db.add(FranjaHoraria(unidad_id=espacio.id, nombre="Noche", hora_inicio=time(21),
                         hora_fin=time(5), precio=Decimal(300000)))
    inicio = datetime.now(UTC) + timedelta(days=10)
    db.add(BloqueoHorario(unidad_id=espacio.id, origen=OrigenBloqueo.MANUAL,
                          rango=Range(inicio, inicio + timedelta(hours=3))))
    db.flush()

    semilla.limpiar_demo(db)
    db.flush()
    assert db.scalar(select(Publicacion).where(Publicacion.id == salon.id)) is None
