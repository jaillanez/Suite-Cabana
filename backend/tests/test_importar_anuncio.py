# ruff: noqa: E501  (los anuncios de ejemplo tienen líneas largas, como los reales)
"""Leer el texto de un anuncio de Airbnb o Booking que pega el prestador: se
propone, no se guarda nada."""

from datetime import time

import pytest

from app.core.security import crear_token
from app.models import Comodidad, Usuario
from app.services import importar_anuncio as imp

AIRBNB = """Cabaña con vista al lago y parrilla
Cabaña entera en Villa La Angostura, Argentina
4 huéspedes · 2 dormitorios · 3 camas · 1,5 baños
Anfitrión: Marta
Acerca de este espacio
Cabaña de madera a 200 metros del lago, rodeada de bosque. Ideal para familias que buscan tranquilidad y naturaleza.
El living tiene hogar a leña y ventanales al jardín. La cocina está completamente equipada para cocinar todos los días.
Mostrar más
Lo que este lugar ofrece
Vista al lago
Wifi
Estacionamiento gratuito en las instalaciones
TV
Calefacción
Lavarropas
No disponible: Aire acondicionado
No disponible: Detector de monóxido de carbono
Mostrar los 32 servicios
Cosas que tenés que saber
Reglas de la casa
Llegada: a partir de las 15:00
Salida antes de las 10:00
Máximo 4 huéspedes
No se admiten mascotas
No se permiten fiestas ni eventos
Prohibido fumar
Seguridad y propiedad
Detector de humo
"""

BOOKING = """Departamento Centro Mendoza
Servicios más populares
Piscina al aire libre
WiFi gratis
Parking gratis
Aire acondicionado
Desayuno
Este alojamiento está a 5 minutos a pie del centro y cuenta con piscina al aire libre, solárium y vistas a la ciudad.
Normas de la casa
Entrada De 14:00 a 22:00
Salida Hasta las 11:00
Mascotas No se admiten.
Fiestas No se permiten fiestas o eventos.
"""


def test_un_anuncio_de_airbnb():
    p = imp.leer(AIRBNB)
    assert p.descripcion.startswith("Cabaña de madera a 200 metros del lago")
    assert "cocina está completamente equipada" in p.descripcion
    assert "Mostrar más" not in p.descripcion
    assert (p.hora_ingreso, p.hora_salida) == (time(15), time(10))
    assert (p.huespedes, p.dormitorios, p.camas, p.banos) == (4, 2, 3, "1,5")
    # Lo que dice "No disponible" no entra, aunque nombre la comodidad.
    assert "aire" not in p.comodidades
    assert set(p.comodidades) >= {"wifi", "cochera", "tv", "calefaccion", "lavarropas", "parrilla"}
    assert "mascotas" not in p.comodidades  # "No se admiten mascotas"
    assert "• Prohibido fumar" in p.reglas_casa
    # Lo que está bajo "Reglas de la casa", aunque venga después de "Cosas que tenés que saber".
    assert "• Máximo 4 huéspedes" in p.reglas_casa
    assert "• No se admiten mascotas" in p.reglas_casa
    assert "Reglas de la casa" not in p.reglas_casa  # el encabezado no es una regla
    assert "• No se permiten fiestas ni eventos" in p.reglas_casa
    assert "Llegada" not in p.reglas_casa  # los horarios van en sus campos


def test_un_anuncio_de_booking():
    p = imp.leer(BOOKING)
    assert set(p.comodidades) >= {"pileta", "wifi", "cochera", "aire", "desayuno"}
    assert (p.hora_ingreso, p.hora_salida) == (time(14), time(11))
    assert p.descripcion.startswith("Este alojamiento está a 5 minutos")


@pytest.mark.parametrize(
    "texto, ingreso",
    [
        ("Check-in: 3:00 p. m. y algo más de texto suelto", time(15)),
        ("Llegada a partir de las 14 h, el resto lo coordinamos", time(14)),
        ("Llegada con 2 personas como máximo, y todo lo demás", None),
    ],
)
def test_las_horas_en_varios_formatos(texto, ingreso):
    assert imp.leer(texto).hora_ingreso == ingreso


def test_un_texto_corto_o_enorme_se_rechaza():
    with pytest.raises(imp.TextoInvalido, match="corto"):
        imp.leer("Wifi")
    with pytest.raises(imp.TextoInvalido, match="largo"):
        imp.leer("a" * (imp.TEXTO_MAXIMO + 1))


def test_tv_no_se_confunde_dentro_de_otra_palabra():
    assert "tv" not in imp.leer("Una estadía tvbox inolvidable en la montaña, con mucho verde").comodidades


# --- API ---


@pytest.fixture
def anfitrion(db, oferta):
    dueno = db.get(Usuario, oferta["prestador"].usuario_id)
    return {"Authorization": f"Bearer {crear_token(str(dueno.id))}"}


def test_la_api_propone_sin_guardar_nada(cliente, db, anfitrion, oferta):
    p = oferta["cara"]
    antes = (p.descripcion, p.hora_ingreso, sorted(c.codigo for c in p.comodidades))
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{p.id}/importar-anuncio", headers=anfitrion,
        json={"texto": AIRBNB},
    )
    assert r.status_code == 200, r.text
    x = r.json()
    assert x["hora_ingreso"] == "15:00:00" and x["huespedes"] == 4
    # Solo códigos del catálogo de este tipo de servicio.
    validas = {c.codigo for c in db.query(Comodidad)}
    assert set(x["comodidades"]) <= validas
    db.refresh(p)
    assert (p.descripcion, p.hora_ingreso, sorted(c.codigo for c in p.comodidades)) == antes


def test_la_api_avisa_si_no_encontro_nada(cliente, anfitrion, oferta):
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{oferta['cara'].id}/importar-anuncio", headers=anfitrion,
        json={"texto": "hola hola hola hola hola hola"},
    )
    assert r.status_code == 422 and "Copiá la página entera" in r.json()["detail"]


def test_otro_prestador_no_importa_en_lo_ajeno(cliente, oferta):
    r = cliente.post(
        f"/api/v1/mis-publicaciones/{oferta['cara'].id}/importar-anuncio",
        json={"texto": AIRBNB},
    )
    assert r.status_code == 401
