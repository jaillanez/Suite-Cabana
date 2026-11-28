"""Fixtures de tests. Los de búsqueda necesitan Postgres con PostGIS de verdad:
la disponibilidad se apoya en rangos de fecha y en la restricción de exclusión,
que no existen fuera de Postgres. Si la base de test no está, se saltean con un
mensaje que dice cómo crearla.
"""

from __future__ import annotations

import os

# Los tests no salen a internet: sin geocodificador, ubicar por dirección no hace
# nada (los que lo prueban lo reemplazan). Antes de importar la app.
os.environ["GEOCODIFICADOR_URL"] = ""

from datetime import date, timedelta  # noqa: E402
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Base,
    BloqueoFecha,
    Comodidad,
    Foto,
    Localidad,
    Prestador,
    Provincia,
    Publicacion,
    ReglaComision,
    SubtipoServicio,
    Tarifa,
    TipoServicio,
    Unidad,
    Usuario,
)
from app.models.enums import EstadoPublicacion, ModoReserva, OrigenBloqueo, QuienPaga

URL_TEST = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://suite:suite@localhost:5432/suite_cabana_test"
)
# Relativas a hoy: con fechas fijas, los tests que comparan contra el reloj real
# (reintegros por anticipación, tramos de calendario) se rompen al pasar el día.
HOY = date.today()
LLEGADA = HOY + timedelta(days=26)
SALIDA = LLEGADA + timedelta(days=3)


@pytest.fixture(autouse=True)
def _calendarios_sin_internet(monkeypatch):
    """Al conectar un calendario se lo lee en el momento. En los tests no se sale
    a internet: por defecto la plataforma "no responde" (se guarda y se reintenta).
    El test que necesita otra respuesta reemplaza `calendario.descargar`."""
    import httpx

    def sin_red(url):
        raise httpx.ConnectError("los tests no salen a internet", request=httpx.Request("GET", url))

    monkeypatch.setattr("app.services.calendario.descargar", sin_red)


@pytest.fixture(scope="session")
def engine():
    motor = create_engine(URL_TEST)
    try:
        with motor.connect() as con:
            con.execute(text("SELECT postgis_version()"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Sin base de test ({e.__class__.__name__}). Corré scripts/crear_db.sh")
    Base.metadata.drop_all(motor)
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture
def db(engine) -> Session:
    """Cada test corre en su propia transacción y se deshace al terminar.

    `join_transaction_mode="create_savepoint"` hace que un `commit()` del código
    bajo prueba —los endpoints commitean— libere un savepoint en vez de cerrar la
    transacción externa, así el rollback final sigue limpiando todo.
    """
    conexion = engine.connect()
    trans = conexion.begin()
    sesion = sessionmaker(
        bind=conexion, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )()
    try:
        yield sesion
    finally:
        sesion.close()
        trans.rollback()
        conexion.close()


@pytest.fixture
def cliente(db: Session):
    """Cliente HTTP contra la app real, con la sesión de test."""
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _punto(lat: float, lon: float) -> str:
    return f"SRID=4326;POINT({lon} {lat})"


@pytest.fixture
def oferta(db: Session) -> dict:
    """Oferta mínima y explícita: dos localidades, cuatro unidades, un bloqueo."""
    provincia = Provincia(nombre="Río Negro", slug="rio-negro")
    db.add(provincia)
    db.flush()
    bariloche = Localidad(
        provincia_id=provincia.id,
        nombre="San Carlos de Bariloche",
        slug="bariloche",
        ubicacion=_punto(-41.1335, -71.3103),
    )
    bolson = Localidad(
        provincia_id=provincia.id,
        nombre="El Bolsón",
        slug="el-bolson",
        ubicacion=_punto(-41.9667, -71.5333),
    )
    db.add_all([bariloche, bolson])

    tipo = TipoServicio(codigo="alojamiento", nombre="Alojamiento", modo_reserva=ModoReserva.NOCHES)
    db.add(tipo)
    db.flush()
    subtipo = SubtipoServicio(tipo_id=tipo.id, codigo="cabana", nombre="Cabaña")
    wifi = Comodidad(codigo="wifi", nombre="WiFi", tipos=[tipo])
    pileta = Comodidad(codigo="pileta", nombre="Pileta", tipos=[tipo])
    db.add_all([subtipo, wifi, pileta])

    usuario = Usuario(
        email="p@demo.test", nombre="P", apellido="Demo", es_prestador=True,
        telefono="+5492944000000",
    )
    db.add(usuario)
    db.flush()
    prestador = Prestador(
        usuario_id=usuario.id,
        razon_social="Prestador de prueba",
        fecha_alta=HOY - timedelta(days=400),
        es_demo=True,
    )
    db.add(prestador)
    db.flush()

    db.add(
        ReglaComision(
            nombre="Comisión general",
            es_default=True,
            activa=True,
            porcentaje=Decimal(10),
            quien_paga=QuienPaga.PRESTADOR,
        )
    )

    def publicar(titulo, slug, localidad, lat, lon, comodidades, inmediata=True, estado=None):
        p = Publicacion(
            prestador_id=prestador.id,
            tipo_servicio_id=tipo.id,
            subtipo_servicio_id=subtipo.id,
            titulo=titulo,
            slug=slug,
            descripcion="Descripción de prueba",
            estado=estado or EstadoPublicacion.APROBADA,
            localidad_id=localidad.id,
            ubicacion=_punto(lat, lon),
            confirmacion_inmediata=inmediata,
            es_demo=True,
        )
        p.comodidades = comodidades
        db.add(p)
        db.flush()
        db.add(Foto(publicacion_id=p.id, url=f"/fotos/demo/{slug}.jpg", orden=0))
        return p

    def unidad(publicacion, nombre, capacidad, precio, **kw):
        u = Unidad(
            publicacion_id=publicacion.id, nombre=nombre, capacidad=capacidad, **kw
        )
        db.add(u)
        db.flush()
        db.add(Tarifa(unidad_id=u.id, nombre="Base", precio_noche=Decimal(precio)))
        return u

    barata = publicar("Cabañas Baratas", "baratas", bariloche, -41.14, -71.31, [wifi])
    cara = publicar("Complejo Caro", "caro", bariloche, -41.20, -71.40, [wifi, pileta])
    solicitud = publicar(
        "Posada A Solicitud", "solicitud", bariloche, -41.13, -71.30, [wifi], inmediata=False
    )
    borrador = publicar(
        "Sin Aprobar", "sin-aprobar", bariloche, -41.13, -71.31, [wifi],
        estado=EstadoPublicacion.BORRADOR,
    )
    lejos = publicar("Cabañas del Bolsón", "bolson", bolson, -41.96, -71.53, [wifi])

    u_barata = unidad(barata, "Cabaña 1", 4, 50000)
    u_cara = unidad(cara, "Cabaña 1", 6, 90000)
    u_chica = unidad(cara, "Cabaña chica", 2, 40000)
    unidad(solicitud, "Suite", 4, 60000)
    unidad(borrador, "Cabaña 1", 4, 10000)
    unidad(lejos, "Cabaña 1", 4, 45000)

    # La unidad barata está tomada justo en las fechas que buscan los tests.
    db.add(
        BloqueoFecha(
            unidad_id=u_barata.id,
            rango=Range(LLEGADA, SALIDA, bounds="[)"),
            origen=OrigenBloqueo.MANUAL,
            activo=True,
        )
    )
    db.flush()

    return {
        "bariloche": bariloche,
        "barata": barata,
        "cara": cara,
        "u_barata": u_barata,
        "u_cara": u_cara,
        "u_chica": u_chica,
        "prestador": prestador,
        "tipo": tipo,
        "wifi": wifi,
    }
